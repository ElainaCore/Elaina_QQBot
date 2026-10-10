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
    """从一层 protobuf 字段中取出按钮 ID。

    ``Button.id`` 在 QQNT 定义里是 STRING（wire type 2），因此只接受字段 1
    的字符串值。同一字段号在其它层级含义完全不同：``Elem.commonElem`` 的
    字段 1 是 ``serviceType``（变长整数，内联键盘为 46），把它当成按钮 ID
    会得到 ``button_id="46"``，QQ 会以原生错误 10022 拒绝点击。
    """
    for tag, wire_type, value in fields:
        if tag != 1 or wire_type != 2:
            continue
        candidate = _text(value).strip()
        # ButtonExtra/KeyboardData/Row 的 field 1 是嵌套 protobuf，
        # 不能把其二进制内容误当成按钮 ID。真实 ID 必须是可打印文本。
        if (
            candidate
            and not candidate.startswith('BOT1.0_')
            and candidate.isprintable()
            and len(candidate) <= 128
        ):
            return candidate
    return ''


def _collect_buttons(
    data: bytes,
    out: list[tuple[str, str]],
    seen: set[tuple[str, str]],
    depth: int = 0,
    inherited_button_id: str = '',
) -> None:
    """递归遍历 QQNT 消息 protobuf，收集全部内联键盘回调按钮。

    与 JS 侧 ``extractInlineKeyboardButtons`` 对齐：一条消息可携带多个按钮，
    不能只返回第一个。
    """
    if depth > 32 or not data:
        return
    try:
        fields = _parse_fields(data)
    except ValueError:
        return

    local_button_id = _button_id(fields)
    # callback_data 位于 action.data（Button 的更深层），而 action.permission
    # 等同一字段号在不同层级另有含义。只有 Button 一层的字段 1 是真正的
    # 按钮 ID，其余层级取不到 ID 时沿用最近一层已知的 ID，避免把 type、
    # serviceType 之类的数值误当成按钮 ID。
    if not local_button_id:
        local_button_id = inherited_button_id

    for _tag, wire_type, value in fields:
        if wire_type != 2:
            continue
        callback_data = _text(value)
        if not callback_data.startswith('BOT1.0_'):
            continue
        identity = (local_button_id or '1', callback_data)
        if identity not in seen:
            seen.add(identity)
            out.append(identity)

    for _tag, wire_type, value in fields:
        if wire_type != 2:
            continue
        _collect_buttons(value, out, seen, depth + 1, local_button_id)


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
    """提取 SsoGetGroupMsg 响应中嵌入的全部回调按钮。"""
    payload = _hex_payload(response)
    if not payload:
        return []
    found: list[tuple[str, str]] = []
    try:
        _collect_buttons(bytes.fromhex(payload), found, set())
    except ValueError:
        return []
    appid = str(bot_appid or '')
    return [
        {'bot_appid': appid, 'button_id': button_id or '1', 'callback_data': callback_data}
        for button_id, callback_data in found
    ]
