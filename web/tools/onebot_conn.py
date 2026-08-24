"""OneBot 网络连接配置 — 读取/保存 connections.yaml, 查询连接状态"""

import logging

from aiohttp import web

from core.foundation.config import cfg
from core.protocols.onebot.connection import CONN_TYPES, default_connections, normalize
from web.protocol import error, json_body, ok

log = logging.getLogger('ElainaQQ.web.onebot_conn')

_app = None


def set_context(app_instance):
    global _app
    _app = app_instance


def _current_connections():
    conns = cfg.get('connections', 'connections', None)
    if not conns or not isinstance(conns, list):
        conns = default_connections()
    return [normalize(c) for c in conns if isinstance(c, dict)]


def _sanitize(conn: dict) -> dict:
    """仅保留合法字段写入配置"""
    c = normalize(conn)
    out = {
        'type': c['type'] if c['type'] in CONN_TYPES else 'ws_reverse',
        'name': str(c['name'] or c['type']),
        'enable': bool(c['enable']),
    }
    if out['type'] in ('ws_reverse', 'http_server'):
        out['host'] = str(c.get('host') or '0.0.0.0')
        out['port'] = int(c.get('port') or 5201)
        out['path'] = str(c.get('path') or '/')
    if out['type'] in ('ws_forward', 'http_client'):
        out['url'] = str(c.get('url') or '')
    out['token'] = str(c.get('token') or '')
    if out['type'] == 'http_server':
        out['secret'] = str(c.get('secret') or '')
    if out['type'] == 'ws_forward':
        out['reconnect_interval'] = int(c.get('reconnect_interval') or 5000)
    return out


async def handle_get_connections(request: web.Request):
    """获取连接配置 + 运行状态"""
    conns = _current_connections()
    status = []
    if _app and _app.connection_manager:
        try:
            status = _app.connection_manager.status()
        except Exception as e:
            log.warning(f'获取连接状态失败: {e}')
    return ok(
        connections=conns,
        status=status,
        server={
            'host': cfg.get('settings', 'server.host', '0.0.0.0'),
            'port': cfg.get('settings', 'server.port', 5201),
        },
    )


async def handle_save_connections(request: web.Request):
    """保存连接配置并热重载"""
    body = await json_body(request)

    conns = body.get('connections')
    if not isinstance(conns, list):
        return error('connections 必须为数组')

    cleaned = []
    names = set()
    for c in conns:
        if not isinstance(c, dict):
            continue
        item = _sanitize(c)
        if item['type'] in ('ws_forward', 'http_client') and not item['url']:
            return error(f'连接 [{item["name"]}] 缺少 URL')
        name = item['name']
        if name in names:
            return error(f'连接名称重复: {name}')
        names.add(name)
        cleaned.append(item)

    cfg.set_value('connections', 'connections', cleaned)

    if _app:
        try:
            await _app.reload_connections()
        except Exception as e:
            log.warning(f'重载连接失败: {e}')
            return error(f'已保存但重载失败: {e}', status=500)

    status = _app.connection_manager.status() if (_app and _app.connection_manager) else []
    return ok(message='连接配置已保存', connections=cleaned, status=status)
