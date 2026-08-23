"""日志查询 — 最近日志 / 分页 / 登录日志 (异步架构)"""

import contextlib
import json

from aiohttp import web

import web.auth as auth
from core.onebot.event_labels import event_label
from web.protocol import json_body
from web.tools import _common

_RECENT_LIMIT = 200
_LOG_SQL = f'SELECT * FROM log ORDER BY id DESC LIMIT {_RECENT_LIMIT}'


def set_context(app_instance):
    _common.set_app(app_instance)


async def _query_recent(log_type: str, bot_qq: str = '') -> list:
    rows = await _common.query_log(log_type, _LOG_SQL, bot_qq=bot_qq)
    rows.reverse()  # 升序: 旧 → 新
    return rows


def _transform_message_rows(rows: list, bot_qq: str = '') -> list:
    """将 DB 行转换为前端 Logs.vue 期望的字段格式"""
    result = []
    for r in rows:
        extra = r.get('extra', '')
        direction = 'send' if extra == 'send' else 'receive'
        bot_id = r.get('source', '') or bot_qq
        result.append(
            {
                'timestamp': r.get('timestamp', ''),
                'content': r.get('content', ''),
                'user_id': r.get('user_id', ''),
                'group_id': r.get('group_id', ''),
                'message_id': r.get('message_id', ''),
                'message_type': r.get('message_type', ''),
                'bot_qq': bot_id,
                'direction': direction,
                'raw_message': r.get('raw_data', ''),
            }
        )
    return result


def _transform_lifecycle_rows(rows: list, bot_qq: str = '') -> list:
    """将事件(通知)DB 行转换为前端「事件」面板期望的字段格式"""
    result = []
    for r in rows:
        event_type = r.get('message_type', '')
        raw_data = r.get('raw_data', '')
        sub_type = ''
        if raw_data:
            with contextlib.suppress(TypeError, ValueError):
                sub_type = str((json.loads(raw_data) or {}).get('sub_type') or '')
        result.append({
            'timestamp': r.get('timestamp', ''),
            'type': event_type,
            'event_type': event_type,
            'type_label': event_label(event_type, sub_type),
            'user_id': r.get('user_id', ''),
            'group_id': r.get('group_id', ''),
            'bot_qq': r.get('source', '') or bot_qq,
            'content': r.get('content', ''),
            'raw_message': raw_data,
        })
    return result


async def handle_recent_logs(request: web.Request):
    requested = str(request.query.get('bot_qq') or '')
    bot_ids = [requested] if requested else _common.bot_ids()
    if not bot_ids:
        bot_ids = [_common.primary_bot_qq()]
    msg_rows, lc_rows = [], []
    for bot_qq in bot_ids:
        msg_rows.extend(await _query_recent('message', bot_qq=bot_qq))
        lc_rows.extend(await _query_recent('lifecycle', bot_qq=bot_qq))
    msg_rows.sort(key=lambda row: row.get('timestamp', ''))
    lc_rows.sort(key=lambda row: row.get('timestamp', ''))
    fallback_bot = requested or (bot_ids[0] if len(bot_ids) == 1 else '')
    payload = {
        'message': _transform_message_rows(msg_rows, fallback_bot),
        'framework': await _query_recent('framework'),
        'error': await _query_recent('error'),
        'lifecycle': _transform_lifecycle_rows(lc_rows, fallback_bot),
    }
    return web.json_response(payload)


async def handle_get_logs(request: web.Request):
    log_type = request.match_info.get('log_type', 'message')
    if log_type not in ('message', 'framework', 'error', 'lifecycle'):
        return web.json_response({'error': '无效的日志类型'}, status=400)

    page = int(request.query.get('page', '1'))
    page_size = int(request.query.get('size', '50'))
    offset = (page - 1) * page_size

    requested = str(request.query.get('bot_qq') or '')
    bot_ids = [requested] if requested else _common.bot_ids()
    if log_type in ('message', 'lifecycle'):
        if not bot_ids:
            bot_ids = [_common.primary_bot_qq()]
        rows = []
        for bot_qq in bot_ids:
            rows.extend(await _common.query_log(log_type, 'SELECT * FROM log ORDER BY id DESC', bot_qq=bot_qq))
        rows.sort(key=lambda row: (row.get('timestamp', ''), row.get('id', 0)), reverse=True)
        total = len(rows)
        rows = rows[offset : offset + page_size]
    else:
        rows = await _common.query_log(
            log_type,
            f'SELECT * FROM log ORDER BY id DESC LIMIT {page_size} OFFSET {offset}',
        )
        total_rows = await _common.query_log(log_type, 'SELECT MAX(id) AS cnt FROM log')
        total = (total_rows[0].get('cnt') or 0) if total_rows else 0
    if log_type == 'lifecycle':
        rows = _transform_lifecycle_rows(rows, requested)
    return web.json_response(
        {
            'logs': rows,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size if page_size else 0,
        }
    )


async def handle_get_login_logs(request: web.Request):
    logs = auth.get_login_logs()
    total = len(logs)
    banned = sum(1 for e in logs if e.get('is_banned'))
    return web.json_response(
        {
            'success': True,
            'data': logs,
            'stats': {'total': total, 'banned': banned, 'active': total - banned},
        }
    )


async def handle_unban_ip(request: web.Request):
    try:
        body = await json_body(request)
        ip = body.get('ip', '')
        if not ip:
            return web.json_response({'success': False, 'error': '缺少 IP'}, status=400)
        if auth.unban_ip(ip):
            return web.json_response({'success': True, 'message': f'已解封: {ip}'})
        return web.json_response({'success': False, 'error': 'IP 不存在'}, status=404)
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)


async def handle_delete_ip(request: web.Request):
    try:
        body = await json_body(request)
        ip = body.get('ip', '')
        if not ip:
            return web.json_response({'success': False, 'error': '缺少 IP'}, status=400)
        if auth.delete_ip_record(ip):
            return web.json_response({'success': True, 'message': f'已删除: {ip}'})
        return web.json_response({'success': False, 'error': 'IP 不存在'}, status=404)
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)
