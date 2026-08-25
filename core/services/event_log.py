"""OneBot 事件与已发送消息的展示、去重和持久化。"""

from __future__ import annotations

import datetime
import json
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from core.foundation.logging import SYSTEM, get_logger
from core.protocols.onebot.event import MessageEvent, MetaEvent, NoticeEvent, RequestEvent
from core.protocols.onebot.event_labels import event_label
from core.protocols.onebot.protocol import action_succeeded
from core.services.logs import LogService

log = get_logger(SYSTEM, '事件日志')

_MESSAGE_LABELS = {
    'image': '图片',
    'face': '表情',
    'record': '语音',
    'video': '视频',
    'reply': '回复',
    'json': 'JSON',
    'xml': 'XML',
    'node': '合并转发',
}
_SEND_ACTIONS = {'send_msg', 'send_group_msg', 'send_private_msg'}


def format_message_content(message: Any) -> str:
    """将 OneBot 字符串或消息段转换为适合日志展示的文本。"""
    if isinstance(message, str):
        return message.strip() or '[空消息]'
    segments: list | tuple
    if isinstance(message, dict):
        segments = (message,)
    elif isinstance(message, (list, tuple)):
        segments = message
    else:
        content = str(message or '').strip()
        return content or '[空消息]'

    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_type = str(segment.get('type') or '')
        data = segment.get('data')
        if not isinstance(data, dict):
            data = {}
        if segment_type == 'text':
            parts.append(str(data.get('text') or '').strip())
        elif segment_type == 'at':
            parts.append(f'@{data.get("qq", "")}')
        elif segment_type in _MESSAGE_LABELS:
            parts.append(f'[{_MESSAGE_LABELS[segment_type]}]')
        elif segment_type:
            parts.append(f'[{segment_type}]')
    return ''.join(parts) or '[空消息]'


def is_channel_message(event: MessageEvent) -> bool:
    """频道消息不进入普通群聊或私聊的消息记录。"""
    raw = event.raw_data if isinstance(event.raw_data, dict) else {}
    if str(raw.get('message_type') or '').lower() in {'guild', 'channel'}:
        return True
    if any(raw.get(key) not in (None, '', 0, '0') for key in ('guild_id', 'guildId', 'channel_id', 'channelId')):
        return True
    chat_type = raw.get('_chat_type', raw.get('chatType', raw.get('chat_type')))
    if chat_type in (None, ''):
        return False
    try:
        return int(chat_type) not in (1, 2)
    except (TypeError, ValueError):
        return str(chat_type).lower() in {'guild', 'channel'}


