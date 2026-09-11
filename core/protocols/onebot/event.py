"""OneBot v11 事件模型与跨连接字段规范化。"""

import time
from typing import Any

from core.protocols.onebot.contract import (
    FIELD_ALIASES,
    EventKind,
    MessageKind,
    copy_canonical_fields,
    normalize_event_kind,
    normalize_int,
    normalize_message_kind,
    normalize_role,
)
from core.protocols.onebot.message import message_to_cq, normalize_message

# 兼容旧插件从 event.py 导入枚举；新代码应从 contract.py 导入。
PostType = EventKind
MsgType = MessageKind


def _number(value: Any, default: int = 0) -> int:
    return normalize_int(value, default)


def _role(value: Any) -> str:
    return normalize_role(value)


class OneBotEvent:
    __slots__ = ('raw_data', 'time', 'self_id', 'post_type', 'event_type', 'source', 'extra', '_api')

    def __init__(self, data: dict):
        self.raw_data = dict(data)
        self.time = _number(data.get('time'), int(time.time()))
        self.self_id = str(data.get('self_id', '') or '')
        self.post_type = str(data.get('post_type', '') or '')
        self.event_type = str(data.get('event_type') or self.post_type)
        self.source = str(data.get('_source') or '')
        self.extra = data.get('_extra') if isinstance(data.get('_extra'), dict) else {}
        self._api = None

    def __getattr__(self, name: str):
        extra = object.__getattribute__(self, 'extra')
        if name in extra:
            return extra[name]
        raise AttributeError(name)

    def to_dict(self) -> dict:
        return dict(self.raw_data)

    @property
    def channel(self) -> str:
        """事件来源渠道；不影响 OneBot 字段和插件匹配。"""
        return self.source

    @property
    def content(self) -> str:
        return ''


class MessageEvent(OneBotEvent):
    __slots__ = ('message_type', 'sub_type', 'message_id', 'message_seq', 'real_id', 'real_seq', 'user_id', 'group_id', 'group_name', 'temp_source', 'target_id', 'message', 'raw_message', 'message_format', 'message_sent_type', 'sender', 'font', '_content')

    def __init__(self, data: dict):
        super().__init__(data)
        self.message_type = str(data.get('message_type') or MessageKind.PRIVATE)
        self.sub_type = str(data.get('sub_type') or '')
        self.message_id = _number(data.get('message_id'), 0)
        self.message_seq = _number(data.get('message_seq', data.get('real_seq')), 0)
        self.real_id = _number(data.get('real_id'), self.message_id)
        self.real_seq = _number(data.get('real_seq'), self.message_seq)
        self.user_id = _number(data.get('user_id'), 0)
        self.group_id = _number(data.get('group_id'), 0) or None
        self.group_name = str(data.get('group_name') or '')
        self.temp_source = _number(data.get('temp_source'), 0)
        self.target_id = _number(data.get('target_id'), 0) or None
        self.message = normalize_message(data.get('message', []))
        self.raw_message = str(data.get('raw_message') or message_to_cq(self.message))
        self.message_format = str(data.get('message_format') or 'array')
        self.message_sent_type = str(data.get('message_sent_type') or '')
        self.sender = data.get('sender', {}) if isinstance(data.get('sender', {}), dict) else {}
        self.font = _number(data.get('font'), 14)
        self._content = None

    @property
    def is_group(self) -> bool:
        return self.message_type == MessageKind.GROUP

    @property
    def is_private(self) -> bool:
        return self.message_type == MessageKind.PRIVATE

    @property
    def is_sent(self) -> bool:
        return bool(self.message_sent_type) or self.raw_data.get('event_type') == 'message_sent'

    @property
    def sender_nickname(self) -> str:
        return str(self.sender.get('nickname', '') or '')

    @property
    def sender_card(self) -> str:
        return str(self.sender.get('card', '') or '')

    @property
    def member_role(self) -> str:
        """Compatibility alias used by existing plugins for group messages."""
        if not self.is_group:
            return ''
        return _role(self.sender.get('role') or self.sender.get('permission'))

    @property
    def sender_role(self) -> str:
        """Compatibility alias used by older plugin permission checks."""
        return self.member_role

    @property
    def content(self) -> str:
        if self._content is None:
            self._content = ''.join(str(seg.get('data', {}).get('text', '') or '') for seg in self.message if isinstance(seg, dict) and seg.get('type') == 'text').strip()
        return self._content

    async def reply(self, message, **kwargs):
        if self._api is None:
            return None
        if isinstance(message, str):
            message = [{'type': 'text', 'data': {'text': message}}]
        if self.is_group:
            return await self._api.send_group_msg(self.group_id, message, **kwargs, self_id=str(self.self_id))
        target_id = self.target_id if self.is_sent and self.target_id else self.user_id
        return await self._api.send_private_msg(target_id, message, **kwargs, self_id=str(self.self_id))

    async def reply_text(self, text: str, **kwargs):
        return await self.reply(text, **kwargs)

    async def reply_image(self, file: str, **kwargs):
        return await self.reply([{'type': 'image', 'data': {'file': file}}], **kwargs)

    async def call_api(self, action: str, params: dict | None = None):
        if self._api is None:
            return None
        return await self._api.call_api(action, params, self_id=str(self.self_id))


