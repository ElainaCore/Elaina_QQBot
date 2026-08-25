"""内置 QQ 原始包的 Python 契约、PB 构造与响应解析。"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Any

from core.protocols.onebot.protocol import action_failed, normalize_action_response

_HEX = re.compile(r'^(?:[0-9a-fA-F]{2})+$')
_RESPONSE_KEYS = (
    'rspbuffer',
    'rspBuffer',
    'rsp',
    'data',
    'body',
    'payload',
    'buffer',
    'response',
)
MAX_PACKET_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PacketRequest:
    cmd: str
    data: bytes
    wait_response: bool = True

    def bridge_payload(self) -> dict[str, Any]:
        """仅在本机 JSON 控制桥上传输时对二进制做 Base64 编码。"""
        return {
            'cmd': self.cmd,
            'data_base64': base64.b64encode(self.data).decode('ascii'),
            'rsp': self.wait_response,
        }


def onebot_boolean(value: Any, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip().casefold() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def normalize_packet_request(params: dict[str, Any] | None) -> PacketRequest:
    params = params if isinstance(params, dict) else {}
    cmd = str(params.get('cmd') or '').strip()
    encoded = re.sub(r'\s+', '', str(params.get('data') or ''))
    if not cmd or not encoded or not _HEX.fullmatch(encoded):
        raise ValueError('发包参数 cmd/data 无效')
    data = bytes.fromhex(encoded)
    if len(data) > MAX_PACKET_BYTES:
        raise ValueError('原始数据包超过 32 MB 限制')
    return PacketRequest(cmd, data, onebot_boolean(params.get('rsp'), True))


def _encode_varint(value: int) -> bytes:
    remaining = int(value)
    if remaining < 0:
        remaining &= (1 << 64) - 1
    output = bytearray()
    while True:
        current = remaining & 0x7F
        remaining >>= 7
        if remaining:
            current |= 0x80
        output.append(current)
        if not remaining:
            return bytes(output)


def _varint_field(number: int, value: int) -> bytes:
    return _encode_varint(number << 3) + _encode_varint(value)


def _bytes_field(number: int, value: bytes) -> bytes:
    return _encode_varint((number << 3) | 2) + _encode_varint(len(value)) + value


def _string_field(number: int, value: str) -> bytes:
    return _bytes_field(number, str(value).encode())


def build_group_special_title_packet(group_id: Any, uid: Any, title: Any = '') -> PacketRequest:
    group = str(group_id or '').strip()
    member_uid = str(uid or '').strip()
    if not group.isdecimal() or not member_uid:
        raise ValueError('群号或成员 UID 无效')
    title = str(title or '')
    member = b''.join((
        _string_field(1, member_uid),
        _string_field(5, title),
        _varint_field(6, -1),
        _string_field(7, title),
    ))
    request = _varint_field(1, int(group)) + _bytes_field(3, member)
    body = b''.join((
        _varint_field(1, 0x8FC),
        _varint_field(2, 2),
        _bytes_field(4, request),
        _varint_field(12, 0),
    ))
    return PacketRequest('OidbSvcTrpcTcp.0x8FC_2', body, True)


def build_poke_packet(params: dict[str, Any] | None) -> PacketRequest:
    params = params if isinstance(params, dict) else {}
    target = str(params.get('target_id') or params.get('user_id') or '').strip()
    group = str(params.get('group_id') or '').strip()
    peer = group or str(params.get('user_id') or '').strip()
    if not target.isdecimal() or not peer.isdecimal():
        raise ValueError('戳一戳缺少有效的 user_id/group_id')
    inner = b''.join((
        _varint_field(1, int(target)),
        _varint_field(2 if group else 5, int(peer)),
        _varint_field(6, 0),
    ))
    body = b''.join((
        _varint_field(1, 0xED3),
        _varint_field(2, 1),
        _bytes_field(4, inner),
        _varint_field(12, 1),
    ))
    return PacketRequest('OidbSvcTrpcTcp.0xED3_1', body, True)


def _byte_sequence(value: Any) -> bytes | None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, list) and all(isinstance(item, int) and 0 <= item <= 255 for item in value):
        return bytes(value)
    if not isinstance(value, dict):
        return None
    if value.get('type') == 'Buffer':
        return _byte_sequence(value.get('data'))
    if value.get('encoding') == 'base64' and isinstance(value.get('data'), str):
        try:
            return base64.b64decode(value['data'], validate=True)
        except (binascii.Error, ValueError):
            raise ValueError('原始发包响应包含无效的 Base64 数据') from None
    numeric = []
    for index in range(len(value)):
        if str(index) not in value:
            break
        numeric.append(value[str(index)])
    return _byte_sequence(numeric) if numeric and len(numeric) == len(value) else None


def packet_response_bytes(value: Any, depth: int = 0) -> bytes:
    direct = _byte_sequence(value)
    if direct is not None:
        if not direct:
            raise ValueError('原始发包响应正文为空')
        if len(direct) > MAX_PACKET_BYTES:
            raise ValueError('原始发包响应超过 32 MB 限制')
        return direct
    if isinstance(value, str):
        encoded = value.strip().removeprefix('0x')
        if _HEX.fullmatch(encoded):
            return bytes.fromhex(encoded)
    if isinstance(value, dict) and depth < 4:
        for key in _RESPONSE_KEYS:
            if key not in value:
                continue
            try:
                return packet_response_bytes(value[key], depth + 1)
            except ValueError as error:
                if '正文为空' in str(error):
                    raise
    raise ValueError('原始发包未返回可识别的响应正文')


def normalize_packet_action_response(response: Any, *, wait_response: bool) -> dict[str, Any]:
    normalized = normalize_action_response(response, action='send_packet')
    if normalized['status'] == 'failed':
        return normalized
    if not wait_response:
        normalized['data'] = None
        return normalized
    try:
        normalized['data'] = packet_response_bytes(normalized.get('data')).hex()
    except ValueError as error:
        return action_failed(str(error), 1500)
    return normalized
