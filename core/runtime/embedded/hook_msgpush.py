"""MsgPush 原始包 protobuf 解码。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

log = logging.getLogger('ElainaQQ.embedded_qq.msgpush')

# protobuf 线格式。

_MAX_DEPTH = 64


def read_varint(data: bytes, offset: int, end: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= end:
            raise ValueError('varint 越界')
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
        if shift >= 70:
            raise ValueError('varint 过长')


def iter_fields(data: bytes, offset: int = 0, end: int | None = None,
                depth: int = 0) -> list[tuple[int, int, bytes]]:
    """返回 [(field_number, wire_type, raw_value)]。"""
    out: list[tuple[int, int, bytes]] = []
    end = len(data) if end is None else end
    while offset < end:
        tag, offset = read_varint(data, offset, end)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('protobuf 字段号 0 非法')
        if wire == 0:
            value, offset = read_varint(data, offset, end)
            out.append((number, 0, value.to_bytes((value.bit_length() + 7) // 8 or 1, 'little')))
        elif wire == 1:
            if offset + 8 > end:
                raise ValueError('fixed64 越界')
            out.append((number, 1, data[offset:offset + 8]))
            offset += 8
        elif wire == 2:
            length, offset = read_varint(data, offset, end)
            if offset + length > end:
                raise ValueError('长度越界')
            out.append((number, 2, data[offset:offset + length]))
            offset += length
        elif wire == 5:
            if offset + 4 > end:
                raise ValueError('fixed32 越界')
            out.append((number, 5, data[offset:offset + 4]))
            offset += 4
        elif wire == 3:
            if depth >= _MAX_DEPTH:
                raise ValueError('group 嵌套过深')
            inner_end = _skip_group(data, offset, end, number, depth + 1)
            inner = iter_fields(data, offset, inner_end, depth + 1)
            out.append((number, 3, b''))
            out.extend(inner)
            offset = inner_end
        elif wire == 4:
            raise ValueError('不配对的 end-group')
        else:
            raise ValueError(f'不支持的 wire type {wire}')
    return out


def _skip_group(data: bytes, offset: int, end: int, field_number: int, depth: int) -> int:
    """跳过 group 内容，返回 end-group 之后的偏移。"""
    while offset < end:
        tag, offset = read_varint(data, offset, end)
        number, wire = tag >> 3, tag & 7
        if wire == 4:
            if number != field_number:
                raise ValueError('group 结束标签不匹配')
            return offset
        if wire == 0:
            _, offset = read_varint(data, offset, end)
        elif wire == 1:
            offset += 8
        elif wire == 2:
            length, offset = read_varint(data, offset, end)
            offset += length
        elif wire == 5:
            offset += 4
        elif wire == 3:
            offset = _skip_group(data, offset, end, number, depth + 1)
        else:
            raise ValueError(f'group 内不支持的 wire type {wire}')
        if offset > end:
            raise ValueError('group 越界')
    raise ValueError('group 未闭合')


def pb_int(data: bytes, number: int, default: int = 0) -> int:
    for num, wire, raw in iter_fields(data):
        if num == number and wire in (0, 1, 5):
            return int.from_bytes(raw, 'little')
    return default


def pb_bytes(data: bytes, number: int, default: bytes = b'') -> bytes:
    for num, wire, raw in iter_fields(data):
        if num == number and wire == 2:
            return raw
    return default


def pb_str(data: bytes, number: int, default: str = '') -> str:
    raw = pb_bytes(data, number)
    return raw.decode('utf-8', 'replace') if raw else default


def pb_list(data: bytes, number: int) -> list[bytes]:
    return [raw for num, wire, raw in iter_fields(data) if num == number and wire == 2]


def pb_int_list(data: bytes, number: int) -> list[int]:
    return [int.from_bytes(raw, 'little') for num, wire, raw in iter_fields(data)
            if num == number and wire == 0]


# PushMsg 顶层


@dataclass(slots=True)
class MsgContext:
    """一条推送消息的解析上下文（字段与 SnowLuma buildContext 对齐）。"""

    msg_type: int = 0
    sub_type: int = 0
    c2c_cmd: int = 0
    msg_id: int = 0          # u64 原值；int32 用法需 & 0x7FFFFFFF
    sequence: int = 0
    nt_msg_seq: int = 0
    timestamp: int = 0
    from_uin: int = 0
    from_uid: str = ''
    to_uin: int = 0
    self_uin: int = 0
    group_uin: int = 0
    member_name: str = ''
    member_card: str = ''
    group_name: str = ''
    raw_pb: bytes = dc_field(default=b'', repr=False)
    body: bytes = dc_field(default=b'', repr=False)

    @property
    def is_group(self) -> bool:
        return self.msg_type == 82

    @property
    def peer_uin(self) -> int:
        """私聊会话对端（自发回显时为接收方）。"""
        if 0 < self.from_uin == self.self_uin:
            return self.to_uin
        return self.from_uin


def parse_push(body: bytes, self_uin: int = 0) -> list[MsgContext]:
    """解析 ``trpc.msg.olpush.OlPushService.MsgPush`` 包体。"""
    contexts: list[MsgContext] = []
    for message in pb_list(body, 1) or []:
        try:
            ctx = _parse_message(message, self_uin)
        except (ValueError, IndexError) as exc:
            log.debug('MsgPush 单条消息解析失败: %s', exc)
            continue
        if ctx is not None:
            contexts.append(ctx)
    return contexts


def _parse_message(message: bytes, self_uin: int) -> MsgContext | None:
    response_head = pb_bytes(message, 1)
    content_head = pb_bytes(message, 2)
    message_body = pb_bytes(message, 3)
    if not content_head:
        return None
    ctx = MsgContext(
        msg_type=pb_int(content_head, 1),
        sub_type=pb_int(content_head, 2),
        c2c_cmd=pb_int(content_head, 3),
        msg_id=pb_int(content_head, 4),
        sequence=pb_int(content_head, 5),
        timestamp=pb_int(content_head, 6),
        nt_msg_seq=pb_int(content_head, 11),
        self_uin=self_uin,
        raw_pb=message,
    )
    ctx.from_uin = pb_int(response_head, 1)
    ctx.from_uid = pb_str(response_head, 2)
    ctx.to_uin = pb_int(response_head, 5)
    grp = pb_bytes(response_head, 8)  # ResponseHead.grp = field 8
    if grp:
        ctx.group_uin = pb_int(grp, 1)
        ctx.member_name = pb_str(grp, 2)
        ctx.member_card = pb_str(grp, 4)   # memberCard = field 4
        ctx.group_name = pb_str(grp, 7)    # groupName = field 7
    ctx.body = message_body
    return ctx


# 元素解码


def decode_elements(body: bytes) -> list[dict[str, Any]]:
    """把 MessageBody 解码为内部元素列表（供 OneBot 段转换）。"""
    elements: list[dict[str, Any]] = []
    if not body:
        return elements
    rich_text = pb_bytes(body, 1)
    msg_content = pb_bytes(body, 2)
    if rich_text:
        for elem in pb_list(rich_text, 2):
            try:
                _decode_elem(elem, elements)
            except (ValueError, IndexError) as exc:
                log.debug('元素解码失败（已跳过）: %s', exc)
        _decode_ptt(rich_text, elements)
        _decode_not_online_file(rich_text, elements)
    if msg_content:
        try:
            _decode_msg_content(msg_content, elements)
        except (ValueError, IndexError) as exc:
            # 脏消息/非常规元素（如闪照、二进制垃圾）不应中断整个红包派发
            log.debug('msg_content 解码失败（已跳过）: %s', exc)
    return elements


def _decode_elem(elem: bytes, out: list[dict[str, Any]]) -> None:
    text = pb_bytes(elem, 1)
    face = pb_bytes(elem, 2)
    not_online_image = pb_bytes(elem, 4)
    custom_face = pb_bytes(elem, 8)
    market_face = pb_bytes(elem, 6)
    rich_msg = pb_bytes(elem, 12)
    group_file = pb_bytes(elem, 13)
    light_app = pb_bytes(elem, 51)
    common_elem = pb_bytes(elem, 53)
    src_msg = pb_bytes(elem, 45)
    video_file = pb_bytes(elem, 19)

    if src_msg:
        seqs = pb_int_list(src_msg, 1)
        if seqs:
            out.append({'type': 'reply', 'seq': seqs[0], 'sender_uin': pb_int(src_msg, 2)})
    if text:
        content = pb_str(text, 1)
        attr6 = pb_bytes(text, 3)          # attr6Buf = field 3
        mention = _decode_mention(pb_bytes(text, 12))  # pbReserve = field 12
        is_at = (attr6 and len(attr6) > 11) or (mention and mention.get('type') in (1, 2))
        if is_at:
            target = 0
            if attr6 and len(attr6) > 11:
                target = int.from_bytes(attr6[7:11], 'big')
            if not target and mention:
                target = mention.get('uin', 0)
            out.append({'type': 'at', 'qq': target, 'text': content})
        elif content:
            out.append({'type': 'text', 'text': content})
    if face:
        index = pb_int(face, 1)
        if index >= 0:
            out.append({'type': 'face', 'id': index})
    if market_face and len(pb_bytes(market_face, 7)) == 16:
        out.append({
            'type': 'mface',
            'text': pb_str(market_face, 4),
            'emoji_id': pb_bytes(market_face, 7).hex(),
            'emoji_package_id': pb_int(market_face, 8),
            'emoji_key': pb_str(market_face, 10),
        })
    if not_online_image:
        md5 = pb_bytes(not_online_image, 7)
        if len(md5) == 16:
            md5_hex = md5.hex().upper()
            orig_url = pb_str(not_online_image, 15)
            out.append({
                'type': 'image',
                'url': _image_url(orig_url) or (f'http://gchat.qpic.cn/gchatpic_new/0/0-0-{md5_hex}/0'
                                                if md5_hex else ''),
                'file': pb_str(not_online_image, 1) or md5_hex,
                'file_size': pb_int(not_online_image, 2),
                'width': pb_int(not_online_image, 9),
                'height': pb_int(not_online_image, 8),
            })
    if custom_face:
        md5 = pb_bytes(custom_face, 13)
        if len(md5) == 16:
            md5_hex = md5.hex().upper()
            orig_url = pb_str(custom_face, 16)
            out.append({
                'type': 'image',
                'url': _image_url(orig_url) or (f'http://gchat.qpic.cn/gchatpic_new/0/0-0-{md5_hex}/0'
                                                if md5_hex else ''),
                'file': pb_str(custom_face, 2) or md5_hex,
                'file_size': pb_int(custom_face, 25),
                'width': pb_int(custom_face, 22),
                'height': pb_int(custom_face, 23),
            })
    if video_file:
        out.append({
            'type': 'video',
            'file': pb_str(video_file, 3),
            'file_id': pb_str(video_file, 1),
            'file_size': pb_int(video_file, 6),
            'duration': pb_int(video_file, 5),
            'width': pb_int(video_file, 7),
            'height': pb_int(video_file, 8),
        })
    if group_file:
        out.append({
            'type': 'file',
            'file_id': pb_str(group_file, 3),
            'name': pb_str(group_file, 1),
            'size': pb_int(group_file, 2),
        })
    if rich_msg:
        service_id = pb_int(rich_msg, 2)
        template = pb_bytes(rich_msg, 1)
        if template and template[0] in (0, 1):
            template = template[1:]
        out.append({'type': 'json' if service_id == 1 else 'xml',
                    'data': template.decode('utf-8', 'replace')})
    if light_app:
        payload = pb_bytes(light_app, 1)
        if payload and payload[0] in (0, 1):
            payload = payload[1:]
        out.append({'type': 'json', 'data': payload.decode('utf-8', 'replace')})
    if common_elem:
        service_type = pb_int(common_elem, 1)
        business_type = pb_int(common_elem, 3)
        pb_elem = pb_bytes(common_elem, 2)
        if service_type == 2:
            out.append({'type': 'poke', 'sub_type': business_type})
        elif service_type == 33 and pb_elem:
            face_id = pb_int(pb_elem, 1)  # QSmallFaceExtra.faceId = field 1
            if face_id >= 0:
                out.append({'type': 'face', 'id': face_id})
    wallet = pb_bytes(elem, 24)  # WalletElem / 红包元素
    if wallet:
        packet = _decode_wallet(wallet)
        if packet:
            packet['raw_wallet'] = wallet.hex()
            out.append(packet)


def _wallet_fields(data: bytes, offset: int = 0, end: int | None = None):
    """钱包元素的宽松字段迭代：上游截断时仍能提取前段字段。"""
    if end is None:
        end = len(data)
    while offset < end:
        try:
            key, offset = read_varint(data, offset, end)
        except Exception:  # noqa: BLE001
            return
        num, wire = key >> 3, key & 7
        if wire == 0:
            try:
                value, offset = read_varint(data, offset, end)
            except Exception:  # noqa: BLE001
                return
            yield num, value
        elif wire == 2:
            try:
                length, offset = read_varint(data, offset, end)
            except Exception:  # noqa: BLE001
                return
            if offset + length > end:
                length = end - offset
            yield num, data[offset:offset + length]
            offset += length
        elif wire == 1:
            if offset + 8 > end:
                return
            yield num, data[offset:offset + 8]
            offset += 8
        elif wire == 5:
            if offset + 4 > end:
                return
            yield num, data[offset:offset + 4]
            offset += 4
        else:
            return


def _wallet_get(data: bytes, number: int):
    for num, value in _wallet_fields(data):
        if num == number:
            return value
    return None


def _wallet_str(data: bytes, number: int) -> str:
    value = _wallet_get(data, number)
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value or '')


def _wallet_int(data: bytes, number: int, default: int = 0) -> int:
    value = _wallet_get(data, number)
    if isinstance(value, bytes):
        try:
            return int.from_bytes(value, 'little')
        except Exception:  # noqa: BLE001
            return default
    if isinstance(value, int):
        return value
    return default


def _decode_wallet(wallet: bytes) -> dict[str, Any] | None:
    """WalletElem（Elem.f24）：f1=WalletItem{f3=红包详情, f9=billNo, f10=key}。"""
    try:
        item = _wallet_get(wallet, 1)
        if not isinstance(item, bytes) or not item:
            return None
        bill_no = _wallet_str(item, 9).strip()
        detail = _wallet_get(item, 3)
        detail = detail if isinstance(detail, bytes) else b''
        url = _wallet_str(detail, 14)
        if not bill_no:
            match = re.search(r'(?:^|[?&])id=(\d{16,40})', url)
            if match:
                bill_no = match.group(1)
        if not bill_no or not bill_no.isdigit():
            return None
        return {
            'type': 'red_packet',
            'bill_no': bill_no,
            'red_packet_type': _wallet_int(detail, 2, -1),
            'wishing': _wallet_str(detail, 3) or _wallet_str(detail, 5),
            'tip': _wallet_str(detail, 4),
            'url': url,
            'key': _wallet_str(item, 10),
        }
    except Exception:  # noqa: BLE001 - 红包元素解析失败不影响消息本身
        return None


def _decode_mention(pb_reserve: bytes) -> dict[str, Any] | None:
    """MentionExtra: type=3 uin=4 field5=5 uid=9。"""
    if not pb_reserve:
        return None
    try:
        return {
            'type': pb_int(pb_reserve, 3),
            'uin': pb_int(pb_reserve, 4),
            'uid': pb_str(pb_reserve, 9),
        }
    except (ValueError, IndexError):
        return None


def _decode_ptt(rich_text: bytes, out: list[dict[str, Any]]) -> None:
    for ptt in pb_list(rich_text, 4):
        file_uuid = pb_bytes(ptt, 3)
        out.append({
            'type': 'record',
            'file': pb_str(ptt, 5) or file_uuid.decode('utf-8', 'replace'),
            'file_id': pb_str(ptt, 10) or pb_str(ptt, 14),
            'file_size': pb_int(ptt, 6),
            'duration': pb_int(ptt, 19),   # time = field 19
            'voice_format': pb_int(ptt, 29),
            'md5': pb_bytes(ptt, 4).hex(),
        })


def _decode_not_online_file(rich_text: bytes, out: list[dict[str, Any]]) -> None:
    for file_ in pb_list(rich_text, 3):
        out.append({
            'type': 'file',
            'file_id': pb_str(file_, 3),   # fileUuid = field 3
            'name': pb_str(file_, 5),      # fileName = field 5
            'size': pb_int(file_, 6),      # fileSize = field 6
            'md5': pb_bytes(file_, 4).hex(),
            'file_hash': pb_str(file_, 57),
        })


def _decode_msg_content(msg_content: bytes, out: list[dict[str, Any]]) -> None:
    """msgContent = FileExtra{ f1=file(NotOnlineFile) }。"""
    file_ = pb_bytes(msg_content, 1)
    if not file_:
        return
    file_uuid = pb_str(file_, 3)
    if not file_uuid:
        return
    out.append({
        'type': 'file',
        'file_id': file_uuid,
        'name': pb_str(file_, 5),
        'size': pb_int(file_, 6),
        'md5': pb_bytes(file_, 4).hex(),
        'file_hash': pb_str(file_, 57),
    })


def _image_url(orig_url: str) -> str:
    """与 SnowLuma makeImageUrl 对齐。"""
    if not orig_url:
        return ''
    if orig_url.startswith('http'):
        return orig_url
    if not orig_url.startswith('/'):
        return ''
    if 'rkey' in orig_url or 'fileid' in orig_url:
        return 'https://multimedia.nt.qq.com.cn' + orig_url
    return 'http://gchat.qpic.cn' + orig_url
