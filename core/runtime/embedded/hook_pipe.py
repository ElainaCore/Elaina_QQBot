"""SnowLuma 兼容 Hook DLL 的本机管道客户端（QHP1 协议）。

DLL 注入 QQ 后在进程内创建两条命名管道（``mojo.<pid>.control`` 与
``mojo.<pid>.recv``，位于 named-pipe 根目录）。协议帧格式（全部小端）::

    magic  u32 = 0x314D5151 ('QHP1'  ASCII)
    ver    u16 = 1
    op     u16
    reqId  u32
    status i32
    flags  u32   (bit0 = 期望回复, bit2 = 已登录)
    cmdLen u32
    msgLen u32
    bodyLen u32
    pad    u32
    value0 u64
    cmd    bytes[cmdLen]
    msg    bytes[msgLen]
    body   bytes[bodyLen]

op 码（由 SnowLuma ``index.mjs`` 桥接源反推）::

    1 = HELLO       控制端连接后由 DLL 主动推送
    2 = REQUEST     客户端 → DLL 的服务请求（cmd=trpc 服务名）
    3 = ACK         请求已受理
    4 = REPLY       请求最终回复（status=错误码，body=响应）
    5 = ERROR       请求失败通知
    6 = PACKET      recv 管道上的原始包事件（value0=seq, cmd=服务名, msg=uin）
    7 = LOGIN_STATE 登录态推送（value0=uin, msg=uin 字符串）
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
from dataclasses import dataclass, field

log = logging.getLogger('ElainaQQ.embedded_qq.hook')

PIPE_MAGIC = 827344977  # 'QHP1'
PIPE_VERSION = 1
FLAG_WANT_REPLY = 1
FLAG_LOGGED_IN = 4
MAX_FRAME_BODY = 16 * 1024 * 1024
# 与 SnowLuma encodeFrame 完全一致：40 字节头，value0 紧跟 bodyLen（无 pad）
HEADER = struct.Struct('<IHHIiIIIIQ')  # 40 字节

OP_HELLO = 1
OP_REQUEST = 2
OP_ACK = 3
OP_REPLY = 4
OP_ERROR = 5
OP_PACKET = 6
OP_LOGIN_STATE = 7


@dataclass(slots=True)
class Frame:
    op: int = 0
    request_id: int = 0
    status: int = 0
    flags: int = 0
    value0: int = 0
    cmd: str = ''
    msg: str = ''
    body: bytes = field(default=b'', repr=False)

    @classmethod
    def decode(cls, buf: bytes) -> tuple['Frame', int]:
        """解析一帧，返回 (frame, 总字节数)；数据不足返回 (frame(空), 0)。"""
        if len(buf) < HEADER.size:
            return cls(), 0
        magic, version, op, request_id, status, flags, cmd_len, msg_len, body_len, value0 = HEADER.unpack_from(buf)
        if magic != PIPE_MAGIC or version != PIPE_VERSION:
            raise ValueError(f'管道帧头不合法: magic=0x{magic:08X} version={version}')
        total = HEADER.size + cmd_len + msg_len + body_len
        if len(buf) < total:
            return cls(), 0
        offset = HEADER.size
        cmd = buf[offset:offset + cmd_len]
        offset += cmd_len
        msg = buf[offset:offset + msg_len]
        offset += msg_len
        body = buf[offset:offset + body_len]
        return cls(
            op=op,
            request_id=request_id,
            status=status,
            flags=flags,
            value0=value0,
            cmd=cmd.decode('utf-8', 'replace'),
            msg=msg.decode('utf-8', 'replace'),
            body=body,
        ), total

    def encode(self) -> bytes:
        cmd = self.cmd.encode('utf-8')
        msg = self.msg.encode('utf-8')
        if max(len(cmd), len(msg), len(self.body)) > MAX_FRAME_BODY:
            raise ValueError('管道帧负载超长')
        return HEADER.pack(
            PIPE_MAGIC, PIPE_VERSION, self.op, self.request_id & 0xFFFFFFFF, self.status,
            self.flags, len(cmd), len(msg), len(self.body), self.value0,
        ) + cmd + msg + self.body


def control_pipe_name(pid: int) -> str:
    return rf'\\.\pipe\mojo.{pid}.control'


def recv_pipe_name(pid: int) -> str:
    return rf'\\.\pipe\mojo.{pid}.recv'


class HookPipe:
    """单条命名管道的异步读写封装。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self._handle = None
        self._buffer = b''
        self._closed = False

    @property
    def ok(self) -> bool:
        return self._handle is not None and not self._closed

    def connect(self) -> bool:
        """打开命名管道（同步，在线程中调用）。"""
        import ctypes

        gen = ctypes.WinDLL('kernel32', use_last_error=True)
        gen.CreateFileW.restype = ctypes.c_void_p
        gen.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ]
        handle = gen.CreateFileW(self.name, 0xC0000000, 0, None, 3, 0, None)  # GENERIC_READ|WRITE, OPEN_EXISTING
        if handle in (None, 0, 0xFFFFFFFFFFFFFFFF):
            self._handle = None
            return False
        self._handle = handle
        return True

    async def connect_async(self) -> bool:
        return await asyncio.to_thread(self.connect)

    def _read_once(self) -> bytes:
        import ctypes

        gen = ctypes.WinDLL('kernel32', use_last_error=True)
        avail = ctypes.c_uint32(0)
        if not gen.PeekNamedPipe(self._handle, None, 0, None, ctypes.byref(avail), None) or not avail.value:
            return b''
        out = ctypes.create_string_buffer(avail.value)
        got = ctypes.c_uint32(0)
        if not gen.ReadFile(self._handle, out, avail.value, ctypes.byref(got), None):
            raise ConnectionError(f'管道 {self.name} 读取失败: error={ctypes.get_last_error()}')
        return out.raw[:got.value]

    def _write_all(self, data: bytes) -> None:
        import ctypes

        gen = ctypes.WinDLL('kernel32', use_last_error=True)
        wrote = ctypes.c_uint32(0)
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        offset = 0
        while offset < len(data):
            if not gen.WriteFile(self._handle, buf, len(data) - offset, ctypes.byref(wrote), None):
                raise ConnectionError(f'管道 {self.name} 写入失败: error={ctypes.get_last_error()}')
            offset += wrote.value
            if wrote.value == 0:
                raise ConnectionError(f'管道 {self.name} 写入停滞')
            buf = ctypes.create_string_buffer(bytes(data[offset:]), len(data) - offset)

    async def pump(self) -> list[Frame]:
        """读取当前可用的全部完整帧。连接断开时抛出 ConnectionError。"""
        if not self.ok:
            return []
        try:
            chunk = await asyncio.to_thread(self._read_once)
        except ConnectionError:
            await self.close()
            raise
        if not chunk:
            return []
        self._buffer += chunk
        frames: list[Frame] = []
        try:
            while True:
                frame, used = Frame.decode(self._buffer)
                if used == 0:
                    break
                frames.append(frame)
                self._buffer = self._buffer[used:]
        except ValueError as exc:
            # 坏帧（含流错位）：清空缓冲重同步。DLL 不会发非 QHP1 数据，
            # 走到这里多半是上一帧长度解错后的连锁，重同步是最快恢复方式。
            self._buffer = b''
            log.warning('丢弃 %s 上的坏帧: %s', self.name, exc)
        return frames

    async def write(self, frame: Frame) -> None:
        if not self.ok:
            raise ConnectionError(f'管道 {self.name} 未连接')
        await asyncio.to_thread(self._write_all, frame.encode())

    async def close(self) -> None:
        handle, self._handle, self._closed = self._handle, None, True
        if handle is not None:
            await asyncio.to_thread(_close_handle, handle)

    def __repr__(self) -> str:  # pragma: no cover
        return f'<HookPipe {self.name} ok={self.ok}>'


def _close_handle(handle) -> None:
    import ctypes

    ctypes.WinDLL('kernel32', use_last_error=True).CloseHandle(handle)
