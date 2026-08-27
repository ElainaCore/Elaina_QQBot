"""内置 QQ 原始包的 Python 契约、PB 构造与响应解析。"""

from __future__ import annotations

import base64
import binascii
import json
import re
import secrets
import time
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


def _message_field(number: int, *values: bytes) -> bytes:
    return _bytes_field(number, b''.join(values))


def _oidb_packet(command: int, sub_command: int, body: bytes, *, reserved: bool = True) -> PacketRequest:
    packet = b''.join((
        _varint_field(1, command),
        _varint_field(2, sub_command),
        _bytes_field(4, body),
        _varint_field(12, int(reserved)),
    ))
    return PacketRequest(f'OidbSvcTrpcTcp.0x{command:X}_{sub_command}', packet, True)


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift < 70:
        current = data[offset]
        offset += 1
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value, offset
        shift += 7
    raise ValueError('PB varint 数据损坏')


def _protobuf_fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    fields: list[tuple[int, int, int | bytes]] = []
    offset = 0
    while offset < len(data):
        tag, offset = _decode_varint(data, offset)
        number, wire_type = tag >> 3, tag & 7
        if number <= 0:
            raise ValueError('PB 字段编号无效')
        if wire_type == 0:
            value, offset = _decode_varint(data, offset)
        elif wire_type == 1:
            if offset + 8 > len(data):
                raise ValueError('PB fixed64 数据损坏')
            value, offset = data[offset:offset + 8], offset + 8
        elif wire_type == 2:
            size, offset = _decode_varint(data, offset)
            if size < 0 or offset + size > len(data):
                raise ValueError('PB bytes 数据损坏')
            value, offset = data[offset:offset + size], offset + size
        elif wire_type == 5:
            if offset + 4 > len(data):
                raise ValueError('PB fixed32 数据损坏')
            value, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError(f'不支持的 PB wire type: {wire_type}')
        fields.append((number, wire_type, value))
    return fields


def _field_values(data: bytes, number: int, wire_type: int | None = None) -> list[int | bytes]:
    return [
        value
        for field_number, field_wire_type, value in _protobuf_fields(data)
        if field_number == number and (wire_type is None or wire_type == field_wire_type)
    ]


def _first_bytes(data: bytes, number: int, fallback: bytes = b'') -> bytes:
    values = _field_values(data, number, 2)
    return bytes(values[0]) if values else fallback


def _first_int(data: bytes, number: int, fallback: int = 0) -> int:
    values = _field_values(data, number, 0)
    return int(values[0]) if values else fallback


def _first_text(data: bytes, number: int, fallback: str = '') -> str:
    value = _first_bytes(data, number)
    return value.decode('utf-8', errors='replace') if value else fallback


def parse_oidb_response(data: bytes) -> bytes:
    error_code = _first_int(data, 3)
    if error_code:
        message = _first_text(data, 5) or f'OIDB 调用失败 ({error_code})'
        raise ValueError(message)
    return _first_bytes(data, 4)


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


def build_rkey_packet() -> PacketRequest:
    common = _varint_field(1, 1) + _varint_field(2, 202)
    scene = b''.join((
        _varint_field(101, 2),
        _varint_field(102, 1),
        _varint_field(200, 0),
    ))
    client = _varint_field(1, 2)
    request_head = b''.join((
        _bytes_field(1, common),
        _bytes_field(2, scene),
        _bytes_field(3, client),
    ))
    keys = b''.join(_varint_field(1, value) for value in (10, 20, 2))
    return _oidb_packet(0x9067, 202, _bytes_field(1, request_head) + _bytes_field(4, keys))


def parse_rkey_response(data: bytes) -> list[dict[str, Any]]:
    body = parse_oidb_response(data)
    container = _first_bytes(body, 4)
    result = []
    for item in _field_values(container, 1, 2):
        item = bytes(item)
        result.append({
            'rkey': _first_text(item, 1),
            'ttl': _first_int(item, 2),
            'time': _first_int(item, 4),
            'type': _first_int(item, 5),
        })
    return result


def build_group_todo_packet(group_id: Any, message_seq: Any, operation: str) -> PacketRequest:
    group = str(group_id or '').strip()
    sequence = str(message_seq or '').strip()
    sub_commands = {'set_group_todo': 1, 'complete_group_todo': 2, 'cancel_group_todo': 3}
    if not group.isdecimal() or not sequence.isdecimal() or operation not in sub_commands:
        raise ValueError('群待办缺少有效的 group_id/message_seq')
    body = _varint_field(1, int(group)) + _varint_field(2, int(sequence))
    return _oidb_packet(0xF90, sub_commands[operation], body)


