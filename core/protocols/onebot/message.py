"""所有传输方式共用的 OneBot 消息和动作规范化。"""

import json
import re
from typing import Any

from core.protocols.onebot.contract import normalize_message_kind

_CQ_PATTERN = re.compile(r'\[CQ:([^,\]]+)((?:,[^\]]*)?)\]')
_ACTION_SUFFIX = re.compile(r'_(?:async|rate_limited)$', re.IGNORECASE)
_SEND_ACTIONS = frozenset({'send_msg', 'send_group_msg', 'send_private_msg'})


def _cq_decode(value: str) -> str:
    return value.replace('&#44;', ',').replace('&#91;', '[').replace('&#93;', ']').replace('&amp;', '&')


def _cq_encode(value: Any) -> str:
    if isinstance(value, (dict, list, bool)):
        value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return str(value).replace('&', '&amp;').replace('[', '&#91;').replace(']', '&#93;').replace(',', '&#44;')


def _cq_encode_text(value: Any) -> str:
    return str(value).replace('&', '&amp;').replace('[', '&#91;').replace(']', '&#93;')


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def parse_cq_message(value: str) -> list[dict]:
    """将 CQ 字符串解析为 OneBot 消息段，并保留周围文本。"""
    segments: list[dict] = []
    offset = 0
    for match in _CQ_PATTERN.finditer(value):
        if match.start() > offset:
            segments.append({'type': 'text', 'data': {'text': _cq_decode(value[offset : match.start()])}})
        data = {}
        for item in match.group(2).lstrip(',').split(','):
            if not item:
                continue
            key, separator, raw = item.partition('=')
            data[key] = _cq_decode(raw if separator else '')
        segments.append({'type': match.group(1), 'data': data})
        offset = match.end()
    if offset < len(value):
        segments.append({'type': 'text', 'data': {'text': _cq_decode(value[offset:])}})
    return segments or [{'type': 'text', 'data': {'text': value}}]


def normalize_message(message: Any, *, auto_escape: bool = False) -> list[dict]:
    """返回四种渠道共用的标准 OneBot 数组消息。"""
    if isinstance(message, str):
        return [{'type': 'text', 'data': {'text': message}}] if auto_escape else parse_cq_message(message)
    if isinstance(message, dict):
        message = [message]
    if not isinstance(message, (list, tuple)):
        return []

    normalized = []
    for segment in message:
        if not isinstance(segment, dict):
            if segment is not None:
                normalized.append({'type': 'text', 'data': {'text': str(segment)}})
            continue
        segment_type = str(segment.get('type') or '').strip().lower()
        if not segment_type:
            continue
        if segment_type in {'voice', 'audio'}:
            segment_type = 'record'
        data = segment.get('data')
        if isinstance(data, dict):
            normalized_data = dict(data)
        elif data is None:
            normalized_data = {}
        else:
            # 少数协议端把 json/xml 的内容直接放在 data 字段；转换为
            normalized_data = {'data': data}
        if segment_type == 'text' and 'text' in normalized_data:
            normalized_data['text'] = str(normalized_data['text'])
        normalized.append({'type': segment_type, 'data': normalized_data})
    return normalized


def message_to_cq(message: Any) -> str:
    parts = []
    for segment in normalize_message(message):
        segment_type = segment['type']
        data = segment['data']
        if segment_type == 'text':
            parts.append(_cq_encode_text(data.get('text') or ''))
            continue
        fields = ','.join(f'{key}={encoded}' for key, value in data.items() if value is not None and (encoded := _cq_encode(value)))
        parts.append(f'[CQ:{segment_type}{"," if fields else ""}{fields}]')
    return ''.join(parts)


def normalize_action_request(action: str, params: dict | None) -> tuple[str, dict]:
    """在选择本机、WebSocket 或 HTTP 传输前规范化 API 调用。"""
    normalized_action = _ACTION_SUFFIX.sub('', str(action or '').strip())
    normalized_params = dict(params or {})
    if normalized_action in _SEND_ACTIONS and 'message' in normalized_params:
        normalized_params['message'] = normalize_message(
            normalized_params['message'],
            auto_escape=_as_bool(normalized_params.get('auto_escape')),
        )
    if normalized_action in {'send_group_msg', 'send_group_forward_msg'}:
        normalized_params['message_type'] = 'group'
    elif normalized_action in {'send_private_msg', 'send_private_forward_msg'}:
        normalized_params['message_type'] = 'private'
    elif normalized_action == 'send_msg':
        requested_type = normalized_params.get('message_type')
        if requested_type in (None, ''):
            requested_type = 'group' if normalized_params.get('group_id') is not None else 'private'
        message_type = normalize_message_kind(requested_type)
        normalized_params['message_type'] = message_type
    return normalized_action, normalized_params
