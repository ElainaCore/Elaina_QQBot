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


def set_context(app_instance, base_dir=''):
    global _base_dir
    _common.set_app(app_instance)
    if base_dir:
        _base_dir = base_dir


def _api():
    from core.onebot.api import get_api

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
        data = segment.get('data') if isinstance(segment.get('data'), dict) else {}
        if kind == 'text':
            parts.append(str(data.get('text') or ''))
        elif kind == 'at':
            parts.append('@' + str(data.get('name') or data.get('qq') or ''))
        elif kind != 'reply':
            parts.append(labels.get(kind, f'[{kind}]' if kind else ''))
    return ''.join(parts).strip()


async def _fetch_directory(api, chat_type: str, bot_qq: str) -> dict[str, dict]:
    try:
        response = (
            await api.get_friend_list(self_id=bot_qq)
            if chat_type == 'user'
            else await api.get_group_list(self_id=bot_qq)
        )
    except Exception:
        return {}
    result = {}
    for item in _onebot_data(response, []) or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get('user_id') if chat_type == 'user' else item.get('group_id') or '')
        if key:
            result[key] = item
    return result


def _directory_chats(chat_type: str, directory: dict[str, dict], bot_qq: str) -> list[dict]:
    """仅在最近会话扩展不可用时提供基础列表，绝不回读框架日志库。"""
    remarks = _load_remarks()
    chats = []
    for chat_id, item in directory.items():
        remark = item.get('remark', '') if chat_type == 'user' else _remark_name(remarks.get(chat_id))
        name = remark or item.get('nickname') or item.get('group_name') or chat_id
        chats.append(
            {
                'chat_id': chat_id,
                'bot_qq': bot_qq,
                'nickname': str(name),
                'remark': str(remark or ''),
                'group_qq': _remark_qq(remarks.get(chat_id)) if chat_type == 'group' else '',
                'last_time': '',
                'last_date': '',
                'last_content': '',
                'msg_count': 0,
                'source': 'onebot_directory',
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

    recent_response, directory = await asyncio.gather(get_recent(), _fetch_directory(api, chat_type, bot_qq))
    if not _onebot_ok(recent_response):
        return _directory_chats(chat_type, directory, bot_qq)

    remarks = _load_remarks()
    today = datetime.now().strftime('%Y-%m-%d')
    wanted_type = 2 if chat_type == 'group' else 1
    chats_by_id = {}
    for contact in _onebot_data(recent_response, []) or []:
        if not isinstance(contact, dict) or int(contact.get('chatType') or 0) != wanted_type:
            continue
        chat_id = str(contact.get('peerUin') or '')
        if not chat_id or not chat_id.isdigit():
            continue
        latest = contact.get('lastestMsg') if isinstance(contact.get('lastestMsg'), dict) else {}
        last_time = _timestamp_text(contact.get('msgTime') or latest.get('time'))
        if not last_time.startswith(today):
            continue
        directory_item = directory.get(chat_id, {})
        if chat_type == 'group':
            remark = _remark_name(remarks.get(chat_id))
            name = remark or contact.get('peerName') or directory_item.get('group_name') or chat_id
        else:
            remark = contact.get('remark') or directory_item.get('remark') or ''
            name = remark or contact.get('peerName') or directory_item.get('nickname') or contact.get('sendNickName') or chat_id
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
            'msg_count': 0,
            'source': 'qq_native',
        }
        previous = chats_by_id.get(chat_id)
        if previous is None or candidate['last_time'] > previous['last_time']:
            chats_by_id[chat_id] = candidate

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
    page_size = _bounded_int(body.get('page_size'), 100, 1, 100)

    now = time.time()
    bot_ids = [requested_bot_qq] if requested_bot_qq else _common.connected_ids()
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


async def _normalize_history(events: list, bot_qq: str) -> list[dict[str, Any]]:
    parsed = []
    missing_names = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        sender = event.get('sender') if isinstance(event.get('sender'), dict) else {}
        user_id = str(event.get('user_id') or sender.get('user_id') or '')
        is_self = bool(bot_qq and user_id == bot_qq)
        nickname = str(sender.get('card') or sender.get('nickname') or '')
        if user_id and not is_self and not nickname:
            missing_names.add(user_id)
        parsed.append((event, sender, user_id, is_self, nickname))

    nicknames = await _common.batch_nicknames(missing_names, bot_qq) if missing_names else {}
    messages = []
    for index, (event, sender, user_id, is_self, nickname) in enumerate(parsed):
        segments = event.get('message') if isinstance(event.get('message'), list) else []
        reply = next((item for item in segments if isinstance(item, dict) and item.get('type') == 'reply'), None)
        message_id = str(event.get('message_id') or '')
        timestamp = _timestamp_text(event.get('time'))
        messages.append(
            {
                'id': f'{bot_qq}:{message_id or _event_cursor(event) or index}',
                'message_id': message_id,
                'message_seq': _event_cursor(event),
                'reference_id': str(((reply or {}).get('data') or {}).get('id') or ''),
                'user_id': user_id,
                'bot_qq': bot_qq,
                'nickname': (bot_qq or 'Bot') if is_self else nickname or nicknames.get(user_id, user_id),
                'content': _segment_content(segments) or str(event.get('raw_message') or ''),
                'timestamp': timestamp,
                'is_self': is_self,
                'role': str(sender.get('role') or ''),
                'source': 'qq_native',
                'raw_message': json.dumps(event, ensure_ascii=False),
                'recalled': False,
                '_epoch': _event_epoch(event),
            }
        )
    messages.sort(key=lambda item: (item['_epoch'], item['message_seq']))
    for message in messages:
        message.pop('_epoch', None)
    return messages


async def handle_get_chat_history(request: web.Request):
    try:
        body = await json_body(request)
    except Exception:
        body = {}
    chat_type = body.get('chat_type', 'group')
    chat_id = str(body.get('chat_id', ''))
    bot_qq = str(body.get('bot_qq') or _primary_id())
    if not chat_id:
        return web.json_response({'success': True, 'data': {'messages': [], 'has_more': False}})

    if chat_type not in ('group', 'user'):
        chat_type = 'group'
    cursor = str(body.get('before_seq') or body.get('cursor') or body.get('message_seq') or '')
    count = _bounded_int(body.get('count'), 50, 1, 100)
    api = _api()
    try:
        if chat_type == 'group':
            response = await api.get_group_msg_history(chat_id, cursor or 0, count, False, self_id=bot_qq)
        else:
            response = await api.get_friend_msg_history(chat_id, cursor or 0, count, False, self_id=bot_qq)
    except Exception:
        response = None

    data = _onebot_data(response, {})
    events = data.get('messages', []) if isinstance(data, dict) else []
    normalized = await _normalize_history(events, bot_qq)
    today = datetime.now().strftime('%Y-%m-%d')
    if not cursor:
        messages = [item for item in normalized if item['timestamp'].startswith(today)]
        hidden_older = len(messages) != len(normalized)
        has_more = hidden_older or len(events) >= count
    else:
        messages = normalized
        has_more = len(events) >= count

    next_cursor = ''
    if messages:
        next_cursor = str(messages[0].get('message_seq') or '')
    elif normalized:
        next_cursor = str(normalized[0].get('message_seq') or '')
    if cursor and next_cursor == cursor and len(messages) <= 1:
        has_more = False

    last_msg_id = next((item['message_id'] for item in reversed(messages) if not item['is_self']), '')
    oldest_date = messages[0]['timestamp'][:10] if messages else today
    return web.json_response(
        {
            'success': True,
            'data': {
                'messages': messages,
                'last_msg_id': last_msg_id,
                'next_cursor': next_cursor,
                'oldest_date': oldest_date,
                'has_more': has_more,
                'source': 'qq_native',
            },
        }
    )


# ──────────── 发送 / 撤回 ────────────


async def _log_sent(chat_type, chat_id, content, message_id, bot_qq=''):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    bot_qq = str(bot_qq or _primary_id())
    svc = _common.log_service()
    if svc:
        await svc.add(
            'message',
            {
                'timestamp': ts,
                'content': content,
                'user_id': '' if chat_type == 'group' else chat_id,
                'group_id': chat_id if chat_type == 'group' else '',
                'message_id': str(message_id or ''),
                'message_type': chat_type,
                'source': 'WebPanel',
                'extra': 'send',
            },
            bot_qq=bot_qq,
        )
    # 实时推送到 Web 面板
    from web.ws import push_log

    push_log(
        'message',
        {
            'timestamp': ts,
            'content': content,
            'user_id': '' if chat_type == 'group' else chat_id,
            'group_id': chat_id if chat_type == 'group' else '',
            'message_id': str(message_id or ''),
            'message_type': chat_type,
            'bot_qq': bot_qq,
            'direction': 'send',
            'raw_message': '',
        },
    )


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
        adapter = _common.adapter()
        local_actions = getattr(adapter, 'local_actions', {}) if adapter else {}
        is_embedded = bot_qq in local_actions
        if chat_type == 'group':
            resp = await api.send_group_msg(chat_id, segments, self_id=bot_qq)
        else:
            resp = await api.send_private_msg(chat_id, segments, self_id=bot_qq)

        if resp and resp.get('retcode') == 0:
            if not is_embedded:
                mid = (resp.get('data') or {}).get('message_id', '')
                display = content or '[图片]'
                await _log_sent(chat_type, chat_id, display, mid, bot_qq)
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
    return web.json_response({'success': True, 'data': _load_remarks()})


async def handle_set_remark(request: web.Request):
    body = await json_body(request)
    gid = str(body.get('group_id', '') or body.get('chat_id', ''))
    name = body.get('name', '') or body.get('remark', '')
    qq = body.get('qq', '')
    if not gid:
        return web.json_response({'success': False, 'message': '缺少群号'}, status=400)
    remarks = dict(_load_remarks())
    remarks[gid] = {'name': name, 'qq': qq}
    _save_remarks(remarks)
    _chat_cache.clear()
    return web.json_response({'success': True})


async def handle_delete_remark(request: web.Request):
    body = await json_body(request)
    gid = str(body.get('group_id', '') or body.get('chat_id', ''))
    remarks = dict(_load_remarks())
    if gid in remarks:
        del remarks[gid]
        _save_remarks(remarks)
        _chat_cache.clear()
    return web.json_response({'success': True})


async def handle_get_group_roles(request: web.Request):
    return web.json_response({'success': True, 'data': {}})