def build_group_sign_packet(self_id: Any, group_id: Any) -> PacketRequest:
    self_uin = str(self_id or '').strip()
    group = str(group_id or '').strip()
    if not self_uin.isdecimal() or not group.isdecimal():
        raise ValueError('群签到缺少有效的 self_id/group_id')
    sign = b''.join((
        _string_field(1, self_uin),
        _string_field(2, group),
        _string_field(3, '9.0.90'),
    ))
    return _oidb_packet(0xEB7, 1, _bytes_field(2, sign), reserved=False)


def build_unidirectional_friend_packet(self_id: Any) -> PacketRequest:
    self_uin = str(self_id or '').strip()
    if not self_uin.isdecimal():
        raise ValueError('获取单向好友列表缺少有效的 self_id')
    request = json.dumps({
        'uint64_uin': self_uin,
        'uint64_top': 0,
        'uint32_req_num': 99,
        'bytes_cookies': '',
    }, separators=(',', ':'))
    data = _varint_field(2, 2) + _string_field(3, request)
    return PacketRequest('MQUpdateSvc_com_qq_ti.web.OidbSvc.0xe17_0', data, True)


def parse_unidirectional_friend_response(data: bytes) -> list[dict[str, Any]]:
    raw = _first_text(data, 4)
    if not raw:
        raise ValueError('单向好友响应缺少数据')
    payload = json.loads(raw)
    blocks = payload.get('rpt_block_list') or []
    result = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        try:
            nick = base64.b64decode(str(block.get('bytes_nick') or '')).decode('utf-8', errors='replace')
            source = base64.b64decode(str(block.get('bytes_source') or '')).decode('utf-8', errors='replace')
        except (binascii.Error, ValueError):
            nick, source = '', ''
        result.append({
            'uin': int(block.get('uint64_uin') or 0),
            'uid': str(block.get('str_uid') or ''),
            'nick_name': nick,
            'age': int(block.get('uint32_age') or 0),
            'source': source,
        })
    return result


def build_ai_characters_packet(group_id: Any, chat_type: Any = 1) -> PacketRequest:
    group = str(group_id or '').strip()
    if not group.isdecimal():
        raise ValueError('AI 角色请求缺少有效的 group_id')
    body = _varint_field(1, int(group)) + _varint_field(2, int(chat_type or 1))
    return _oidb_packet(0x929D, 0, body)


def parse_ai_characters_response(data: bytes) -> list[dict[str, Any]]:
    body = parse_oidb_response(data)
    result = []
    for category in _field_values(body, 1, 2):
        category = bytes(category)
        voices = []
        for voice in _field_values(category, 2, 2):
            voice = bytes(voice)
            voices.append({
                'character_id': _first_text(voice, 1),
                'character_name': _first_text(voice, 2),
                'preview_url': _first_text(voice, 3),
            })
        result.append({'type': _first_text(category, 1), 'characters': voices})
    return result


def build_ai_voice_packet(group_id: Any, character: Any, text: Any, *, session_id: int | None = None) -> PacketRequest:
    group = str(group_id or '').strip()
    voice_id = str(character or '').strip()
    content = str(text or '').strip()
    if not group.isdecimal() or not voice_id or not content:
        raise ValueError('AI 语音缺少有效的 group_id/character/text')
    session = int(session_id if session_id is not None else secrets.randbits(32))
    body = b''.join((
        _varint_field(1, int(group)),
        _string_field(2, voice_id),
        _string_field(3, content),
        _varint_field(4, 1),
        _message_field(5, _varint_field(1, session)),
    ))
    return _oidb_packet(0x929B, 0, body)


def parse_ai_voice_index(data: bytes) -> bytes | None:
    body = parse_oidb_response(data)
    msg_info = _first_bytes(body, 4)
    msg_body = _first_bytes(msg_info, 1)
    return _first_bytes(msg_body, 1) or None


def build_group_ptt_url_packet(group_id: Any, index: bytes) -> PacketRequest:
    group = str(group_id or '').strip()
    if not group.isdecimal() or not index:
        raise ValueError('AI 语音下载缺少有效的 group_id/index')
    common = _varint_field(1, 4) + _varint_field(2, 200)
    scene = b''.join((
        _varint_field(101, 1),
        _varint_field(102, 3),
        _varint_field(200, 2),
        _message_field(202, _varint_field(1, int(group))),
    ))
    request_head = b''.join((
        _bytes_field(1, common),
        _bytes_field(2, scene),
        _message_field(3, _varint_field(1, 2)),
    ))
    # NapCat sends the PTT index through DownloadExt.video (field 2),
    # despite consuming the response as a PTT URL.
    video = _varint_field(1, 0) + _varint_field(2, 0)
    download = _bytes_field(1, index) + _message_field(2, video)
    body = _bytes_field(1, request_head) + _bytes_field(3, download)
    return _oidb_packet(0x126E, 200, body)


