"""OneBot 各传输方式共用的内联键盘提取工具。"""

from __future__ import annotations

import re
from typing import Any

GROUP_MESSAGE_COMMAND = 'trpc.msg.register_proxy.RegisterProxy.SsoGetGroupMsg'
_HEX_PATTERN = re.compile(r'^(?:[0-9a-fA-F]{2})+$')


def _encode_varint(value: int) -> bytes:
    value = int(value)
    if value < 0:
        raise ValueError('protobuf 变长整数不能为负数')
    result = bytearray()
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _varint_field(tag: int, value: int) -> bytes:
    return _encode_varint(tag << 3) + _encode_varint(value)


def _bytes_field(tag: int, value: bytes) -> bytes:
    return _encode_varint((tag << 3) | 2) + _encode_varint(len(value)) + value


def build_group_message_request(group_id: str | int, real_seq: str | int) -> str:
    """构建 Elaina 使用的 SsoGetGroupMsg protobuf 请求。"""
    group = int(group_id)
    sequence = int(real_seq)
    message_range = b''.join((
        _varint_field(1, group),
        _varint_field(2, sequence),
        _varint_field(3, sequence),
    ))
    return (_bytes_field(1, message_range) + _varint_field(2, 1)).hex()


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(10):
        if offset >= len(data):
            raise ValueError('protobuf 变长整数被截断')
        current = data[offset]
        offset += 1
        value |= (current & 0x7f) << shift
        if not current & 0x80:
            return value, offset
        shift += 7
    raise ValueError('protobuf 变长整数过长')


def _parse_fields(data: bytes) -> list[tuple[int, int, Any]]:
    fields: list[tuple[int, int, Any]] = []
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        tag, wire_type = key >> 3, key & 7
        if tag <= 0:
            raise ValueError('无效的 protobuf 字段标记')
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            if offset + 8 > len(data):
                raise ValueError('protobuf fixed64 被截断')
            value = int.from_bytes(data[offset:offset + 8], 'little')
            offset += 8
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError('protobuf 字节字段被截断')
            value = data[offset:end]
            offset = end
        elif wire_type == 5:
            if offset + 4 > len(data):
                raise ValueError('protobuf fixed32 被截断')
            value = int.from_bytes(data[offset:offset + 4], 'little')
            offset += 4
        else:
            raise ValueError(f'不支持的 protobuf 线类型: {wire_type}')
        fields.append((tag, wire_type, value))
    return fields


def _text(value: bytes) -> str:
    try:
        return value.decode('utf-8')
    except UnicodeDecodeError:
        return ''


def _button_id(fields: list[tuple[int, int, Any]]) -> str:
    for tag, wire_type, value in fields:
        if tag != 1:
            continue
        if wire_type == 2:
            candidate = _text(value).strip()
            if candidate and not candidate.startswith('BOT1.0_'):
                return candidate
        elif wire_type in {0, 1, 5}:
            return str(value)
    return ''


def _find_button(data: bytes, depth: int = 0) -> tuple[str, str] | None:
    if depth > 32 or not data:
        return None
    try:
        fields = _parse_fields(data)
    except ValueError:
        return None

    local_button_id = _button_id(fields)
    for _tag, wire_type, value in fields:
        if wire_type != 2:
            continue
        callback_data = _text(value)
        if callback_data.startswith('BOT1.0_'):
            return local_button_id, callback_data

    for _tag, wire_type, value in fields:
        if wire_type != 2:
            continue
        found = _find_button(value, depth + 1)
        if found:
            button_id, callback_data = found
            return button_id or local_button_id, callback_data
    return None


def _hex_payload(value: Any) -> str:
    if isinstance(value, str):
        compact = ''.join(value.split())
        return compact if len(compact) > 10 and _HEX_PATTERN.fullmatch(compact) else ''
    if isinstance(value, dict):
        preferred = ('data', 'rsp', 'rspbuffer', 'rspBuffer', 'body', 'payload', 'buffer')
        for key in preferred:
            if key in value and (found := _hex_payload(value[key])):
                return found
        for item in value.values():
            if found := _hex_payload(item):
                return found
    if isinstance(value, (list, tuple)):
        for item in value:
            if found := _hex_payload(item):
                return found
    return ''


def extract_inline_keyboard_buttons(
    response: Any,
    *,
    bot_appid: str = '',
) -> list[dict[str, str]]:
    """提取 SsoGetGroupMsg 响应中嵌入的回调按钮。"""
    payload = _hex_payload(response)
    if not payload:
        return []
    try:
        found = _find_button(bytes.fromhex(payload))
    except ValueError:
        return []
    if not found:
        return []
    button_id, callback_data = found
    return [{
        'bot_appid': str(bot_appid or ''),
        'button_id': button_id or '1',
        'callback_data': callback_data,
    }]
