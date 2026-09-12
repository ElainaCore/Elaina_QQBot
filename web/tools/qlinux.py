"""QLinux 渠道 Web API — 账号管理、扫码登录、验证码提交。"""

from __future__ import annotations

import logging

from aiohttp import web

from web.protocol import error, json_body, ok
from web.tools._common import get_app

log = logging.getLogger('ElainaQQ.web.qlinux')


def _manager(request: web.Request):
    app = get_app()
    mgr = getattr(app, 'qlinux', None) if app else None
    return mgr


async def handle_qlinux_accounts(request: web.Request) -> web.Response:
    """GET /api/qlinux/accounts — 账号列表。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用 (settings.qlinux.enabled)', status=404)
    accounts = mgr.list_accounts()
    if mgr._rpc is None or not mgr._rpc.alive:
        # runner 未启动时异步拉起 (首启自动下载, 不阻塞响应)
        import asyncio
        asyncio.get_running_loop().create_task(mgr.ensure_started())
    return ok(accounts=accounts, version=mgr_version(mgr))


def mgr_version(mgr) -> str:
    from core.runtime.qlinux.runner import RUNNER_VERSION
    return RUNNER_VERSION


async def handle_qlinux_create(request: web.Request) -> web.Response:
    """POST /api/qlinux/create {bot_id} — 创建 Linux 协议账号实例。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or '').strip()
    if not bot_id or not bot_id.replace('-', '').replace('_', '').isalnum():
        return error('bot_id 必须是字母/数字/下划线/连字符')
    if len(bot_id) > 80:
        return error('bot_id 长度不能超过 80 个字符')
    if bot_id in {a['bot_id'] for a in mgr.list_accounts()}:
        return error('账号 ID 已存在')
    acc = await mgr.create_account(bot_id)
    return ok(bot_id=acc.get('bot_id', bot_id), message='QLinux 账号已创建')


async def handle_qlinux_login_qr(request: web.Request) -> web.Response:
    """POST /api/qlinux/login/qr {bot_id} — 发起扫码登录。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or '').strip()
    if bot_id not in {a['bot_id'] for a in mgr.list_accounts()}:
        return error('账号不存在')
    result = await mgr.login_qr(bot_id)
    already_running = bool(result.get('already_running'))
    return ok(
        {
            'started': bool(result.get('started', True)),
            'already_running': already_running,
            'bot_id': bot_id,
        },
        message='登录流程已在进行, 请轮询 /api/qlinux/qr 获取'
        if already_running else '二维码生成中, 请轮询 /api/qlinux/qr 获取',
    )


async def handle_qlinux_login_password(request: web.Request) -> web.Response:
    """POST /api/qlinux/login/password {bot_id, uin, password} — 账密登录。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or '').strip()
    try:
        uin = int(body.get('uin') or 0)
    except (TypeError, ValueError):
        return error('uin 必须是数字', status=400)
    password = str(body.get('password') or '')
    if len(bot_id) > 80 or not bot_id or uin <= 0 or not password:
        return error('bot_id / uin / password 参数无效', status=400)
    if len(password) > 1024:
        return error('密码长度不能超过 1024 个字符', status=400)
    if bot_id not in {a['bot_id'] for a in mgr.list_accounts()}:
        return error('账号不存在', status=404)
    result = await mgr.login_password(bot_id, uin, password)
    return ok({'started': bool(result.get('started', True)), 'bot_id': bot_id},
              message='登录流程已发起, 可能需要验证码')


async def handle_qlinux_qr(request: web.Request) -> web.Response:
    """GET /api/qlinux/qr?bot_id=xxx — 获取当前二维码 (PNG base64) 与状态。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    bot_id = request.query.get('bot_id', '')
    cache = mgr.get_qr_image(bot_id)
    if not cache:
        return error('暂无二维码 (尚未发起扫码登录或已过期)')
    acc = next((a for a in mgr.list_accounts() if a['bot_id'] == bot_id), {})
    return ok(png_base64=cache.get('png_base64', ''), url=cache.get('url', ''),
              status=acc.get('status', ''), state=acc.get('last_state'),
              error=acc.get('last_error'))


async def handle_qlinux_submit(request: web.Request) -> web.Response:
    """POST /api/qlinux/submit {bot_id, type: captcha|sms, ticket, randstr, code}"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or '').strip()
    submit_type = str(body.get('type') or '')
    try:
        if bot_id not in {a['bot_id'] for a in mgr.list_accounts()}:
            return error('账号不存在', status=404)
        if submit_type == 'captcha':
            ticket = str(body.get('ticket') or '')
            randstr = str(body.get('randstr') or '')
            if not ticket or len(ticket) > 4096 or len(randstr) > 1024:
                return error('验证码参数无效', status=400)
            result = await mgr.submit_captcha(
                bot_id, ticket, randstr)
        elif submit_type == 'sms':
            code = str(body.get('code') or '')
            if not code or len(code) > 32:
                return error('短信验证码无效', status=400)
            result = await mgr.submit_sms(bot_id, code)
        else:
            return error('type 必须是 captcha 或 sms')
    except Exception as e:  # noqa: BLE001
        return error(str(e))
    return ok(**(result or {}), message='验证码已提交')


async def handle_qlinux_stop(request: web.Request) -> web.Response:
    """POST /api/qlinux/stop {bot_id} — 下线账号 (保留 keystore)。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or '').strip()
    if bot_id not in {a['bot_id'] for a in mgr.list_accounts()}:
        return error('账号不存在')
    result = await mgr.stop_account(bot_id)
    return ok(**(result or {}), message='账号已下线')


async def handle_qlinux_delete(request: web.Request) -> web.Response:
    """POST /api/qlinux/delete {bot_id} — 删除账号 (清 keystore)。"""
    mgr = _manager(request)
    if mgr is None:
        return error('QLinux 渠道未启用', status=404)
    body = await json_body(request)
    bot_id = str(body.get('bot_id') or '').strip()
    if bot_id not in {a['bot_id'] for a in mgr.list_accounts()}:
        return error('账号不存在')
    result = await mgr.delete_account(bot_id)
    return ok(**(result or {}), message='账号已删除')
