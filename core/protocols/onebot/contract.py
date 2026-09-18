"""OneBot 内部契约。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class Channel(StrEnum):
    """框架支持的四种接入渠道。"""

    EMBEDDED = 'embedded'
    INJECTED = 'injected'
    ONEBOT = 'onebot'
    LAGRANGE = 'lagrange'


class EventKind(StrEnum):
    MESSAGE = 'message'
    MESSAGE_SENT = 'message_sent'
    NOTICE = 'notice'
    REQUEST = 'request'
    META = 'meta_event'


class MessageKind(StrEnum):
    GROUP = 'group'
    PRIVATE = 'private'


# 仅在入口适配时读取一次别名；内部事件对象不再以别名互相兜底。
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    'post_type': ('postType',),
    'self_id': ('selfId', 'selfUin'),
    'event_type': ('eventType',),
    'message_type': ('messageType',),
    'sub_type': ('subType',),
    'message_id': ('messageId', 'msg_id', 'msgId'),
    'message_seq': ('messageSeq', 'msgSeq'),
    'real_id': ('realId',),
    'real_seq': ('realSeq',),
    'user_id': ('userId',),
    'group_id': ('groupId',),
    'group_name': ('groupName',),
    'target_id': ('targetId', 'targetUin'),
    'raw_message': ('rawMessage',),
    'message_format': ('messageFormat',),
    'message_sent_type': ('messageSentType',),
    'notice_type': ('noticeType',),
    'request_type': ('requestType',),
    'meta_event_type': ('metaEventType',),
}

_IDENTIFIER_FIELDS = frozenset({
    'self_id', 'message_id', 'message_seq', 'real_id', 'real_seq',
    'user_id', 'group_id', 'operator_id', 'target_id',
})


def _missing_field(value: Any, canonical: str = '') -> bool:
    """判断入口字段是否实际缺失；QQ 身份字段的 0 只是占位值。"""
    if value in (None, ''):
        return True
    if canonical in _IDENTIFIER_FIELDS and value == 0:
        return True
    if canonical in _IDENTIFIER_FIELDS and isinstance(value, str) and value.strip() == '0':
        return True
    return False


def first_field(data: dict[str, Any], canonical: str, *aliases: str) -> Any:
    """读取一个明确的规范字段，不做递归或模糊搜索。"""

    value = data.get(canonical)
    if not _missing_field(value, canonical):
        return value
    for alias in aliases:
        value = data.get(alias)
        if not _missing_field(value, canonical):
            return value
    return value


def copy_canonical_fields(data: dict[str, Any]) -> dict[str, Any]:
    """将入口别名复制为规范字段。"""

    normalized = dict(data)
    for canonical, aliases in FIELD_ALIASES.items():
        value = first_field(normalized, canonical, *aliases)
        if not _missing_field(value, canonical):
            normalized[canonical] = value
    return normalized


def normalize_event_kind(value: Any) -> str:
    text = str(value or '').strip().lower().replace('-', '_')
    if text in {'meta', 'metaevent'}:
        return EventKind.META
    if text in {'message_sent', 'message_sent_event'}:
        return EventKind.MESSAGE_SENT
    return text


def normalize_message_kind(value: Any, *, default: str = MessageKind.PRIVATE) -> str:
    text = str(value or '').strip().lower()
    if text in {'friend', 'user', 'c2c', 'dm', 'private', 'direct'}:
        return MessageKind.PRIVATE
    if text in {'group', '群', 'group_chat'}:
        return MessageKind.GROUP
    # OneBot v11 的 message_type 只有 group/private；未知来源字段不能
    return default


def normalize_int(value: Any, default: int = 0) -> int:
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_role(value: Any) -> str:
    text = str(value or '').strip().lower()
    if text in {'owner', 'groupowner', 'group_owner', '群主', '3'}:
        return 'owner'
    if text in {'admin', 'administrator', 'groupadmin', 'group_admin', '管理员', '2'}:
        return 'admin'
    return 'member'


def event_ordering_key(event: Any) -> str:
    """返回严格基于规范字段的会话排序键。"""

    self_id = str(getattr(event, 'self_id', '') or '')
    post_type = str(getattr(event, 'post_type', '') or '')
    if post_type in {EventKind.MESSAGE, EventKind.MESSAGE_SENT}:
        if str(getattr(event, 'message_type', '') or '') == MessageKind.GROUP:
            conversation = str(getattr(event, 'group_id', '') or '')
        else:
            conversation = str(
                getattr(event, 'target_id', None)
                or getattr(event, 'user_id', '')
                or ''
            )
    elif post_type == EventKind.NOTICE:
        conversation = str(
            getattr(event, 'group_id', None)
            or getattr(event, 'user_id', None)
            or getattr(event, 'operator_id', '')
            or 'global'
        )
    elif post_type == EventKind.REQUEST:
        conversation = str(
            getattr(event, 'group_id', None)
            or getattr(event, 'user_id', '')
            or 'global'
        )
    else:
        conversation = 'global'
    return f'{self_id}:{post_type}:{conversation}'


def event_deduplication_key(event: Any) -> tuple[str, ...] | None:
    """生成跨渠道去重键；消息和带 bill_no 的红包通知都去重。"""

    post_type = str(getattr(event, 'post_type', '') or '')
    if post_type == EventKind.NOTICE and str(getattr(event, 'notice_type', '') or '') == 'red_packet':
        extra = getattr(event, 'extra', {})
        packet = extra.get('red_packet') if isinstance(extra, dict) else None
        bill_no = packet.get('bill_no') if isinstance(packet, dict) else ''
        if not bill_no:
            return None
        return (
            str(getattr(event, 'self_id', '') or ''),
            'notice.red_packet',
            str(bill_no),
        )
    if post_type not in {EventKind.MESSAGE, EventKind.MESSAGE_SENT}:
        return None
    message_id = getattr(event, 'message_id', 0)
    if message_id in (None, '', 0, '0'):
        return None
    return (
        str(getattr(event, 'self_id', '') or ''),
        post_type,
        str(getattr(event, 'message_type', '') or ''),
        str(getattr(event, 'group_id', '') or ''),
        str(getattr(event, 'user_id', '') or ''),
        str(message_id),
    )


__all__ = [
    'Channel',
    'EventKind',
    'MessageKind',
    'FIELD_ALIASES',
    'copy_canonical_fields',
    'event_deduplication_key',
    'event_ordering_key',
    'normalize_event_kind',
    'normalize_int',
    'normalize_message_kind',
    'normalize_role',
]
