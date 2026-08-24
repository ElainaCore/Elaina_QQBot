"""OneBot v11 事件模型与跨连接字段规范化。"""

import time
from enum import StrEnum
from typing import Any

from core.protocols.onebot.message import message_to_cq, normalize_message


class PostType(StrEnum):
    MESSAGE = 'message'
    NOTICE = 'notice'
    REQUEST = 'request'
    META = 'meta_event'


class MsgType(StrEnum):
    GROUP = 'group'
    PRIVATE = 'private'


def _copy_alias(data: dict, canonical: str, *aliases: str) -> None:
    if canonical in data and data[canonical] is not None:
        return
    for alias in aliases:
        if alias in data and data[alias] is not None:
            data[canonical] = data[alias]
            return


def _number(value: Any, default: int = 0) -> Any:
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


class OneBotEvent:
    __slots__ = ('raw_data', 'time', 'self_id', 'post_type', 'event_type', '_api')

    def __init__(self, data: dict):
        self.raw_data = data
        self.time = _number(data.get('time'), int(time.time()))
        self.self_id = data.get('self_id', '')
        self.post_type = data.get('post_type', '')
        self.event_type = data.get('event_type', self.post_type)
        self._api = None

    def __getattr__(self, name: str):
        raw_data = object.__getattribute__(self, 'raw_data')
        if name in raw_data:
            return raw_data[name]
        raise AttributeError(name)

    def to_dict(self) -> dict:
        return self.raw_data

    @property
    def content(self) -> str:
        return ''


class MessageEvent(OneBotEvent):
    __slots__ = ('message_type', 'sub_type', 'message_id', 'message_seq', 'real_id', 'real_seq', 'user_id', 'group_id', 'group_name', 'temp_source', 'target_id', 'message', 'raw_message', 'message_format', 'message_sent_type', 'sender', 'font', '_content')

    def __init__(self, data: dict):
        super().__init__(data)
        self.message_type = data.get('message_type', '')
        self.sub_type = data.get('sub_type', '')
        self.message_id = data.get('message_id', 0)
        self.message_seq = data.get('message_seq', data.get('real_seq', 0))
        self.real_id = data.get('real_id', self.message_id)
        self.real_seq = data.get('real_seq', self.message_seq)
        self.user_id = data.get('user_id', 0)
        self.group_id = data.get('group_id')
        self.group_name = data.get('group_name', '')
        self.temp_source = data.get('temp_source', 0)
        self.target_id = data.get('target_id')
        self.message = normalize_message(data.get('message', []))
        self.raw_message = data.get('raw_message', '') or message_to_cq(self.message)
        self.message_format = data.get('message_format', 'array')
        self.message_sent_type = data.get('message_sent_type', '')
        self.sender = data.get('sender', {}) if isinstance(data.get('sender', {}), dict) else {}
        self.font = data.get('font', 14)
        self._content = None

    @property
    def is_group(self) -> bool:
        return self.message_type == MsgType.GROUP

    @property
    def is_private(self) -> bool:
        return self.message_type == MsgType.PRIVATE

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
        self.notice_type = data.get('notice_type', '')
        self.sub_type = data.get('sub_type', '')
        self.user_id = data.get('user_id', 0)
        self.group_id = data.get('group_id')
        self.operator_id = data.get('operator_id', 0)


class RequestEvent(OneBotEvent):
    __slots__ = ('request_type', 'sub_type', 'user_id', 'group_id', 'comment', 'flag', 'approve', 'reason')

    def __init__(self, data: dict):
        super().__init__(data)
        self.request_type = data.get('request_type', '')
        self.sub_type = data.get('sub_type', '')
        self.user_id = data.get('user_id', 0)
        self.group_id = data.get('group_id')
        self.comment = data.get('comment', '')
        self.flag = data.get('flag', '')
        self.approve = data.get('approve')
        self.reason = data.get('reason', '')


class MetaEvent(OneBotEvent):
    __slots__ = ('meta_event_type', 'status', 'interval')

    def __init__(self, data: dict):
        super().__init__(data)
        self.meta_event_type = data.get('meta_event_type', '')
        self.status = data.get('status', {})
        self.interval = data.get('interval', 0)


def normalize_event(data: dict, default_self_id: str = '') -> dict | None:
    """统一内置、WebSocket、HTTP 上报的等价字段与消息表示。"""
    if not isinstance(data, dict):
        return None
    normalized = dict(data)
    aliases = {
        'post_type': ('postType',), 'self_id': ('selfId', 'selfUin'), 'message_type': ('messageType',),
        'sub_type': ('subType',), 'message_id': ('messageId', 'msg_id', 'msgId'),
        'message_seq': ('messageSeq', 'msgSeq'), 'real_id': ('realId',), 'real_seq': ('realSeq',),
        'user_id': ('userId',), 'group_id': ('groupId',), 'group_name': ('groupName',),
        'target_id': ('targetId', 'targetUin'),
        'raw_message': ('rawMessage',), 'notice_type': ('noticeType',), 'request_type': ('requestType',),
        'meta_event_type': ('metaEventType',), 'message_sent_type': ('messageSentType',),
    }
    for canonical, names in aliases.items():
        _copy_alias(normalized, canonical, *names)
    if default_self_id and not normalized.get('self_id'):
        normalized['self_id'] = str(default_self_id)
    post_type = str(normalized.get('post_type') or '').strip().lower().replace('-', '_')
    if post_type in {'meta', 'metaevent'}:
        post_type = 'meta_event'
    if post_type in {'message_sent', 'message_sent_event'}:
        normalized.setdefault('message_sent_type', 'self')
        post_type = 'message_sent'
    if not post_type:
        return None
    normalized['post_type'] = post_type
    if post_type in {PostType.MESSAGE, 'message_sent'}:
        raw = normalized.get('raw_message')
        source = normalized.get('message')
        if (source is None or source == []) and isinstance(raw, str) and raw:
            source = raw
        normalized['message'] = normalize_message(source or [])
        sender = normalized.get('sender')
        sender = dict(sender) if isinstance(sender, dict) else {}
        _copy_alias(sender, 'user_id', 'userId', 'uin')
        sender.setdefault('user_id', normalized.get('user_id', 0))
        _copy_alias(sender, 'nickname', 'nick', 'name')
        _copy_alias(sender, 'card', 'member_name', 'remark')
        normalized['sender'] = sender
        message_type = str(normalized.get('message_type') or '').lower()
        if message_type in {'friend', 'user', 'c2c', 'dm'}:
            message_type = 'private'
        elif message_type in {'temp', 'temporary', 'temp_group'}:
            message_type = 'private'
            normalized.setdefault('sub_type', 'group')
        normalized['message_type'] = message_type or 'private'
        normalized.setdefault('sub_type', 'normal' if message_type == 'group' else 'friend')
        normalized.setdefault('message_format', 'array')
        normalized.setdefault('font', 14)
        normalized.setdefault('message_seq', normalized.get('message_id', 0))
        normalized.setdefault('real_id', normalized.get('message_id', 0))
        normalized.setdefault('real_seq', normalized.get('message_seq', 0))
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
