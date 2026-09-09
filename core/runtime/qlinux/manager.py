"""QLinux 渠道管理器 — 账号持久化 + runner 托管 + OneBot 动作绑定。

账号存储: data/qlinux/accounts.json
  [{bot_id, uin, status, created_at, last_online}]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from core.runtime.qlinux.runner import (
    RunnerDownloader,
    RunnerRPC,
    runner_event_to_onebot,
)

log = logging.getLogger('ElainaQQ.qlinux')

_DEFAULT_SIGN_SERVER = 'https://esign.linsur.cn/'


class QLinuxManager:
    """QLinux 渠道总管理器 (由 Application 持有, 生命周期同框架)。"""

    def __init__(self, app):
        self._app = app
        self._base_dir = Path(getattr(app, '_base_dir', '.'))
        self._data_dir = self._base_dir / 'data' / 'qlinux'
        self._bin_dir = self._data_dir / 'bin'
        self._accounts_path = self._data_dir / 'accounts.json'
        self._accounts: dict[str, dict] = {}  # bot_id -> account meta
        self._rpc: RunnerRPC | None = None
        self._downloader: RunnerDownloader | None = None
        self._starting = False
        # 并发请求 (例如账号列表触发后台启动后立即点击扫码) 共享同一次启动，
        # 避免后续请求在 runner 尚未创建时继续执行。
        self._start_task: asyncio.Task | None = None
        self._login_waits: dict[str, asyncio.Future] = {}  # bot_id -> 登录结果等待
        self._registered_uins: set[str] = set()
        self._load_accounts()

    # ---------- 配置 ----------

    def _sign_server(self) -> str:
        try:
            return str(self._app.cfg.get('settings', 'qlinux', {}).get('sign_server')
                       or _DEFAULT_SIGN_SERVER)
        except Exception:  # noqa: BLE001
            return _DEFAULT_SIGN_SERVER

    def enabled(self) -> bool:
        try:
            # 默认开启 (与 Application 装配逻辑一致), 显式 enabled: false 才禁用
            return bool((self._app.cfg.get('settings', 'qlinux', {}) or {}).get('enabled', True))
        except Exception:  # noqa: BLE001
            return True

    # ---------- 账号持久化 ----------

    def _load_accounts(self) -> None:
        if self._accounts_path.is_file():
            try:
                for acc in json.loads(self._accounts_path.read_text(encoding='utf-8')):
                    self._accounts[acc['bot_id']] = acc
            except Exception:  # noqa: BLE001
                log.exception('QLinux 账号文件损坏, 已忽略')

    def _save_accounts(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._accounts_path.write_text(
            json.dumps(list(self._accounts.values()), ensure_ascii=False, indent=2),
            encoding='utf-8')

    # ---------- runner 托管 ----------

    async def ensure_started(self) -> None:
        """启动 runner (如未运行); 二进制缺失自动走 Releases 下载。"""
        if self._rpc and self._rpc.alive:
            return

        # 不能在 _starting 时直接返回: Web 请求可能紧接着访问 _rpc，
        # 造成断言失败并被包装成“服务器内部错误”。
        existing_task = self._start_task
        if existing_task and not existing_task.done():
            await asyncio.shield(existing_task)
            return

        loop = asyncio.get_running_loop()
        start_task = loop.create_task(self._start_runner(), name='qlinux-runner-start')
        self._start_task = start_task
        try:
            await asyncio.shield(start_task)
        finally:
            if self._start_task is start_task and start_task.done():
                self._start_task = None

    async def _start_runner(self) -> None:
        """执行一次 runner 启动；由 ensure_started 统一复用和等待。"""
        self._starting = True
        try:
            self._downloader = RunnerDownloader(self._bin_dir)
            exe = await self._downloader.ensure_runner()
            self._rpc = RunnerRPC(exe, self._data_dir / 'bots', self._sign_server(),
                                  self._on_runner_event)
            await self._rpc.start()
            log.info('QLinux runner 就绪')
            # 恢复已有账号 (keystore 仍在, 自动快速重登)
            for bot_id in list(self._accounts):
                try:
                    await self._create_bot_on_runner(bot_id)
                except Exception:  # noqa: BLE001
                    log.exception('QLinux 账号恢复失败: %s', bot_id)
        finally:
            self._starting = False

    async def shutdown(self) -> None:
        if self._rpc:
            await self._rpc.stop()
            self._rpc = None

    # ---------- runner 事件入口 ----------

    def _on_runner_event(self, event: dict) -> None:
        """runner 事件统一入口: 登录流程事件走状态机, 消息事件进 OneBot 管线。"""
        etype = event.get('event')
        bot_id = str(event.get('bot_id', ''))

        # 二维码缓存 (面板拉取用)
        if etype == 'qr.code':
            self.cache_qr(bot_id, event.get('png_base64', ''), event.get('url', ''))

        # 登录状态机
        if etype == 'login.result':
            state = event.get('state')
            error = event.get('error')
            if not error:
                error = {
                    235: 'QQ 拒绝登录：Linux 协议版本过低',
                    237: 'QQ 拒绝登录：设备环境风险（请先用官方 QQ 完成一次安全验证）',
                }.get(state)
            acc = self._accounts.get(bot_id)
            if acc:
                acc['status'] = 'online' if event.get('success') else 'login_failed'
                acc['last_state'] = state
                if event.get('success'):
                    acc.pop('last_error', None)
                else:
                    acc['last_error'] = error or '未知登录错误'
                self._save_accounts()
            fut = self._login_waits.pop(bot_id, None)
            if fut and not fut.done():
                fut.set_result({'success': event.get('success'),
                                'state': state,
                                'error': error})
            return
        if etype == 'bot.online':
            acc = self._accounts.get(bot_id)
            if acc:
                acc['status'] = 'online'
                acc['uin'] = str(event.get('uin') or acc.get('uin', ''))
                acc['last_online'] = int(time.time())
                self._save_accounts()
            asyncio.get_running_loop().create_task(self._bind_account(bot_id))
        elif etype == 'bot.offline':
            acc = self._accounts.get(bot_id)
            if acc:
                acc['status'] = 'offline'
                self._save_accounts()
        elif etype == 'qr.state':
            acc = self._accounts.get(bot_id)
            if acc and event.get('state') in ('Confirmed',):
                acc['status'] = 'confirming'
                self._save_accounts()

        # OneBot 事件转换 → 框架事件总线
        payload = runner_event_to_onebot(event)
        if payload:
            loop = asyncio.get_running_loop()
            loop.create_task(self._ingest(payload))

    async def _ingest(self, payload: dict) -> None:
        try:
            await self._app.ingest_event(payload, default_self_id=str(payload.get('self_id', '')))
        except Exception:  # noqa: BLE001
            log.exception('QLinux 事件注入失败')

    async def _bind_account(self, bot_id: str) -> None:
        """登录成功后把账号注册为 OneBot 本地动作 bot (发消息能力)。"""
        acc = self._accounts.get(bot_id)
        uin = str(acc.get('uin', '')) if acc else ''
        if not uin or uin in self._registered_uins:
            return
        adapter = getattr(self._app, 'adapter', None)
        if adapter is None:
            return

        async def _handler(action: str, params: dict, _bot_id=bot_id):
            return await self.handle_action(_bot_id, action, params)

        adapter.register_local_bot(uin, _handler)
        self._registered_uins.add(uin)
        log.info('QLinux 账号 %s (bot_id=%s) 已绑定本地动作', uin, bot_id)

    # ---------- 公开 API (web 面板与动作层调用) ----------

    async def create_account(self, bot_id: str) -> dict:
        """新建账号实例 (只建 runner 侧 bot, 不触发登录)。"""
        await self.ensure_started()
        assert self._rpc
        await self._create_bot_on_runner(bot_id)
        acc = {'bot_id': bot_id, 'uin': '', 'status': 'created',
               'created_at': int(time.time()), 'last_online': 0}
        self._accounts[bot_id] = acc
        self._save_accounts()
        return acc

    async def login_qr(self, bot_id: str) -> dict:
        """发起扫码登录。二维码通过 runner 事件 'qr.code' 推给面板。"""
        await self.ensure_started()
        assert self._rpc
        if bot_id not in self._accounts:
            await self.create_account(bot_id)
        acc = self._accounts[bot_id]
        acc['status'] = 'waiting_scan'
        self._save_accounts()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._login_waits[bot_id] = fut
        try:
            result = await self._rpc.call('bot.login.qr', {'bot_id': bot_id}, timeout=10)
        except Exception:
            self._login_waits.pop(bot_id, None)
            raise
        return result

    async def login_password(self, bot_id: str, uin: int, password: str) -> dict:
        """账密登录。可能触发 captcha/sms 事件, 由面板引导用户提交。"""
        await self.ensure_started()
        assert self._rpc
        if bot_id not in self._accounts:
            await self.create_account(bot_id)
        acc = self._accounts[bot_id]
        acc['uin'] = str(uin)
        acc['status'] = 'password_login'
        self._save_accounts()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._login_waits[bot_id] = fut
        try:
            result = await self._rpc.call(
                'bot.login.password', {'bot_id': bot_id, 'uin': uin, 'password': password},
                timeout=15)
        except Exception:
            self._login_waits.pop(bot_id, None)
            raise
        return result

    async def submit_captcha(self, bot_id: str, ticket: str, randstr: str = '') -> dict:
        assert self._rpc
        return await self._rpc.call(
            'bot.submit.captcha', {'bot_id': bot_id, 'ticket': ticket, 'randstr': randstr})

    async def submit_sms(self, bot_id: str, code: str) -> dict:
        assert self._rpc
        return await self._rpc.call('bot.submit.sms', {'bot_id': bot_id, 'code': code})

    async def stop_account(self, bot_id: str) -> dict:
        assert self._rpc
        result = await self._rpc.call('bot.stop', {'bot_id': bot_id})
        acc = self._accounts.get(bot_id)
        if acc:
            acc['status'] = 'stopped'
            self._save_accounts()
        uin = str(acc.get('uin', '')) if acc else ''
        if uin and uin in self._registered_uins:
            adapter = getattr(self._app, 'adapter', None)
            if adapter:
                adapter.unregister_local_bot(uin)
            self._registered_uins.discard(uin)
        return result

    async def delete_account(self, bot_id: str) -> dict:
        """停掉并删除 keystore (彻底移除账号)。"""
        try:
            await self.stop_account(bot_id)
        except Exception:  # noqa: BLE001
            pass
        self._accounts.pop(bot_id, None)
        self._save_accounts()
        bot_dir = self._data_dir / 'bots' / bot_id
        if bot_dir.is_dir():
            import shutil
            shutil.rmtree(bot_dir, ignore_errors=True)
        return {'deleted': True}

    def list_accounts(self) -> list[dict]:
        return [dict(a) for a in self._accounts.values()]

    def get_qr_image(self, bot_id: str) -> str | None:
        """最近一次二维码 (base64 PNG); 由 runner 事件缓存。"""
        return getattr(self, '_qr_cache', {}).get(bot_id)

    def cache_qr(self, bot_id: str, png_b64: str, url: str) -> None:
        if not hasattr(self, '_qr_cache'):
            self._qr_cache = {}
        self._qr_cache[bot_id] = {'png_base64': png_b64, 'url': url, 'ts': int(time.time())}

    # ---------- OneBot 动作映射 (插件 call_api 走到这里) ----------

    async def handle_action(self, bot_id: str, action: str, params: dict) -> dict | None:
        assert self._rpc
        if action == 'send_group_msg':
            segs = params.get('message', [])
            return await self._rpc.call('msg.send.segments', {
                'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0)),
                'segments': self._ob_to_segments(segs)})
        if action == 'send_private_msg':
            segs = params.get('message', [])
            return await self._rpc.call('msg.send.segments', {
                'bot_id': bot_id, 'friend_uin': int(params.get('user_id', 0)),
                'segments': self._ob_to_segments(segs)})
        if action == 'send_msg':
            if params.get('group_id'):
                return await self.handle_action(bot_id, 'send_group_msg', params)
            return await self.handle_action(bot_id, 'send_private_msg', params)
        if action == 'get_login_info':
            acc = self._accounts.get(bot_id, {})
            return {'user_id': int(acc.get('uin', 0) or 0),
                    'nickname': acc.get('nickname', '')}
        if action == 'delete_msg':
            return await self._rpc.call('msg.recall', {
                'bot_id': bot_id, 'group_uin': params.get('group_id'),
                'sequence': int(params.get('message_id', 0))})
        if action == 'get_msg':
            return None  # 首期不支持按 id 查历史
        return None

    @staticmethod
    def _ob_to_segments(message) -> list[dict]:
        """OneBot v11 消息段 → runner segments。"""
        if isinstance(message, str):
            return [{'type': 'text', 'data': message}]
        out: list[dict] = []
        for seg in message:
            t = seg.get('type')
            d = seg.get('data', {}) or {}
            if t == 'text':
                out.append({'type': 'text', 'data': d.get('text', '')})
            elif t == 'at':
                qq = str(d.get('qq', ''))
                out.append({'type': 'at_all'} if qq == 'all' else {'type': 'at', 'qq': int(qq or 0)})
            elif t == 'image':
                # 支持 base64 直传或 URL (URL 拉取转 base64)
                b64 = d.get('file', '')
                if b64.startswith('base64://'):
                    b64 = b64[len('base64://'):]
                elif b64.startswith('http'):
                    b64 = _fetch_b64_sync(b64)
                out.append({'type': 'image', 'data_base64': b64})
            elif t == 'json':
                out.append({'type': 'json', 'data': d.get('data', '')})
            # reply 段暂不透传 (需要 BotMessage 对象)
        return out

    # ---------- runner 侧 bot 创建 ----------

    async def _create_bot_on_runner(self, bot_id: str) -> None:
        assert self._rpc
        await self._rpc.call('bot.create', {'bot_id': bot_id}, timeout=30)


def _fetch_b64_sync(url: str) -> str:
    """同步拉取图片 URL → base64 (aiohttp 在动作协程里不好嵌套, 用阻塞拉取 + 线程)。"""
    import base64 as _b64
    import urllib.request

    def _fetch():
        req = urllib.request.Request(url, headers={'User-Agent': 'ElainaQQ/QLinux'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return _b64.b64encode(r.read()).decode()

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_fetch).result(timeout=20)