def parse_group_ptt_url_response(data: bytes) -> str:
    body = parse_oidb_response(data)
    download = _first_bytes(body, 3)
    rkey = _first_text(download, 1)
    info = _first_bytes(download, 3)
    domain, url_path = _first_text(info, 1), _first_text(info, 2)
    if not domain or not url_path:
        raise ValueError('AI 语音下载响应缺少 URL')
    return f'https://{domain}{url_path}{rkey}'


_MINI_APP_TEMPLATES = {
    'bili': {
        'sdkId': 'V1_PC_MINISDK_99.99.99_1_APP_A', 'appId': '1109937557', 'scene': 1,
        'templateType': 1, 'businessType': 0, 'verType': 3, 'shareType': 0,
        'versionId': 'cfc5f7b05b44b5956502edaecf9d2240', 'withShareTicket': 0,
        'iconUrl': 'https://miniapp.gtimg.cn/public/appicon/51f90239b78a2e4994c11215f4c4ba15_200.jpg',
    },
    'weibo': {
        'sdkId': 'V1_PC_MINISDK_99.99.99_1_APP_A', 'appId': '1109224783', 'scene': 1,
        'templateType': 1, 'businessType': 0, 'verType': 3, 'shareType': 0,
        'versionId': 'e482a3cc4e574d9b772e96ba6eec9ba2', 'withShareTicket': 0,
        'iconUrl': 'https://miniapp.gtimg.cn/public/appicon/35bbb44dc68e65194cfacfb206b8f1f7_200.jpg',
    },
}


def build_mini_app_packet(params: dict[str, Any] | None) -> PacketRequest:
    params = dict(params or {})
    if params.get('type'):
        template = _MINI_APP_TEMPLATES.get(str(params['type']).casefold())
        if template is None:
            raise ValueError('未知的小程序模板类型')
        params = {**template, **params}
    required = ('title', 'desc', 'picUrl', 'jumpUrl', 'appId', 'iconUrl', 'versionId')
    if any(not str(params.get(key) or '').strip() for key in required):
        raise ValueError('小程序 Ark 参数不完整')
    ext_info = _bytes_field(2, b'')
    template = _string_field(1, '') + _string_field(2, '')
    body = b''.join((
        _bytes_field(1, ext_info),
        _string_field(2, params['appId']),
        _string_field(3, params['title']),
        _string_field(4, params['desc']),
        _varint_field(5, int(time.time() * 1000)),
        _varint_field(6, int(params.get('scene') or 0)),
        _varint_field(7, int(params.get('templateType') or 0)),
        _varint_field(8, int(params.get('businessType') or 0)),
        _string_field(9, params['picUrl']),
        _string_field(10, ''),
        _string_field(11, params['jumpUrl']),
        _string_field(12, params['iconUrl']),
        _varint_field(13, int(params.get('verType') or 0)),
        _varint_field(14, int(params.get('shareType') or 0)),
        _string_field(15, params['versionId']),
        _varint_field(16, int(params.get('withShareTicket') or 0)),
        _string_field(17, params.get('webUrl') or ''),
        _bytes_field(18, b''),
        _bytes_field(19, template),
        _string_field(20, ''),
    ))
    request = _string_field(2, params.get('sdkId') or 'V1_PC_MINISDK_99.99.99_1_APP_A') + _bytes_field(4, body)
    return PacketRequest('LightAppSvc.mini_app_share.AdaptShareInfo', request, True)


def parse_mini_app_response(data: bytes, *, raw: bool = False) -> dict[str, Any]:
    content = _first_bytes(data, 4)
    raw_data = json.loads(_first_text(content, 2))
    if raw:
        return {'data': raw_data}
    return {'data': {
        'ver': raw_data.get('ver'),
        'prompt': raw_data.get('prompt'),
        'config': raw_data.get('config'),
        'app': raw_data.get('appName'),
        'view': raw_data.get('appView'),
        'meta': raw_data.get('metaData'),
        'miniappShareOrigin': 3,
        'miniappOpenRefer': '10002',
    }}


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