class EventLogRecorder:
    """集中维护事件日志策略，避免应用编排器承担数据转换职责。"""

    def __init__(
        self,
        storage: LogService,
        web_callback: Callable[[str, dict], None] | None = None,
        *,
        recent_message_limit: int = 4096,
    ) -> None:
        self._storage = storage
        self._web_callback = web_callback
        self._recent_limit = max(1, recent_message_limit)
        self._recent_messages: OrderedDict[tuple[str, str], None] = OrderedDict()

    def _remember_message(self, bot_qq: str, message_id: str) -> bool:
        if not message_id:
            return True
        key = (bot_qq, message_id)
        if key in self._recent_messages:
            self._recent_messages.move_to_end(key)
            return False
        self._recent_messages[key] = None
        while len(self._recent_messages) > self._recent_limit:
            self._recent_messages.popitem(last=False)
        return True

    def _push_web(self, log_type: str, entry: dict) -> None:
        if self._web_callback:
            self._web_callback(log_type, entry)

    async def log_sent_message(self, self_id: str, action: str, params: dict, response: dict) -> bool:
        """记录成功发送的 OneBot 消息。"""
        if action not in _SEND_ACTIONS or not action_succeeded(response):
            return False

        message_type = str(params.get('message_type') or '')
        if action == 'send_group_msg' or params.get('group_id') is not None:
            message_type = 'group'
        elif action == 'send_private_msg' or params.get('user_id') is not None:
            message_type = 'private'
        if message_type not in {'group', 'private'}:
            return False

        target_key = 'group_id' if message_type == 'group' else 'user_id'
        target_id = str(params.get(target_key) or '')
        if not target_id:
            return False

        bot_qq = str(self_id or '')
        content = format_message_content(params.get('message'))
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result_data = response.get('data')
        if not isinstance(result_data, dict):
            result_data = {}
        message_id = str(result_data.get('message_id') or '')
        if not self._remember_message(bot_qq, message_id):
            return True

        group_id = target_id if message_type == 'group' else ''
        user_id = '' if message_type == 'group' else target_id
        location = f'群({target_id})' if message_type == 'group' else f'私聊({target_id})'
        display = content[:100] + '...' if len(content) > 100 else content
        log.info(
            '[%s] 发送%s | %s | %s',
            bot_qq,
            '群聊' if message_type == 'group' else '私聊',
            location,
            display,
            extra={'web_skip': True},
        )

        self._push_web(
            'message',
            {
                'timestamp': timestamp,
                'content': content,
                'user_id': user_id,
                'group_id': group_id,
                'message_id': message_id,
                'message_type': message_type,
                'sender': bot_qq,
                'bot_qq': bot_qq,
                'direction': 'send',
                'raw_message': '',
            },
        )
        await self._storage.add(
            'message',
            {
                'timestamp': timestamp,
                'content': content,
                'source': bot_qq,
                'user_id': user_id,
                'group_id': group_id,
                'message_id': message_id,
                'message_type': message_type,
                'raw_data': '',
                'extra': 'send',
            },
            bot_qq=bot_qq,
            durable=True,
        )
        return True

    async def log_event(self, event: Any) -> None:
        """记录已经完成规范化的 OneBot 事件。"""
        if isinstance(event, MetaEvent) and str(event.meta_event_type).lower() == 'heartbeat':
            return
        if isinstance(event, MessageEvent):
            await self._log_message_event(event)
        elif isinstance(event, (NoticeEvent, RequestEvent, MetaEvent)):
            await self._log_lifecycle_event(event)

    async def _log_message_event(self, event: MessageEvent) -> None:
        if is_channel_message(event):
            return
        is_sent = bool(getattr(event, 'is_sent', False))
        if is_sent and not self._remember_message(str(event.self_id or ''), str(event.message_id or '')):
            return

        msg_type = '群聊' if event.is_group else '私聊'
        sender = event.sender_card or event.sender_nickname or str(event.user_id)
        target_id = str(event.raw_data.get('target_id') or event.user_id)
        location = f'群({event.group_id})' if event.is_group else f'私聊({target_id})'
        content = format_message_content(event.message)
        display = content[:100] + '...' if len(content) > 100 else content
        verb = '发送' if is_sent else '接收'
        log.info(f'[{event.self_id}] {verb}{msg_type} | {location} | {sender}: {display}', extra={'web_skip': True})

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        bot_qq = str(event.self_id or '')
        raw_json = json.dumps(event.raw_data, ensure_ascii=False)
        nickname = ''
        if isinstance(event.sender, dict):
            nickname = event.sender.get('card') or event.sender.get('nickname') or ''
        user_id = target_id if is_sent and event.is_private else str(event.user_id)
        group_id = str(event.group_id or '')
        direction = 'send' if is_sent else 'receive'

        self._push_web(
            'message',
            {
                'timestamp': timestamp,
                'content': content,
                'user_id': user_id,
                'group_id': group_id,
                'message_id': str(event.message_id),
                'message_type': event.message_type,
                'sender': sender,
                'bot_qq': bot_qq,
                'direction': direction,
                'raw_message': raw_json,
            },
        )
        await self._storage.add(
            'message',
            {
                'timestamp': timestamp,
                'content': content,
                'source': bot_qq,
                'user_id': user_id,
                'group_id': group_id,
                'message_id': str(event.message_id),
                'message_type': event.message_type,
                'raw_data': raw_json,
                'extra': json.dumps({'nickname': nickname, 'direction': direction}, ensure_ascii=False),
            },
            bot_qq=bot_qq,
            durable=True,
        )

    async def _log_lifecycle_event(self, event: NoticeEvent | RequestEvent | MetaEvent) -> None:
        if isinstance(event, NoticeEvent):
            event_type = event.notice_type
        elif isinstance(event, RequestEvent):
            event_type = f'request.{event.request_type}'
        else:
            event_type = f'meta_event.{event.meta_event_type}'
        sub_type = str(getattr(event, 'sub_type', '') or event.raw_data.get('sub_type') or '')
        user_id = str(getattr(event, 'user_id', '') or '')
        group_id = str(getattr(event, 'group_id', '') or '')
        type_label = event_label(event_type, sub_type)
        log.debug(f'事件: {type_label} | 群 {group_id} | 用户 {user_id}', extra={'web_skip': True})

        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        bot_qq = str(event.self_id or '')
        raw_json = json.dumps(event.raw_data, ensure_ascii=False)
        content = f'{type_label} | 群{group_id} | 用户{user_id}'
        self._push_web(
            'lifecycle',
            {
                'timestamp': now,
                'type': event_type,
                'event_type': event_type,
                'type_label': type_label,
                'user_id': user_id,
                'group_id': group_id,
                'bot_qq': bot_qq,
                'content': content,
                'raw_message': raw_json,
            },
        )
        await self._storage.add(
            'lifecycle',
            {
                'timestamp': now,
                'content': content,
                'source': bot_qq,
                'user_id': user_id,
                'group_id': group_id,
                'message_type': event_type,
                'raw_data': raw_json,
            },
            bot_qq=bot_qq,
            durable=True,
        )
        if isinstance(event, NoticeEvent) and event.notice_type in ('group_recall', 'friend_recall'):
            recalled_mid = str(event.raw_data.get('message_id', '') or '')
            if recalled_mid:
                await self._storage.execute(
                    'message',
                    "UPDATE log SET extra = 'recalled' WHERE message_id = ?",
                    (recalled_mid,),
                    bot_qq=bot_qq,
                )

