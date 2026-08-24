"""消息管理 — 聊天列表 / 历史 / 发送 / 撤回 (异步架构)"""

import asyncio
import contextlib
import json
import os
import time
from datetime import datetime
from typing import Any

from aiohttp import web
from aiohttp.multipart import BodyPartReader

from web.protocol import json_body
from web.tools import _common

_base_dir = ''
_chat_cache: dict = {}
_CHAT_TTL = 10
_directory_cache: dict[tuple[str, str], tuple[float, dict[str, dict]]] = {}
_directory_tasks: dict[tuple[str, str], asyncio.Task] = {}
_DIRECTORY_TTL = 600
_INVALID_NAMES = {'[object Map]', '[object Object]', 'undefined', 'null'}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _display_text(value: Any) -> str:
    """将 QQ 内核可能返回的 Map/对象名称归一化为可展示文本。"""
    if value is None:
        return ''
    if isinstance(value, str):
        text = value.strip()
        return '' if text in _INVALID_NAMES else text
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ('remark', 'name', 'nickname', 'nick', 'card', 'text', 'value'):
            text = _display_text(value.get(key))
            if text:
                return text
        for item in value.values():
            text = _display_text(item)
            if text:
                return text
        return ''
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = _display_text(item)
            if text:
                return text
        return ''
    text = str(value).strip()
    return '' if text in _INVALID_NAMES else text


def set_context(app_instance, base_dir=''):
    global _base_dir
    _common.set_app(app_instance)
    if base_dir:
        _base_dir = base_dir


def _api():
    from core.protocols.onebot.api import get_api

    return get_api()


def _primary_id():
    return _common.primary_bot_qq()


# ──────────── 昵称 ────────────


async def handle_get_nickname(request: web.Request):
    body = await json_body(request)
    uid = str(body.get('user_id', ''))
    if not uid:
        return web.json_response({'success': False, 'message': '缺少用户ID'}, status=400)
    bot_qq = str(body.get('bot_qq') or _primary_id())
    nick = await _common.get_nickname(uid, bot_qq)
    return web.json_response({'success': True, 'data': {'user_id': uid, 'nickname': nick}})


async def handle_get_nicknames_batch(request: web.Request):
    body = await json_body(request)
    uids = body.get('user_ids', [])
    if not isinstance(uids, list) or not uids:
        return web.json_response({'success': False, 'message': '缺少用户ID列表'}, status=400)
    bot_qq = str(body.get('bot_qq') or _primary_id())
    result = await _common.batch_nicknames(uids, bot_qq)
    return web.json_response({'success': True, 'data': {'nicknames': result}})


# ──────────── 聊天列表 ────────────


def _onebot_ok(response) -> bool:
    if not isinstance(response, dict):
        return False
    try:
        return int(response.get('retcode', -1)) == 0
    except (TypeError, ValueError):
        return False


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _onebot_data(response, default=None):
    if not _onebot_ok(response):
        return default
    data = response.get('data')
    return default if data is None else data