class NoticeEvent(OneBotEvent):
    __slots__ = ('notice_type', 'sub_type', 'user_id', 'group_id', 'operator_id')

    def __init__(self, data: dict):
        super().__init__(data)
        self.notice_type = str(data.get('notice_type') or '')
        self.sub_type = str(data.get('sub_type') or '')
        self.user_id = _number(data.get('user_id'), 0)
        self.group_id = _number(data.get('group_id'), 0) or None
        self.operator_id = _number(data.get('operator_id'), 0)


class RequestEvent(OneBotEvent):
    __slots__ = ('request_type', 'sub_type', 'user_id', 'group_id', 'comment', 'flag', 'approve', 'reason')

    def __init__(self, data: dict):
        super().__init__(data)
        self.request_type = str(data.get('request_type') or '')
        self.sub_type = str(data.get('sub_type') or '')
        self.user_id = _number(data.get('user_id'), 0)
        self.group_id = _number(data.get('group_id'), 0) or None
        self.comment = str(data.get('comment') or '')
        self.flag = str(data.get('flag') or '')
        self.approve = data.get('approve')
        self.reason = str(data.get('reason') or '')


class MetaEvent(OneBotEvent):
    __slots__ = ('meta_event_type', 'status', 'interval')

    def __init__(self, data: dict):
        super().__init__(data)
        self.meta_event_type = str(data.get('meta_event_type') or '')
        self.status = data.get('status', {}) if isinstance(data.get('status', {}), dict) else {}
        self.interval = _number(data.get('interval'), 0)


