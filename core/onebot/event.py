"""OneBot v11 事件模型 (异步框架)"""

import time
from enum import StrEnum


class PostType(StrEnum):
    """OneBot 上报类型"""

    MESSAGE = 'message'
    NOTICE = 'notice'
    REQUEST = 'request'
    META = 'meta_event'


class MsgType(StrEnum):
    """消息类型"""

    GROUP = 'group'
    PRIVATE = 'private'


class OneBotEvent:
    """OneBot v11 基础事件"""

    __slots__ = ('raw_data', 'time', 'self_id', 'post_type', '_api')

    def __init__(self, data: dict):
        self.raw_data = data
        self.time = data.get('time', int(time.time()))
        self.self_id = data.get('self_id', '')
        self.post_type = data.get('post_type', '')
        self._api = None  # 由 Application 注入

    def to_dict(self) -> dict:
        return self.raw_data

    @property
    def content(self) -> str:
        return ''


class MessageEvent(OneBotEvent):
    """消息事件"""

    __slots__ = ('message_type', 'sub_type', 'message_id', 'user_id', 'group_id', 'message', 'raw_message', 'sender', 'font', '_content')

    def __init__(self, data: dict):
        super().__init__(data)
        self.message_type = data.get('message_type', '')
        self.sub_type = data.get('sub_type', '')
        self.message_id = data.get('message_id', 0)
        self.user_id = data.get('user_id', 0)
        self.group_id = data.get('group_id')
        self.message: list[dict] = data.get('message', [])
        self.raw_message = data.get('raw_message', '')
        self.sender: dict = data.get('sender', {})
        self.font = data.get('font', 0)
        self._content: str | None = None

    @property
    def is_group(self) -> bool:
        return self.message_type == MsgType.GROUP

    @property
    def is_private(self) -> bool:
        return self.message_type == MsgType.PRIVATE

    @property
    def sender_nickname(self) -> str:
        return self.sender.get('nickname', '')

    @property
    def sender_card(self) -> str:
        return self.sender.get('card', '')

    @property
    def content(self) -> str:
        """提取纯文本内容 (首次访问后缓存)"""
        if self._content is None:
            parts = [seg.get('data', {}).get('text', '') for seg in self.message if isinstance(seg, dict) and seg.get('type') == 'text']
            self._content = ''.join(parts).strip()
        return self._content

    async def reply(self, message, **kwargs):
        """异步回复消息 (字符串或消息段列表)"""
        if self._api is None:
            return None
        if isinstance(message, str):
            message = [{'type': 'text', 'data': {'text': message}}]
        if self.is_group:
            return await self._api.send_group_msg(self.group_id, message, **kwargs, self_id=str(self.self_id))
        else:
            return await self._api.send_private_msg(self.user_id, message, **kwargs, self_id=str(self.self_id))

    async def reply_text(self, text: str, **kwargs):
        """回复纯文本"""
        return await self.reply(text, **kwargs)

    async def reply_image(self, file: str, **kwargs):
        """回复图片"""
        msg = [{'type': 'image', 'data': {'file': file}}]
        return await self.reply(msg, **kwargs)

    async def call_api(self, action: str, params: dict | None = None):
        """调用 OneBot API"""
        if self._api is None:
            return None
        return await self._api.call_api(action, params, self_id=str(self.self_id))


class NoticeEvent(OneBotEvent):
    """通知事件"""

    __slots__ = ('notice_type', 'sub_type', 'user_id', 'group_id', 'operator_id')

    def __init__(self, data: dict):
        super().__init__(data)
        self.notice_type = data.get('notice_type', '')
        self.sub_type = data.get('sub_type', '')
        self.user_id = data.get('user_id', 0)
        self.group_id = data.get('group_id')
        self.operator_id = data.get('operator_id', 0)


class RequestEvent(OneBotEvent):
    """请求事件"""

    __slots__ = ('request_type', 'sub_type', 'user_id', 'group_id', 'comment', 'flag')

    def __init__(self, data: dict):
        super().__init__(data)
        self.request_type = data.get('request_type', '')
        self.sub_type = data.get('sub_type', '')
        self.user_id = data.get('user_id', 0)
        self.group_id = data.get('group_id')
        self.comment = data.get('comment', '')
        self.flag = data.get('flag', '')


class MetaEvent(OneBotEvent):
    """元事件"""

    __slots__ = ('meta_event_type',)

    def __init__(self, data: dict):
        super().__init__(data)
        self.meta_event_type = data.get('meta_event_type', '')


def normalize_event(data: dict, default_self_id: str = '') -> dict | None:
    """统一不同 OneBot 实现上报的等价字段与消息表示。"""
    if not isinstance(data, dict):
        return None
    normalized = dict(data)
    if default_self_id and not normalized.get('self_id'):
        normalized['self_id'] = str(default_self_id)
    if 'post_type' not in normalized and normalized.get('postType'):
        normalized['post_type'] = normalized['postType']
    if 'post_type' not in normalized:
        return None

    if normalized.get('post_type') == PostType.MESSAGE:
        message = normalized.get('message', [])
        if isinstance(message, str):
            message = [{'type': 'text', 'data': {'text': message}}]
        elif isinstance(message, dict):
            message = [message]
        elif not isinstance(message, list):
            message = []
        normalized['message'] = message
        sender = normalized.get('sender')
        sender = {} if not isinstance(sender, dict) else dict(sender)
        sender.setdefault('user_id', normalized.get('user_id', 0))
        normalized['sender'] = sender
        message_type = str(normalized.get('message_type') or '')
        if message_type in {'friend', 'user'}:
            normalized['message_type'] = MsgType.PRIVATE
        if normalized.get('raw_message') is None:
            normalized['raw_message'] = ''
        if not normalized.get('raw_message'):
            normalized['raw_message'] = ''.join(
                str(segment.get('data', {}).get('text') or '')
                for segment in message
                if isinstance(segment, dict) and segment.get('type') == 'text'
            )
    return normalized


def parse_event(data: dict, default_self_id: str = '') -> OneBotEvent | None:
    """规范化并解析 OneBot 事件。"""
    normalized = normalize_event(data, default_self_id)
    if normalized is None:
        return None

    match normalized.get('post_type'):
        case PostType.MESSAGE:
            return MessageEvent(normalized)
        case PostType.NOTICE:
            return NoticeEvent(normalized)
        case PostType.REQUEST:
            return RequestEvent(normalized)
        case PostType.META:
            return MetaEvent(normalized)
        case _:
            return OneBotEvent(normalized)