def _timestamp_text(value) -> str:
    """将 QQ 秒/毫秒时间戳统一为面板使用的本地时间。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = str(value or '')
        return text if '-' in text else ''
    if number > 10**11:
        number /= 1000
    return datetime.fromtimestamp(number).strftime('%Y-%m-%d %H:%M:%S') if number > 0 else ''


def _segment_content(message) -> str:
    labels = {
        'image': '[图片]',
        'record': '[语音]',
        'video': '[视频]',
        'file': '[文件]',
        'face': '[表情]',
        'forward': '[合并转发]',
    }
    parts = []
    for segment in message if isinstance(message, list) else []:
        if not isinstance(segment, dict):
            continue
        kind = str(segment.get('type') or '')
        data = _as_dict(segment.get('data'))
        if kind == 'text':
            parts.append(str(data.get('text') or ''))
        elif kind == 'at':
            parts.append('@' + str(data.get('name') or data.get('qq') or ''))
        elif kind != 'reply':
            parts.append(labels.get(kind, f'[{kind}]' if kind else ''))
    return ''.join(parts).strip()


async def _fetch_directory(api, chat_type: str, bot_qq: str) -> dict[str, dict]:
    """读取联系人目录并长缓存，避免每次刷新聊天列表都全量调用 OneBot。"""
    cache_key = (str(bot_qq), chat_type)
    now = time.time()
    cached = _directory_cache.get(cache_key)
    if cached and now - cached[0] < _DIRECTORY_TTL:
        return cached[1]

    async def load() -> dict[str, dict]:
        response = (
            await api.get_friend_list(self_id=bot_qq)
            if chat_type == 'user'
            else await api.get_group_list(self_id=bot_qq)
        )
        if not _onebot_ok(response):
            raise RuntimeError('获取联系人目录失败')
        result = {}
        for item in _onebot_data(response, []) or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get('user_id') if chat_type == 'user' else item.get('group_id') or '')
            if key:
                result[key] = item
        return result

    task = _directory_tasks.get(cache_key)
    if cached:
        if task is None:
            task = asyncio.create_task(load())
            _directory_tasks[cache_key] = task

            def finish_refresh(completed: asyncio.Task) -> None:
                if _directory_tasks.get(cache_key) is completed:
                    _directory_tasks.pop(cache_key, None)
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    _directory_cache[cache_key] = (time.time(), completed.result())

            task.add_done_callback(finish_refresh)
        return cached[1]

    if task is None:
        task = asyncio.create_task(load())
        _directory_tasks[cache_key] = task
    try:
        result = await task
    except Exception:
        return cached[1] if cached else {}
    finally:
        if _directory_tasks.get(cache_key) is task:
            _directory_tasks.pop(cache_key, None)
    _directory_cache[cache_key] = (time.time(), result)
    return result


def _is_channel_payload(value: Any) -> bool:
    payload = _as_dict(value)
    chat_type = payload.get('_chat_type', payload.get('chatType', payload.get('chat_type')))
    if chat_type not in (None, ''):
        try:
            if int(chat_type) not in (1, 2):
                return True
        except (TypeError, ValueError):
            if str(chat_type).lower() in {'guild', 'channel'}:
                return True
    message_type = str(payload.get('message_type') or '').lower()
    if message_type in {'guild', 'channel'}:
        return True
    return any(payload.get(key) not in (None, '', 0, '0') for key in ('channel_id', 'channelId', 'guild_id', 'guildId'))


async def _db_chat_stats(chat_type: str, bot_qq: str) -> dict[str, dict]:
    """读取已持久化消息的会话摘要，供完整目录补充最近消息。"""
    if chat_type == 'group':
        key, where = 'group_id', "group_id != ''"
    else:
        key, where = 'user_id', "user_id != '' AND group_id = ''"
    rows = await _common.query_log(
        'message',
        f"""SELECT chat_id, id AS last_id, timestamp AS last_time, content AS last_content, raw_data, msg_count
                   FROM (
                       SELECT {key} AS chat_id, id, timestamp, content, raw_data,
                              COUNT(*) OVER (PARTITION BY {key}) AS msg_count,
                              ROW_NUMBER() OVER (
                                  PARTITION BY {key} ORDER BY timestamp DESC, id DESC
                              ) AS row_number
                       FROM log WHERE {where}
                   )
                   WHERE row_number = 1
                   ORDER BY last_time DESC, last_id DESC""",
        bot_qq=bot_qq,
    )
    result = {}
    for row in rows:
        chat_id = str(row.get('chat_id') or '')
        if not chat_id:
            continue
        raw = {}
        with contextlib.suppress(TypeError, ValueError):
            raw = json.loads(row.get('raw_data') or '{}')
        if _is_channel_payload(raw):
            continue
        result[chat_id] = row
    return result


def _directory_chats(chat_type: str, directory: dict[str, dict], stats: dict[str, dict], bot_qq: str) -> list[dict]:
    """合并联系人目录与已有消息记录，目录名称已由长缓存提供。"""
    remarks = _load_remarks()
    chats = []
    for chat_id in dict.fromkeys((*directory.keys(), *stats.keys())):
        item = directory.get(chat_id, {})
        stat = stats.get(chat_id, {})
        remark = _display_text(item.get('remark')) if chat_type == 'user' else _remark_name(remarks.get(chat_id))
        name = remark or _display_text(item.get('nickname')) or _display_text(item.get('group_name')) or chat_id
        chats.append(
            {
                'chat_id': chat_id,
                'bot_qq': bot_qq,
                'nickname': str(name),
                'remark': str(remark or ''),
                'group_qq': _remark_qq(remarks.get(chat_id)) if chat_type == 'group' else '',
                'last_id': str(stat.get('last_id') or ''),
                'last_time': str(stat.get('last_time') or ''),
                'last_date': str(stat.get('last_time') or '')[:10],
                'last_content': str(stat.get('last_content') or ''),
                'msg_count': int(stat.get('msg_count') or 0),
                'source': 'onebot_directory' if chat_id in directory else 'message_database',
            }
        )
    return chats


async def _fetch_chats(chat_type, bot_qq=''):
    """读取 QQ 原生最近会话，并用好友/群目录补全真实名称。"""
    bot_qq = str(bot_qq or _primary_id())
    api = _api()

    async def get_recent():
        try:
            return await api.get_recent_contact(count=100, self_id=bot_qq)
        except Exception:
            return None

    recent_response, directory, stats = await asyncio.gather(
        get_recent(),
        _fetch_directory(api, chat_type, bot_qq),
        _db_chat_stats(chat_type, bot_qq),
    )
    chats_by_id = {
        item['chat_id']: item
        for item in _directory_chats(chat_type, directory, stats, bot_qq)
    }
    if not _onebot_ok(recent_response):
        chats = list(chats_by_id.values())
        chats.sort(key=lambda item: (item['last_time'], item['nickname']), reverse=True)
        return chats

    remarks = _load_remarks()
    wanted_type = 2 if chat_type == 'group' else 1
    for contact in _onebot_data(recent_response, []) or []:
        if not isinstance(contact, dict) or _is_channel_payload(contact):
            continue
        try:
            contact_type = int(contact.get('chatType') or 0)
        except (TypeError, ValueError):
            continue
        if contact_type != wanted_type:
            continue
        chat_id = str(contact.get('peerUin') or '')
        if not chat_id or not chat_id.isdigit():
            continue
        latest = contact.get('lastestMsg') if isinstance(contact.get('lastestMsg'), dict) else {}
        last_time = _timestamp_text(contact.get('msgTime') or latest.get('time'))
        directory_item = directory.get(chat_id, {})
        if chat_type == 'group':
            remark = _remark_name(remarks.get(chat_id))
            name = remark or _display_text(contact.get('peerName')) or _display_text(directory_item.get('group_name')) or chat_id
        else:
            remark = _display_text(contact.get('remark')) or _display_text(directory_item.get('remark'))
            name = (
                remark
                or _display_text(contact.get('peerName'))
                or _display_text(directory_item.get('nickname'))
                or _display_text(contact.get('sendNickName'))
                or chat_id
            )
        candidate = {
            'chat_id': chat_id,
            'bot_qq': bot_qq,
            'nickname': str(name),
            'remark': str(remark),
            'group_qq': _remark_qq(remarks.get(chat_id)) if chat_type == 'group' else '',
            'last_id': str(contact.get('msgId') or latest.get('message_id') or ''),
            'last_time': last_time,
            'last_date': last_time[:10],
            'last_content': _segment_content(latest.get('message')) or str(latest.get('raw_message') or ''),
            'msg_count': int(stats.get(chat_id, {}).get('msg_count') or 0),
            'source': 'qq_native',
        }
        previous = chats_by_id.get(chat_id)
        if previous is None:
            chats_by_id[chat_id] = candidate
        else:
            # 最近会话提供预览，完整目录提供稳定名称与数据库统计。
            previous.update({key: value for key, value in candidate.items() if value not in ('', None)})
            if not previous.get('last_content'):
                previous['last_content'] = str(stats.get(chat_id, {}).get('last_content') or '')

    chats = list(chats_by_id.values())
    chats.sort(key=lambda item: item['last_time'], reverse=True)
    return chats


async def handle_get_chats(request: web.Request):
    try:
        body = await json_body(request)
    except Exception:
        body = {}
    chat_type = body.get('type', 'group')
    requested_bot_qq = str(body.get('bot_qq') or '')
    if chat_type not in ('group', 'user'):
        chat_type = 'group'
    search = str(body.get('search') or '').lower()
    page = _bounded_int(body.get('page'), 1, 1, 100000)
    page_size = _bounded_int(body.get('page_size'), 100, 1, 1000)

    now = time.time()
    bot_ids = [requested_bot_qq] if requested_bot_qq else _common.bot_ids()
    if not bot_ids:
        bot_ids = [_primary_id()]
    cache_key = (tuple(bot_ids), chat_type)
    c = _chat_cache.get(cache_key)
    if c and now - c[0] < _CHAT_TTL:
        chats = c[1]
    else:
        chats = []
        for bot_qq in bot_ids:
            chats.extend(await _fetch_chats(chat_type, bot_qq))
        _chat_cache[cache_key] = (now, chats)

    if search:
        chats = [c for c in chats if search in c['chat_id'].lower() or search in c.get('nickname', '').lower()]

    total = len(chats)
    start = (page - 1) * page_size
    return web.json_response(
        {
            'success': True,
            'data': {'chats': chats[start : start + page_size], 'total': total, 'page': page, 'page_size': page_size},
        }
    )


# ──────────── 历史消息 ────────────


def _event_cursor(event: dict) -> str:
    return str(event.get('message_seq') or event.get('real_seq') or event.get('real_id') or '')


def _event_epoch(event: dict) -> float:
    try:
        value = float(event.get('time') or 0)
    except (TypeError, ValueError):
        return 0
    return value / 1000 if value > 10**11 else value


def _history_db_entry(event: dict, chat_type: str, chat_id: str, bot_qq: str) -> dict:
    """将 QQ 原生历史转换成实时 OneBot 消息使用的同一日志结构。"""
    sender = _as_dict(event.get('sender'))
    event_user_id = str(event.get('user_id') or sender.get('user_id') or '')
    is_self = bool(bot_qq and event_user_id == bot_qq)
    message = _as_list(event.get('message'))
    nickname = _display_text(sender.get('card')) or _display_text(sender.get('nickname'))
    return {
        'timestamp': _timestamp_text(event.get('time')) or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'content': _segment_content(message) or str(event.get('raw_message') or ''),
        'source': bot_qq,
        # 私聊中自己发出的历史事件 user_id 是机器人，日志会话键仍应是好友 QQ；
        # 群聊则保留实际发送者，供消息记录显示昵称与成员身份。
        'user_id': event_user_id if chat_type == 'group' else chat_id,
        'group_id': chat_id if chat_type == 'group' else '',
        'message_id': str(event.get('message_id') or ''),
        'message_type': 'group' if chat_type == 'group' else 'private',
        'raw_data': json.dumps(event, ensure_ascii=False),
        'extra': 'send' if is_self else json.dumps({'nickname': nickname}, ensure_ascii=False),
    }


async def _sync_history(events: list, chat_type: str, chat_id: str, bot_qq: str) -> None:
    svc = _common.log_service()
    if not svc:
        return
    valid = [event for event in events if isinstance(event, dict)]
    valid.sort(key=lambda event: (_event_epoch(event), _event_cursor(event)))
    entries = [_history_db_entry(event, chat_type, chat_id, bot_qq) for event in valid]
    await svc.add_many('message', entries, bot_qq=bot_qq, durable=True)


def _db_cursor(value: str) -> tuple[str, int] | None:
    if not value.startswith('db:'):
        return None
    try:
        timestamp, row_id = value[3:].rsplit(':', 1)
        return timestamp, int(row_id)
    except (TypeError, ValueError):
        return None


async def _history_cursor_seq(
    cursor: tuple[str, int] | None,
    chat_type: str,
    chat_id: str,
    bot_qq: str,
) -> str:
    if cursor is None:
        return ''
    where = 'group_id = ?' if chat_type == 'group' else "user_id = ? AND group_id = ''"
    rows = await _common.query_log(
        'message',
        f"""SELECT raw_data FROM log
              WHERE {where}
                AND (timestamp < ? OR (timestamp = ? AND id <= ?))
                AND raw_data != ''
              ORDER BY timestamp DESC, id DESC
              LIMIT 20""",
        (chat_id, cursor[0], cursor[0], cursor[1]),
        bot_qq=bot_qq,
    )
    for row in rows:
        try:
            event = json.loads(row.get('raw_data') or '{}')
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict) and _event_cursor(event):
            return _event_cursor(event)
    return ''


async def _query_db_history(chat_type: str, chat_id: str, bot_qq: str, count: int, cursor: tuple[str, int] | None) -> tuple[list[dict], bool]:
    where = 'group_id = ?' if chat_type == 'group' else "user_id = ? AND group_id = ''"
    params: list[Any] = [chat_id]
    if cursor is not None:
        where += ' AND (timestamp < ? OR (timestamp = ? AND id < ?))'
        params.extend((cursor[0], cursor[0], cursor[1]))
    rows = await _common.query_log(
        'message',
        f'SELECT * FROM log WHERE {where} ORDER BY timestamp DESC, id DESC LIMIT ?',
        (*params, count + 1),
        bot_qq=bot_qq,
    )
    has_more = len(rows) > count
    rows = rows[:count]
    rows.reverse()

    missing_names = set()
    prepared = []
    for row in rows:
        raw: dict[str, Any] = {}
        with contextlib.suppress(TypeError, ValueError):
            raw = _as_dict(json.loads(row.get('raw_data') or '{}'))
        sender = _as_dict(raw.get('sender'))
        extra = str(row.get('extra') or '')
        is_self = extra == 'send' or str(raw.get('user_id') or sender.get('user_id') or '') == bot_qq
        nickname = _display_text(sender.get('card')) or _display_text(sender.get('nickname'))
        user_id = str(row.get('user_id') or '')
        if user_id and not is_self and not nickname:
            missing_names.add(user_id)
        prepared.append((row, raw, sender, extra, is_self, nickname, user_id))

    nicknames = await _common.batch_nicknames(missing_names, bot_qq) if missing_names else {}
    messages = []
    for row, raw, sender, extra, is_self, nickname, user_id in prepared:
        segments = _as_list(raw.get('message'))
        reply = next((item for item in segments if isinstance(item, dict) and item.get('type') == 'reply'), None)
        message_id = str(row.get('message_id') or '')
        messages.append(
            {
                'id': f"db:{row.get('id')}",
                'db_id': int(row.get('id') or 0),
                'message_id': message_id,
                'message_seq': _event_cursor(raw),
                'reference_id': str(((reply or {}).get('data') or {}).get('id') or ''),
                'user_id': user_id,
                'bot_qq': str(row.get('source') or bot_qq),
                'nickname': (bot_qq or 'Bot') if is_self else nickname or nicknames.get(user_id, user_id),
                'content': str(row.get('content') or ''),
                'timestamp': str(row.get('timestamp') or ''),
                'is_self': is_self,
                'role': str(sender.get('role') or ''),
                'source': 'message_database',
                'raw_message': str(row.get('raw_data') or ''),
                'recalled': extra == 'recalled',
            }
        )
    return messages, has_more


async def handle_get_chat_history(request: web.Request):
    try:
        body = await json_body(request)
    except Exception:
        body = {}
    chat_type = body.get('chat_type', 'group')
    chat_id = str(body.get('chat_id', ''))
    bot_qq = _common.resolve_bot_qq(str(body.get('bot_qq') or _primary_id()))
    if not chat_id:
        return web.json_response({'success': True, 'data': {'messages': [], 'has_more': False}})

    if chat_type not in ('group', 'user'):
        chat_type = 'group'
    cursor_text = str(body.get('before_seq') or body.get('cursor') or body.get('message_seq') or '')
    cursor = _db_cursor(cursor_text)
    count = _bounded_int(body.get('count'), 50, 1, 100)
    native_cursor = await _history_cursor_seq(cursor, chat_type, chat_id, bot_qq) if cursor else cursor_text
    api = _api()
    try:
        if chat_type == 'group':
            response = await api.get_group_msg_history(chat_id, native_cursor or 0, count, False, self_id=bot_qq)
        else:
            response = await api.get_friend_msg_history(chat_id, native_cursor or 0, count, False, self_id=bot_qq)
    except Exception:
        response = None

    data = _onebot_data(response, {})
    events = data.get('messages', []) if isinstance(data, dict) else []
    if events:
        await _sync_history(events, chat_type, chat_id, bot_qq)

    messages, db_has_more = await _query_db_history(chat_type, chat_id, bot_qq, count, cursor)
    has_more = db_has_more or len(events) >= count
    next_cursor = ''
    if messages:
        first = messages[0]
        next_cursor = f"db:{first.get('timestamp', '')}:{first.get('db_id', 0)}"
    if cursor_text and next_cursor == cursor_text:
        has_more = False

    last_msg_id = next((item['message_id'] for item in reversed(messages) if not item['is_self']), '')
    oldest_date = messages[0]['timestamp'][:10] if messages else datetime.now().strftime('%Y-%m-%d')
    return web.json_response(
        {
            'success': True,
            'data': {
                'messages': messages,
                'last_msg_id': last_msg_id,
                'next_cursor': next_cursor,
                'oldest_date': oldest_date,
                'has_more': has_more,
                'source': 'message_database',
            },
        }
    )


# ──────────── 发送 / 撤回 ────────────


async def handle_send_message(request: web.Request):
    try:
        if request.content_type and 'multipart' in request.content_type:
            reader = await request.multipart()
            fields: dict[str, Any] = {}
            image_data: bytes | None = None
            while True:
                part = await reader.next()
                if part is None:
                    break
                if not isinstance(part, BodyPartReader):
                    continue
                field_name = part.name or ''
                if field_name == 'image':
                    image_data = await part.read()
                elif field_name:
                    fields[field_name] = (await part.read()).decode('utf-8', errors='replace')
        else:
            fields = await json_body(request)
            image_data = None

        chat_type = fields.get('chat_type', '')
        chat_id = str(fields.get('chat_id', ''))
        bot_qq = str(fields.get('bot_qq') or fields.get('self_id') or _primary_id())
        msg_type = fields.get('msg_type', 'text')
        content = (fields.get('content', '') or '').strip()

        if not chat_type or not chat_id:
            return web.json_response({'success': False, 'message': '缺少 chat_type/chat_id'}, status=400)
        if not content and not image_data:
            return web.json_response({'success': False, 'message': '消息内容为空'}, status=400)
        if not _common.connected_ids():
            return web.json_response({'success': False, 'message': '无可用机器人连接'}, status=400)

        # 构造 OneBot 消息段
        segments = []
        if content:
            if msg_type == 'media':
                segments.append({'type': 'image', 'data': {'file': content}})
            else:
                segments.append({'type': 'text', 'data': {'text': content}})
        if image_data:
            import base64

            b64 = base64.b64encode(image_data).decode()
            segments.append({'type': 'image', 'data': {'file': f'base64://{b64}'}})

        api = _api()
        if chat_type == 'group':
            resp = await api.send_group_msg(chat_id, segments, self_id=bot_qq)
        else:
            resp = await api.send_private_msg(chat_id, segments, self_id=bot_qq)

        if resp and resp.get('retcode') == 0:
            return web.json_response({'success': True, 'message': '发送成功'})
        err = (resp or {}).get('message') or (resp or {}).get('wording') or '发送失败'
        return web.json_response({'success': False, 'message': str(err)})
    except Exception as e:
        import traceback

        traceback.print_exc()
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def handle_recall_message(request: web.Request):
    try:
        body = await json_body(request)
    except Exception:
        body = {}
    message_id = body.get('message_id', '')
    bot_qq = str(body.get('bot_qq') or body.get('self_id') or _primary_id())
    if not message_id:
        return web.json_response({'success': False, 'message': '参数缺失'}, status=400)
    try:
        resp = await _api().delete_msg(message_id, self_id=bot_qq)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)
    if resp and resp.get('retcode') == 0:
        with contextlib.suppress(Exception):
            await _mark_recalled(message_id, bot_qq)
        return web.json_response({'success': True})
    return web.json_response({'success': False, 'message': '撤回失败'})


async def _mark_recalled(message_id, bot_qq=''):
    svc = _common.log_service()
    if not svc:
        return
    with contextlib.suppress(Exception):
        await svc.execute('message', "UPDATE log SET extra='recalled' WHERE message_id=?", (str(message_id),), bot_qq=str(bot_qq or _primary_id()))


# ──────────── 群备注 ────────────

_remarks_cache = None
_remarks_ts = 0.0


def _remarks_path():
    return os.path.join(_base_dir, 'data', 'group_remarks.json')


def _remark_name(val):
    if isinstance(val, dict):
        return val.get('name', '')
    return str(val) if val else ''


def _remark_qq(val):
    return val.get('qq', '') if isinstance(val, dict) else ''


def _load_remarks() -> dict:
    global _remarks_cache, _remarks_ts
    now = time.time()
    if _remarks_cache is not None and now - _remarks_ts < 60:
        return _remarks_cache
    path = _remarks_path()
    data = {}
    if os.path.isfile(path):
        with contextlib.suppress(Exception), open(path, encoding='utf-8') as f:
            d = json.load(f)
            data = d if isinstance(d, dict) else {}
    _remarks_cache = data
    _remarks_ts = now
    return data


def _save_remarks(remarks):
    global _remarks_cache, _remarks_ts
    path = _remarks_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(remarks, f, ensure_ascii=False, indent=2)
    _remarks_cache = remarks
    _remarks_ts = time.time()


async def handle_get_remarks(request: web.Request):
    return web.json_response({'success': True, 'data': await asyncio.to_thread(_load_remarks)})


async def handle_set_remark(request: web.Request):
    body = await json_body(request)
    gid = str(body.get('group_id', '') or body.get('chat_id', ''))
    name = body.get('name', '') or body.get('remark', '')
    qq = body.get('qq', '')
    if not gid:
        return web.json_response({'success': False, 'message': '缺少群号'}, status=400)
    remarks = dict(await asyncio.to_thread(_load_remarks))
    remarks[gid] = {'name': name, 'qq': qq}
    await asyncio.to_thread(_save_remarks, remarks)
    _chat_cache.clear()
    return web.json_response({'success': True})


async def handle_delete_remark(request: web.Request):
    body = await json_body(request)
    gid = str(body.get('group_id', '') or body.get('chat_id', ''))
    remarks = dict(await asyncio.to_thread(_load_remarks))
    if gid in remarks:
        del remarks[gid]
        await asyncio.to_thread(_save_remarks, remarks)
        _chat_cache.clear()
    return web.json_response({'success': True})


async def handle_get_group_roles(request: web.Request):
    return web.json_response({'success': True, 'data': {}})