def normalize_event(data: dict, default_self_id: str = '') -> dict | None:
    """将渠道边界数据收敛为固定的 OneBot v11 字段。"""
    if not isinstance(data, dict):
        return None
    normalized = copy_canonical_fields(data)
    post_type = str(normalize_event_kind(normalized.get('post_type')))
    if not post_type:
        return None
    normalized['post_type'] = post_type
    if default_self_id and not normalized.get('self_id'):
        normalized['self_id'] = str(default_self_id)
    normalized['self_id'] = str(normalized.get('self_id') or '')
    normalized['time'] = _number(normalized.get('time'), int(time.time()))
    normalized.setdefault('event_type', post_type)

    known_fields = {
        'time', 'self_id', 'post_type', 'event_type', '_source', '_extra',
        'message_type', 'sub_type', 'message_id', 'message_seq', 'real_id',
        'real_seq', 'user_id', 'group_id', 'group_name', 'temp_source',
        'target_id', 'message', 'raw_message', 'message_format',
        'message_sent_type', 'sender', 'font', 'notice_type', 'operator_id',
        'request_type', 'comment', 'flag', 'approve', 'reason',
        'meta_event_type', 'status', 'interval',
    }
    alias_fields = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
    extra = dict(normalized.get('_extra')) if isinstance(normalized.get('_extra'), dict) else {}
    extra.update({
        key: value for key, value in normalized.items()
        if key not in known_fields and key not in alias_fields and not key.startswith('_')
    })
    # 从这里开始只保留规范字段；原始别名和渠道扩展集中放进 extra，
    normalized = {
        key: value for key, value in normalized.items()
        if key in known_fields
    }
    normalized.update(extra)
    normalized['_extra'] = extra
    for identifier in ('user_id', 'group_id', 'operator_id', 'target_id'):
        if normalized.get(identifier) not in (None, ''):
            normalized[identifier] = _number(normalized[identifier], 0)

    if post_type in {EventKind.MESSAGE, EventKind.MESSAGE_SENT}:
        if post_type == EventKind.MESSAGE_SENT:
            normalized.setdefault('message_sent_type', 'self')
        raw = normalized.get('raw_message')
        source = normalized.get('message')
        if (source is None or source == []) and isinstance(raw, str) and raw:
            source = raw
        normalized['message'] = normalize_message(source or [])
        sender = normalized.get('sender')
        sender = dict(sender) if isinstance(sender, dict) else {}
        sender_aliases = {
            'user_id': ('userId', 'uin'),
            'nickname': ('nick', 'name'),
            'card': ('member_name', 'remark'),
            'role': ('member_role', 'sender_role', 'permission'),
        }
        for canonical, aliases in sender_aliases.items():
            if sender.get(canonical) not in (None, ''):
                continue
            for alias in aliases:
                if sender.get(alias) not in (None, ''):
                    sender[canonical] = sender[alias]
                    break
        for aliases in sender_aliases.values():
            for alias in aliases:
                if alias == 'permission':
                    continue
                sender.pop(alias, None)
        sender['user_id'] = _number(sender.get('user_id'), _number(normalized.get('user_id'), 0))
        sender.setdefault('nickname', '')
        sender.setdefault('card', '')
        if 'role' in sender or 'permission' in sender:
            normalized_role = normalize_role(sender.get('role') or sender.get('permission'))
            sender['role'] = normalized_role
            sender['permission'] = normalized_role
        normalized['sender'] = sender
        message_type = normalize_message_kind(normalized.get('message_type'))
        if message_type == MessageKind.PRIVATE and normalized.get('sub_type') in {'temp', 'temporary', 'temp_group'}:
            normalized['sub_type'] = 'group'
        normalized['message_type'] = str(message_type)
        normalized.setdefault('sub_type', 'normal' if message_type == MessageKind.GROUP else 'friend')
        normalized.setdefault('message_format', 'array')
        normalized.setdefault('font', 14)
        normalized['message_id'] = _number(normalized.get('message_id'), 0)
        normalized['message_seq'] = _number(normalized.get('message_seq'), normalized['message_id'])
        normalized['real_id'] = _number(normalized.get('real_id'), normalized['message_id'])
        normalized['real_seq'] = _number(normalized.get('real_seq'), normalized['message_seq'])
        normalized['user_id'] = _number(normalized.get('user_id'), 0)
        if not normalized.get('raw_message'):
            normalized['raw_message'] = message_to_cq(normalized['message'])
    return normalized


def parse_event(data: dict, default_self_id: str = '') -> OneBotEvent | None:
    normalized = normalize_event(data, default_self_id)
    if normalized is None:
        return None
    match normalized.get('post_type'):
        case PostType.MESSAGE | 'message_sent':
            return MessageEvent(normalized)
        case PostType.NOTICE:
            return NoticeEvent(normalized)
        case PostType.REQUEST:
            return RequestEvent(normalized)
        case PostType.META:
            return MetaEvent(normalized)
        case _:
            return OneBotEvent(normalized)
