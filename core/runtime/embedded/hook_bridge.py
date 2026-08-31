"""SnowLuma 兼容 Hook DLL 的 Python 接管桥。

一个 QQ 主进程一条 :class:`HookBridge`：持有 control/recv 两条 QHP1 管道，
把 DLL 推送的 MsgPush 原始包解码为 OneBot 事件并注入框架，同时用 op=2 请求
实现 send_msg / get_msg 等动作（与 SnowLuma ``QqHookClient`` 行为一致）。

连接语义（对照 SnowLuma）::

    control 连接后 DLL 立即推 HELLO(op=1)
    recv 连接后 DLL 推 HELLO + LOGIN_STATE(op=7, flags 含 bit2=已登录)
    recv 管道持续推 PACKET(op=6)，value0=seq、cmd=服务名、msg=uin
    op=2 请求: DLL 先回 ACK(op=3) 再回 REPLY(op=4, status=错误码, body=响应)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
import time
from dataclasses import dataclass, field as dc_field
from typing import Any, Awaitable, Callable

from core.runtime.embedded import hook_msgpush as msgpush
from core.runtime.embedded import hook_send as sendpb
from core.runtime.embedded.hook_pipe import (
    FLAG_LOGGED_IN,
    Frame,
    HookPipe,
    OP_ACK,
    OP_ERROR,
    OP_HELLO,
    OP_LOGIN_STATE,
    OP_PACKET,
    OP_REPLY,
    OP_REQUEST,
    PIPE_VERSION,
    control_pipe_name,
    recv_pipe_name,
)

log = logging.getLogger('ElainaQQ.embedded_qq.hook')

DEFAULT_ACK_TIMEOUT = 5.0
DEFAULT_REPLY_TIMEOUT = 60.0
HELLO_TIMEOUT = 8.0

OLPUSH_CMD = 'trpc.msg.olpush.OlPushService.MsgPush'

# PkgType（与 SnowLuma enums.ts 一致）
PKG_GROUP_MESSAGE = 82
PKG_PRIVATE_MESSAGE = 166
PKG_TEMP_MESSAGE = 141
PKG_GROUP_REQUEST_JOIN = 84
PKG_GROUP_SELF_JOINED = 85
PKG_GROUP_INVITE = 87
PKG_GROUP_ADMIN_CHANGED = 44
PKG_GROUP_MEMBER_INCREASE = 33
PKG_GROUP_MEMBER_DECREASE = 34
PKG_EVENT_0X210 = 528
PKG_EVENT_0X2DC = 732
PKG_PRIVATE_RECORD = 208
PKG_PRIVATE_FILE = 529

MESSAGE_EVENTS = frozenset({82, 166, 141, 208, 529})

EVENT_DISPATCHER = Callable[[dict], Awaitable[None]]


def hash_message_id(sequence: int, session_id: int, event_name: str) -> int:
    """与 SnowLuma hashMessageIdInt32 完全一致的 int32 消息 ID。"""
    key = f'{int(sequence)}:{int(session_id)}:{event_name}'.encode()
    id_ = int.from_bytes(hashlib.sha1(key).digest()[:4], 'big', signed=True)
    return id_ or 1


@dataclass(slots=True)
class HookStatus:
    pid: int = 0
    control_open: bool = False
    recv_open: bool = False
    logged_in: bool = False
    uin: str = ''
    hello: str = ''
    last_packet_at: float = 0.0
    packet_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            'pid': self.pid,
            'control_open': self.control_open,
            'recv_open': self.recv_open,
            'logged_in': self.logged_in,
            'uin': self.uin,
            'hello': self.hello,
            'last_packet_at': self.last_packet_at,
            'packet_count': self.packet_count,
        }


class HookBridge:
    """接管一条已注入 DLL 的 QQ 主进程。"""

    def __init__(self, pid: int, on_event: EVENT_DISPATCHER | None = None) -> None:
        self.pid = pid
        self.on_event = on_event
        self.status = HookStatus(pid=pid)
        self._control = HookPipe(control_pipe_name(pid))
        self._recv = HookPipe(recv_pipe_name(pid))
        self._pump_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._request_id = 9000
        self._dispatch_tasks: set[asyncio.Task] = set()
        self.forward_self_messages = True  # 是否接收自身消息回显（embedded_qq.self_message_enabled）
        self._closed = False
        self._snapshot: dict[int, dict[str, Any]] = {}

    # -- 生命周期 -----------------------------------------------------------

    async def connect(self) -> bool:
        """连接两条管道并等待 HELLO；返回是否全部就绪。"""
        if self.status.control_open:
            return True
        control_ok = await self._control.connect_async()
        recv_ok = await self._recv.connect_async()
        self.status.control_open = control_ok
        self.status.recv_open = recv_ok
        if not control_ok:
            return False
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.create_task(self._pump_loop(), name=f'hook-pump-{self.pid}')
        if not await self._wait_hello():
            await self.close()
            return False
        return True

    async def _wait_hello(self) -> bool:
        deadline = time.monotonic() + HELLO_TIMEOUT
        while time.monotonic() < deadline:
            if self.status.hello:
                return True
            await asyncio.sleep(0.05)
        return False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError('接管桥已关闭'))
        self._pending.clear()
        if self._pump_task:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._pump_task = None
        await self._control.close()
        await self._recv.close()
        self.status.control_open = self.status.recv_open = False

    # -- 泵与帧处理 ---------------------------------------------------------

    async def _pump_loop(self) -> None:
        while not self._closed:
            try:
                frames = await self._control.pump() + await self._recv.pump()
            except ConnectionError:
                self.status.control_open = self.status.recv_open = False
                log.info('QQ(pid=%s) 管道断开', self.pid)
                break
            if frames:
                for frame in frames:
                    self._handle_frame(frame)
            await asyncio.sleep(0.03)

    def _handle_frame(self, frame: Frame) -> None:
        op = frame.op
        if op == OP_HELLO:
            self.status.hello = frame.msg or str(frame.value0)
            return
        if op == OP_LOGIN_STATE:
            self.status.logged_in = bool(frame.flags & FLAG_LOGGED_IN)
            if frame.msg:
                self.status.uin = frame.msg
            elif frame.value0:
                self.status.uin = str(frame.value0)
            return
        if op == OP_PACKET:
            self.status.packet_count += 1
            self.status.last_packet_at = time.time()
            self._handle_packet(frame)
            return
        if op in (OP_ACK, OP_REPLY, OP_ERROR):
            fut = self._pending.pop(frame.request_id, None)
            if fut is None or fut.done():
                return
            if op == OP_ACK:
                return  # 仅确认受理，继续等 REPLY
            if op == OP_ERROR:
                fut.set_exception(RuntimeError(frame.msg or f'hook 请求失败 status={frame.status}'))
                return
            if frame.status != 0:
                fut.set_exception(RuntimeError(f'hook 请求失败 status={frame.status}: {frame.msg}'))
            else:
                fut.set_result(frame.body)

    # -- 包处理 -------------------------------------------------------------

    def _handle_packet(self, frame: Frame) -> None:
        cmd = frame.cmd
        if cmd != OLPUSH_CMD:
            log.debug('忽略服务包 cmd=%s seq=%s', cmd, frame.value0)
            return
        self_uin = int(self.status.uin) if self.status.uin.isdigit() else 0
        for ctx in msgpush.parse_push(frame.body, self_uin):
            payload = self._build_event(ctx)
            if payload is None:
                continue
            self._remember(ctx, payload)
            if self.on_event:
                task = asyncio.get_running_loop().create_task(self._dispatch(payload))
                self._dispatch_tasks.add(task)
                task.add_done_callback(self._dispatch_tasks.discard)

    async def _dispatch(self, payload: dict) -> None:
        if payload.get('post_type') == 'message_sent' and not self.forward_self_messages:
            return  # 已关闭「接收自身消息」：丢弃自发回显，不进事件管线
        try:
            await self.on_event(payload)  # type: ignore[misc]
        except Exception:  # noqa: BLE001
            log.exception('接管事件分发失败')

    def _build_event(self, ctx: msgpush.MsgContext) -> dict[str, Any] | None:
        if ctx.msg_type not in MESSAGE_EVENTS:
            return None
        if ctx.msg_type in (PKG_GROUP_MESSAGE,):
            return self._event_group(ctx)
        return self._event_private(ctx)

    # -- 事件构造（对照 SnowLuma onebot 事件转换器）--------------------------

    def _common_time(self, ctx: msgpush.MsgContext) -> int:
        return ctx.timestamp or int(time.time())

    @staticmethod
    def _raw_pb(ctx: msgpush.MsgContext) -> dict[str, Any]:
        """返回当前消息解码前的 protobuf，供消息记录面板查阅。"""
        return {
            'format': 'protobuf',
            'encoding': 'hex',
            'command': OLPUSH_CMD,
            'byte_length': len(ctx.raw_pb),
            'data': ctx.raw_pb.hex(),
        }

    def _message_id_group(self, ctx: msgpush.MsgContext) -> int:
        return hash_message_id(ctx.sequence, ctx.group_uin, 'group_message')

    def _message_id_private(self, ctx: msgpush.MsgContext, is_self: bool) -> int:
        if ctx.nt_msg_seq > 0:
            name = 'private_message_sent' if is_self else 'private_message_nt'
            return hash_message_id(ctx.nt_msg_seq, ctx.peer_uin, name)
        return hash_message_id(ctx.sequence, ctx.peer_uin,
                               'private_message_sent' if is_self else 'private_message')

    def _event_group(self, ctx: msgpush.MsgContext) -> dict[str, Any]:
        is_self = ctx.from_uin == ctx.self_uin
        segments = self._to_segments(msgpush.decode_elements(ctx.body))
        payload: dict[str, Any] = {
            'post_type': 'message_sent' if is_self else 'message',
            'self_id': str(ctx.self_uin),
            'time': self._common_time(ctx),
            'message_type': 'group',
            'sub_type': 'normal',
            'message_id': self._message_id_group(ctx),
            'message_seq': ctx.sequence,
            'real_seq': ctx.sequence,
            'group_id': ctx.group_uin,
            'group_name': ctx.group_name,
            'user_id': ctx.from_uin,
            'message': segments,
            'raw_message': self._raw_message(segments),
            'raw_pb': self._raw_pb(ctx),
            'sender': {
                'user_id': ctx.from_uin,
                'nickname': ctx.member_name,
                'card': ctx.member_card,
                'role': 'member',
                'sex': 'unknown',
                'age': 0,
            },
            'anonymous': None,
            'font': 0,
        }
        if is_self and ctx.to_uin:
            payload['target_id'] = ctx.to_uin
        return payload

    def _event_private(self, ctx: msgpush.MsgContext) -> dict[str, Any]:
        is_self = ctx.from_uin == ctx.self_uin
        temp = ctx.msg_type == PKG_TEMP_MESSAGE
        peer = ctx.peer_uin
        segments = self._to_segments(msgpush.decode_elements(ctx.body))
        payload: dict[str, Any] = {
            'post_type': 'message_sent' if is_self else 'message',
            'self_id': str(ctx.self_uin),
            'time': self._common_time(ctx),
            'message_type': 'private',
            'sub_type': 'group' if temp else 'friend',
            'message_id': self._message_id_private(ctx, is_self),
            'message_seq': ctx.sequence,
            'real_seq': ctx.sequence,
            'user_id': ctx.from_uin,
            'message': segments,
            'raw_message': self._raw_message(segments),
            'raw_pb': self._raw_pb(ctx),
            'sender': {
                'user_id': ctx.from_uin,
                'nickname': ctx.member_name if temp else '',
                'sex': 'unknown',
                'age': 0,
            },
            'font': 0,
        }
        if temp and ctx.group_uin:
            payload['sender']['group_id'] = ctx.group_uin
        if is_self and peer and peer != ctx.self_uin:
            payload['target_id'] = peer
        return payload

    _SEGMENT_MAP = {
        'text': ('text', lambda d: {'text': d.get('text', '')}),
        'at': ('at', lambda d: {'qq': str(d.get('qq') or d.get('target_uin') or '')}),
        'face': ('face', lambda d: {'id': str(d.get('id', ''))}),
        'mface': ('mface', lambda d: {k: d[k] for k in
                                      ('text', 'emoji_id', 'emoji_package_id', 'emoji_key') if k in d}),
        'image': ('image', lambda d: {k: d[k] for k in ('file', 'url', 'file_size', 'width', 'height')
                                      if d.get(k) is not None}),
        'record': ('record', lambda d: {'file': d.get('file', ''), 'file_id': d.get('file_id', ''),
                                        'file_size': d.get('file_size', 0),
                                        'duration': d.get('duration', 0)}),
        'video': ('video', lambda d: {'file': d.get('file', ''), 'file_size': d.get('file_size', 0),
                                      'duration': d.get('duration', 0)}),
        'file': ('file', lambda d: {'file_id': d.get('file_id', ''), 'name': d.get('name', ''),
                                    'size': d.get('size', 0)}),
        'reply': ('reply', lambda d: {'id': str(d.get('seq', ''))}),
        'json': ('json', lambda d: {'data': d.get('data', '')}),
        'xml': ('xml', lambda d: {'data': d.get('data', '')}),
        'poke': ('poke', lambda d: {'sub_type': d.get('sub_type', 0)}),
    }

    def _to_segments(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        for element in elements:
            map_entry = self._SEGMENT_MAP.get(element.get('type', ''))
            if map_entry is None:
                continue
            seg_type, build = map_entry
            data = build(element)
            if seg_type == 'image' and not data.get('url') and not data.get('file'):
                continue
            segments.append({'type': seg_type, 'data': data})
        return segments

    @staticmethod
    def _raw_message(segments: list[dict[str, Any]]) -> str:
        """把段列表序列化为 CQ 码字符串（与 OneBot raw_message 语义一致）。"""
        parts: list[str] = []
        for seg in segments:
            seg_type = seg['type']
            data = seg.get('data') or {}
            if seg_type == 'text':
                text = str(data.get('text') or '')
                parts.append(text.replace('&', '&amp;').replace('[', '&#91;')
                             .replace(']', '&#93;').replace(',', '&#44;'))
                continue
            fields = ','.join(
                '{}={}'.format(
                    key,
                    str(value).replace('&', '&amp;').replace('[', '&#91;')
                    .replace(']', '&#93;').replace(',', '&#44;')
                    .replace('\r', '&#10;').replace('\n', '&#8260;'),
                )
                for key, value in data.items() if value is not None
            )
            parts.append(f'[CQ:{seg_type}{"," if fields else ""}{fields}]')
        return ''.join(parts)

    # -- 请求缓存（供 get_msg / 回复目标）-----------------------------------

    def _remember(self, ctx: msgpush.MsgContext, payload: dict[str, Any]) -> None:
        self._snapshot[abs(payload.get('message_id', 0))] = {
            'sequence': ctx.sequence,
            'nt_msg_seq': ctx.nt_msg_seq,
            'peer': ctx.peer_uin if ctx.msg_type != PKG_GROUP_MESSAGE else ctx.group_uin,
            'is_group': ctx.msg_type == PKG_GROUP_MESSAGE,
            'time': payload.get('time', 0),
        }
        while len(self._snapshot) > 512:
            self._snapshot.pop(next(iter(self._snapshot)))

    def lookup_message(self, message_id: int) -> dict[str, Any] | None:
        return self._snapshot.get(abs(message_id))

    # -- 发送侧（对照 SnowLuma MessageApi）------------------------------------

    _SELF_SEQ = int(time.time() * 1000) & 0x7FFFFFFF

    def _next_random(self) -> int:
        self._SELF_SEQ = (self._SELF_SEQ + 2654435769) & 0x7FFFFFFF
        return self._SELF_SEQ

    async def _send_request(self, routing: bytes, c2c_cmd: int,
                            elements: list[bytes]) -> dict[str, Any]:
        request = sendpb.encode_send_message_request(
            routing=routing,
            content_head=sendpb.content_head(c2c_cmd=c2c_cmd),
            rich_elems=elements,
            random=self._next_random(),
        )
        reply = await self.request(sendpb.SEND_MSG_CMD, request, reply_timeout=15.0)
        parsed = sendpb.parse_send_response(reply)
        if parsed['result']:
            raise RuntimeError(f"发送被拒: result={parsed['result']} {parsed['err_msg']}")
        return parsed

    def _encode_elements(self, segments: list[dict[str, Any]]) -> list[bytes]:
        elems: list[bytes] = []
        for seg in segments:
            seg_type = seg.get('type', '')
            data = seg.get('data') or {}
            if seg_type == 'text':
                elems.append(sendpb.encode_text_elem(str(data.get('text') or '')))
            elif seg_type == 'at':
                qq = str(data.get('qq') or '0')
                target = 0 if qq == 'all' else int(qq or 0)
                elems.append(sendpb.encode_at_elem(target))
            elif seg_type == 'face':
                elems.append(sendpb.encode_face_elem(int(data.get('id') or 0)))
            elif seg_type == 'reply':
                message_id = int(data.get('id') or 0)
                remembered = self.lookup_message(message_id)
                source_seq = int(data.get('seq') or (remembered or {}).get('sequence') or message_id)
                elems.append(sendpb.encode_reply_elem(source_seq))
            elif seg_type == 'json':
                elems.append(sendpb.encode_json_elem(str(data.get('data') or '')))
            elif seg_type == 'xml':
                elems.append(sendpb.encode_xml_elem(str(data.get('data') or '')))
            else:
                raise ValueError(f'接管通道暂不支持发送段类型: {seg_type}')
        if not elems:
            raise ValueError('消息为空或没有可发送的段')
        return elems

    async def send_group(self, group_id: int, segments: list[dict[str, Any]]) -> dict[str, Any]:
        parsed = await self._send_request(sendpb.routing_group(group_id), 0,
                                          self._encode_elements(segments))
        sequence = parsed['group_seq']
        message_id = hash_message_id(sequence, group_id, 'group_message') if sequence \
            else self._next_random()
        return {'message_id': message_id, 'sequence': sequence,
                'timestamp': parsed['timestamp']}

    async def send_private(self, user_id: int, segments: list[dict[str, Any]],
                           *, temp_group: int = 0) -> dict[str, Any]:
        if temp_group:
            routing = sendpb.routing_grp_tmp(temp_group, '')
        else:
            routing = sendpb.routing_c2c(user_id)
        parsed = await self._send_request(routing, 11, self._encode_elements(segments))
        sequence = parsed['private_seq']
        message_id = self._next_random() or sequence
        return {'message_id': message_id, 'sequence': sequence,
                'timestamp': parsed['timestamp']}

    async def recall_group(self, group_id: int, sequence: int) -> None:
        request = sendpb.encode_group_recall_request(group_id, sequence)
        reply = await self.request(sendpb.GROUP_RECALL_CMD, request, reply_timeout=15.0)
        _ = reply

    async def recall_private(self, user_id: int, client_seq: int, msg_seq: int,
                             random: int, timestamp: int) -> None:
        request = sendpb.encode_c2c_recall_request('', client_seq, msg_seq, random, timestamp)
        await self.request(sendpb.C2C_RECALL_CMD, request, reply_timeout=15.0)

    # -- OneBot 动作入口 ------------------------------------------------------

    async def handle_action(self, action: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """处理 OneBot 动作；返回 None 表示本桥不处理（交回上层）。"""
        from core.protocols.onebot.message import normalize_message

        try:
            if action == 'send_group_msg':
                result = await self.send_group(
                    int(params.get('group_id') or 0),
                    normalize_message(params.get('message')),
                )
                return {'message_id': result['message_id'], 'seq': result['sequence']}
            if action == 'send_private_msg':
                result = await self.send_private(
                    int(params.get('user_id') or 0),
                    normalize_message(params.get('message')),
                )
                return {'message_id': result['message_id'], 'seq': result['sequence']}
            if action == 'send_msg':
                message_type = str(params.get('message_type') or '')
                if not message_type:
                    message_type = 'group' if params.get('group_id') else 'private'
                segments = normalize_message(params.get('message'))
                if message_type == 'group':
                    result = await self.send_group(int(params.get('group_id') or 0), segments)
                else:
                    result = await self.send_private(int(params.get('user_id') or 0), segments)
                return {'message_id': result['message_id'], 'seq': result['sequence']}
            if action == 'delete_msg':
                message_id = int(params.get('message_id') or 0)
                meta = self.lookup_message(message_id)
                if not meta:
                    return {'message_id': message_id, 'error': '未知消息，无法撤回'}
                if meta['is_group']:
                    await self.recall_group(meta['peer'], meta['sequence'])
                # 私聊撤回需要 (client_seq, random, timestamp) 完整四元组，快照缺信息时忽略
                return {}
            if action == 'get_msg':
                message_id = int(params.get('message_id') or 0)
                meta = self.lookup_message(message_id)
                if not meta:
                    return None
                return {'message_id': message_id, **meta}
        except (ValueError, RuntimeError, ConnectionError, TimeoutError) as exc:
            return {'error': str(exc)}
        return None

    # -- op=2 服务请求 ------------------------------------------------------

    async def request(self, cmd: str, body: bytes = b'', *,
                      want_reply: bool = True,
                      reply_timeout: float = DEFAULT_REPLY_TIMEOUT) -> bytes:
        """发送 op=2 请求并等待 REPLY；返回响应 body。"""
        if not self.status.control_open:
            raise ConnectionError(f'QQ(pid={self.pid}) 控制管道未连接')
        self._request_id = (self._request_id + 1) & 0xFFFFFFFF or 1
        request_id = self._request_id
        frame = Frame(
            op=OP_REQUEST,
            request_id=request_id,
            flags=1 if want_reply else 0,
            cmd=cmd,
            body=body,
        )
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut
        try:
            await self._control.write(frame)
        except ConnectionError:
            self._pending.pop(request_id, None)
            raise
        if not want_reply:
            self._pending.pop(request_id, None)
            return b''
        try:
            return await asyncio.wait_for(fut, reply_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise TimeoutError(f'hook 请求 {cmd} 回复超时 ({reply_timeout}s)') from None

    # -- 状态 ----------------------------------------------------------------

    def as_status(self) -> dict[str, Any]:
        return self.status.as_dict()
