"""机器人列表 / 详情 (OneBot 适配)"""

import asyncio
import os
import time
from typing import Any

from aiohttp import web

from core.foundation.config import cfg
from core.plugins import get_api
from web.protocol import error, json_body, ok
from web.tools import _common

_app = None
_login_cache: dict[str, tuple[float, dict]] = {}
_LOGIN_TTL = 60


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
        async with asyncio.timeout(5):
            resp = await get_api().call_api('get_login_info', self_id=self_id)
        if resp and resp.get('retcode') == 0:
            info = resp.get('data') or {}
    except Exception:
        info = {}
    _login_cache[self_id] = (now, info)
    return info


def _avatar(qq: str) -> str:
    return f'https://q1.qlogo.cn/g?b=qq&nk={qq}&s=100' if qq else ''


async def handle_get_bots(request: web.Request):
    prune = getattr(_app, 'prune_hook_bridges', None)
    if callable(prune):
        await prune()
    api = get_api()
    # The adapter only exposes accounts that are currently connected. Keep the
    # embedded manager's persisted accounts as well, otherwise a newly-created
    # offline QQ account disappears from the panel after the create request.
    adapter_bots = api.bot_accounts() if api else []
    manager = getattr(_app, 'embedded_qq', None)
    embedded_bots = manager.list_bots() if manager else []

    def account_keys(item: dict) -> set[str]:
        return {
            str(item.get(key) or '').strip()
            for key in ('bot_id', 'self_id', 'bot_qq', 'qq', 'uin')
            if str(item.get(key) or '').strip()
        }

    bots = []
    remaining = list(adapter_bots)
    for embedded in embedded_bots:
        embedded_keys = account_keys(embedded)
        match_index = next(
            (index for index, item in enumerate(remaining) if embedded_keys & account_keys(item)),
            None,
        )
        if match_index is None:
            bots.append(dict(embedded))
            continue
        adapter_item = remaining.pop(match_index)
        # Keep the embedded account identity and lifecycle fields while adding
        # any live adapter fields (aliases, channel and connection state).
        bots.append({**adapter_item, **embedded})
    bots.extend(remaining)
    for item in bots:
        self_id = str(item.get('self_id') or item.get('bot_qq') or item.get('qq') or '')
        info = await _login_info(self_id)
        item['name'] = str(info.get('nickname') or item.get('name') or self_id)
        item['user_id'] = info.get('user_id') or item.get('user_id') or self_id
        item['bot_qq'] = self_id
        item['qq'] = self_id
        item['avatar'] = _avatar(self_id)
        item['connected'] = bool(item.get('connected', True))
        item['enabled'] = item['connected']
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
    if os.name == 'nt' and str(body.get('runtime_mode') or '') != 'hookqq':
        return error('Windows 内置账号必须使用 HookQQ 模式')
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
    if os.name == 'nt' and not bool(cfg.get('settings', 'embedded_qq.windows_hook_launch', False)):
        # 这是用户显式选择内置 HookQQ 的时刻；普通注入流程不会修改此项，
        cfg.set_value('settings', 'embedded_qq.windows_hook_launch', True)
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
