"""机器人列表 / 详情 (OneBot 适配)"""

import time
from typing import Any

from aiohttp import web

from web.protocol import error, json_body, ok
from web.tools import _common

_app = None
_login_cache: dict[str, tuple[float, dict]] = {}
_LOGIN_TTL = 60
_BOT_IDENTITY_FIELDS = ('bot_id', 'bot_qq', 'qq', 'uin')


def set_context(app_instance):
    global _app
    _app = app_instance
    _common.set_app(app_instance)


async def _login_info(self_id: str) -> dict:
    now = time.time()
    c = _login_cache.get(self_id)
    if c and now - c[0] < _LOGIN_TTL:
        return c[1]
    info: dict[str, Any] = {}
    try:
        from core.protocols.onebot.api import OneBotAPI

        resp = await OneBotAPI(_common.adapter()).call_api('get_login_info', self_id=self_id)
        if resp and resp.get('retcode') == 0:
            info = resp.get('data') or {}
    except Exception:
        info = {}
    _login_cache[self_id] = (now, info)
    return info


def _avatar(qq: str) -> str:
    return f'https://q1.qlogo.cn/g?b=qq&nk={qq}&s=100' if qq else ''


def _conn_type(ad, self_id: str) -> str:
    """依据适配器记录判断连接方式 (WebSocket 优先于 HTTP)"""
    if self_id in ad.local_actions:
        return '注入 QQ'
    if self_id in ad.websockets:
        return 'WebSocket'
    rec = ad.bots.get(self_id) or {}
    return 'WebSocket' if rec.get('type') == 'websocket' else 'HTTP'


def _bot_identities(item) -> set[str]:
    """返回内置账号的临时编号、真实 QQ 等全部身份别名。"""
    values = (item.get(key) for key in _BOT_IDENTITY_FIELDS) if isinstance(item, dict) else (getattr(item, key, '') for key in _BOT_IDENTITY_FIELDS)
    return {str(value).strip() for value in values if value}


async def handle_get_bots(request: web.Request):
    ad = _common.adapter()
    bots = []
    manager = getattr(_app, 'embedded_qq', None)
    embedded_ids = set()
    if manager:
        embedded_bots = manager.list_bots()
        bots.extend(embedded_bots)
        # 登录过程中 bot_id 可能暂时不同于真实 QQ，所有别名都视为同一账号。
        for item in embedded_bots:
            embedded_ids.update(_bot_identities(item))
        for bot in getattr(manager, 'bots', {}).values():
            embedded_ids.update(_bot_identities(bot))
    if ad:
        for self_id in _common.connected_ids():
            self_id = str(self_id)
            if self_id in embedded_ids:
                continue
            conn_type = _conn_type(ad, self_id)
            connected = self_id in ad.local_actions or self_id in ad.websockets or conn_type == 'WebSocket'
            info = await _login_info(self_id) if connected else {}
            name = info.get('nickname', '') or self_id
            hook_status = next(
                (
                    status
                    for status in getattr(_app, 'hook_bridges', lambda: [])()
                    if str(status.get('uin') or '') == self_id
                ),
                {},
            )
            bots.append(
                {
                    'bot_qq': self_id,
                    'name': name,
                    'qq': self_id,
                    'avatar': _avatar(self_id),
                    'connected': connected,
                    'connection_type': conn_type,
                    'runtime_mode': conn_type,
                    'pid': hook_status.get('pid'),
                    'enabled': True,
                }
            )
    for item in bots:
        qq = str(item.get('bot_qq') or item.get('qq') or '')
        item.setdefault('qq', qq)
        item.setdefault('avatar', _avatar(qq))
    return ok(bots=bots)


async def handle_toggle_bot(request: web.Request):
    body = await json_body(request)
    manager = getattr(_app, 'embedded_qq', None)
    if not manager:
        return error('内置 QQ 未启用')
    bot_qq = str(body.get('bot_qq') or '')
    bot = next((item for item in manager.bots.values() if item.bot_id == bot_qq or item.uin == bot_qq), None)
    if not bot:
        return error('账号不存在', status=404)
    if body.get('enabled', True):
        bot.enabled = True
        await manager.start(bot.bot_id)
    else:
        bot.enabled = False
        await manager.stop(bot.bot_id)
    await manager._save_accounts()
    return ok()


async def handle_create_embedded_bot(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    if not manager:
        return error('内置 QQ 未启用')
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or body.get('uin') or '').strip()
    if not bot_id:
        return error('缺少 bot_id')
    try:
        bot = await manager.create_bot(
            bot_id,
            str(body.get('nickname') or ''),
            str(body.get('uin') or ''),
            str(body.get('qq_version_key') or ''),
            bool(body.get('force_quick_login', False)),
        )
    except ValueError as exc:
        return error(str(exc))
    return ok(bot=next(item for item in manager.list_bots() if item['bot_id'] == bot.bot_id))


async def handle_set_embedded_version(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    if not manager:
        return error('内置 QQ 未启用')
    body = await json_body(request)
    try:
        bot = await manager.set_bot_version(
            str(body.get('bot_id') or '').strip(),
            str(body.get('qq_version_key') or '').strip(),
        )
    except ValueError as exc:
        return error(str(exc))
    payload = next(item for item in manager.list_bots() if item['bot_id'] == bot.bot_id)
    return ok(bot=payload)


async def handle_set_embedded_quick_login(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    if not manager:
        return error('内置 QQ 未启用')
    body = await json_body(request)
    try:
        bot = await manager.set_force_quick_login(
            str(body.get('bot_id') or '').strip(),
            bool(body.get('enabled', False)),
        )
    except ValueError as exc:
        return error(str(exc))
    payload = next(item for item in manager.list_bots() if item['bot_id'] == bot.bot_id)
    return ok(bot=payload)


async def handle_start_embedded_bot(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or body.get('uin') or '')
    if not manager or not bot_id:
        return error('参数错误')
    bot = await manager.start(bot_id)
    payload = next(item for item in manager.list_bots() if item['bot_id'] == bot_id)
    if bot.status == 'not_installed':
        return ok(
            started=False,
            code='qq_not_installed',
            message='请先在机器人页面安装 QQ',
            bot=payload,
        )
    if bot.status == 'error':
        return error(bot.error or 'QQ 启动失败', status=502, started=False, bot=payload)
    return ok(started=True, bot=payload)


async def handle_stop_embedded_bot(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or body.get('uin') or '')
    if not manager or not bot_id:
        return error('参数错误')
    await manager.stop(bot_id)
    return ok()


async def handle_delete_embedded_bot(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    if not manager:
        return error('内置 QQ 未启用')
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or body.get('uin') or '').strip()
    if not bot_id:
        return error('参数错误')
    deleted = await manager.delete_bot(bot_id, cleanup_data=bool(body.get('cleanup_data', False)))
    if not deleted:
        return error('账号不存在', status=404)
    return ok(message='QQ 账号已删除')


async def handle_get_embedded_status(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    return ok(bots=manager.list_bots() if manager else [], enabled=bool(manager))


async def handle_refresh_embedded_qr(request: web.Request):
    manager = getattr(_app, 'embedded_qq', None)
    if not manager:
        return error('内置 QQ 未启用')
    try:
        body = await json_body(request)
    except ValueError:
        body = {}
    bot_id = str(body.get('bot_id') or body.get('uin') or '').strip()
    if not bot_id:
        return error('参数错误')
    result = await manager.refresh_qr(bot_id)
    if not result.get('success'):
        return error(result.get('error') or '二维码刷新失败', status=502, result=result)
    return ok(result=result)
