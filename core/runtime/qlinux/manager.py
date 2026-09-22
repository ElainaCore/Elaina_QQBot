"""QLinux 渠道管理器 — 账号持久化 + runner 托管 + OneBot 动作绑定。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path

from core.protocols.onebot.cache import MessageCache
from core.protocols.onebot.event import normalize_event
from core.protocols.onebot.identity import (
    message_id as build_message_id,
)
from core.protocols.onebot.identity import (
    normalize_message_identity,
)
from core.protocols.onebot.protocol import action_failed, action_ok
from core.runtime.embedded.packet import build_inline_keyboard_click_packet
from core.runtime.qlinux.actions import admin_action
from core.runtime.qlinux.message_codec import to_segments
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
        self._start_task: asyncio.Task | None = None
        self._login_waits: dict[str, asyncio.Future] = {}  # bot_id -> 登录结果等待
        # Lagrange 的 Login() 不是可重入操作。启动恢复和面板点击扫码可能
        self._login_active: set[str] = set()
        self._registered_uins: set[str] = set()
        self._message_cache = MessageCache()
        self._shutting_down = False
        # Runner 进程可能因协议升级或底层网络异常短暂退出。动作请求
        # 不能把这次瞬时故障直接暴露给对比任务；恢复锁保证并发请求只
        # 重建一次 runner。
        self._runner_recovery_lock = asyncio.Lock()
        # 版本标记变化时替换仍在运行的旧进程，避免更新后继续使用旧协议。
        self._runner_lifecycle_lock = asyncio.Lock()
        self._watchdog_task: asyncio.Task | None = None
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

    def _rpc_or_raise(self) -> RunnerRPC:
        """返回已启动的 runner。"""
        if self._rpc is None:
            raise RuntimeError('QLinux runner 未启动')
        return self._rpc

    @staticmethod
    def _is_runner_process_error(exc: BaseException) -> bool:
        """判断异常是否表示 runner 通道失效。"""
        if isinstance(exc, (BrokenPipeError, ConnectionError)):
            return True
        text = str(exc or "").strip().lower()
        return any(token in text for token in (
            'runner 未运行',
            'runner 标准输入不可用',
            'runner 进程意外退出',
            'runner 已停止',
            'runner standard input',
            'runner process exited',
        ))

    @staticmethod
    def _is_qr_expired(state: object = '', error: object = '') -> bool:
        """识别 Lagrange 的二维码过期状态，避免把它误报成账号登录失败。"""
        state_text = str(state or '').strip().lower()
        error_text = str(error or '').strip().lower()
        compact = ''.join(f'{state_text} {error_text}'.split())
        return (
            state_text in {'codeexpired', 'expired', 'qrcodeexpired'}
            or 'codeexpired' in compact
            or 'qrcodeexpired' in compact
            or ('二维码状态' in error_text and ('过期' in error_text or 'expired' in error_text))
        )

    def _mark_qr_expired(self, bot_id: str, state: object = '', error: object = '') -> None:
        """二维码过期只结束本次扫码流程，账号保持离线且不自动重登。"""
        acc = self._accounts.get(bot_id)
        message = '二维码已过期，请重新获取二维码'
        if acc:
            acc['status'] = 'offline'
            acc['last_state'] = state or 'CodeExpired'
            acc['last_error'] = message
            self._unbind_account(bot_id)
            self._save_accounts()
        self._login_active.discard(bot_id)
        fut = self._login_waits.pop(bot_id, None)
        if fut and not fut.done():
            fut.set_result({'success': False, 'state': state or 'CodeExpired', 'error': message})

    async def _recover_runner(self, failed_rpc: RunnerRPC) -> None:
        """重建失效 runner，并恢复已持久化的 bot 实例。"""
        if self._shutting_down:
            return
        async with self._runner_recovery_lock:
            if self._shutting_down:
                return
            # 其他并发请求可能已经完成了恢复。
            if self._rpc is not failed_rpc and self._rpc and self._rpc.alive:
                return
            self._mark_accounts_offline('QLinux runner 通道已断开')
            if self._rpc is failed_rpc:
                self._rpc = None
            with contextlib.suppress(Exception):
                await failed_rpc.stop()
            await self.ensure_started()

    async def _call_runner(
        self,
        method: str,
        params: dict | None = None,
        *,
        timeout: float = 60,
        retry_on_restart: bool = True,
    ):
        """调用 runner；进程级失败时自动恢复并仅重试一次。"""
        await self.ensure_started()
        rpc = self._rpc_or_raise()
        try:
            return await rpc.call(method, params, timeout=timeout)
        except (RuntimeError, BrokenPipeError, ConnectionError) as exc:
            if not retry_on_restart or not self._is_runner_process_error(exc):
                raise
            log.warning('QLinux runner 请求失败，准备恢复后重试: %s (%s)', method, exc)
            await self._recover_runner(rpc)
            return await self._rpc_or_raise().call(method, params, timeout=timeout)

    # ---------- 账号持久化 ----------

    def _load_accounts(self) -> None:
        if self._accounts_path.is_file():
            try:
                changed = False
                for acc in json.loads(self._accounts_path.read_text(encoding='utf-8')):
                    if 'protocol' in acc:
                        acc.pop('protocol')
                        changed = True
                    self._accounts[acc['bot_id']] = acc
                if changed:
                    self._save_accounts()
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
        async with self._runner_lifecycle_lock:
            if self._rpc and self._rpc.alive:
                downloader = self._downloader or RunnerDownloader(self._bin_dir)
                self._downloader = downloader
                if downloader.has_runner():
                    return
                if self._rpc and self._rpc.alive and not downloader.has_runner():
                    log.warning('QLinux runner 版本标记失效，准备替换旧进程')
                    await self._stop_runner_for_restart(self._rpc)

            # 不能在 _starting 时直接返回: Web 请求可能紧接着访问 _rpc，
            existing_task = self._start_task
            if existing_task and not existing_task.done():
                start_task = existing_task
            else:
                loop = asyncio.get_running_loop()
                start_task = loop.create_task(self._start_runner(), name='qlinux-runner-start')
                self._start_task = start_task

        # 不要在生命周期锁内等待启动任务。runner 读取循环在启动阶段
        # 失败时可能触发恢复回调，而恢复回调也需要取得这把锁。
        try:
            await asyncio.shield(start_task)
        finally:
            if self._start_task is start_task and start_task.done():
                self._start_task = None

    async def _stop_runner_for_restart(self, rpc: RunnerRPC) -> None:
        """停止待升级 runner，但保留账号票据供新进程恢复。"""
        watchdog = self._watchdog_task
        self._watchdog_task = None
        if watchdog and not watchdog.done() and watchdog is not asyncio.current_task():
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        resume_bot_ids = {
            bot_id for bot_id, account in self._accounts.items()
            if account.get('status') in {'online', 'connecting', 'reconnecting'}
        }
        for bot_id in resume_bot_ids:
            account = self._accounts.get(bot_id)
            if account:
                account['status'] = 'resume_pending'
        if resume_bot_ids:
            self._save_accounts()
        self._login_active.clear()
        if self._rpc is rpc:
            self._rpc = None
        with contextlib.suppress(Exception):
            await rpc.stop()

    async def _start_runner(self) -> None:
        """执行一次 runner 启动；由 ensure_started 统一复用和等待。"""
        self._starting = True
        try:
            self._downloader = RunnerDownloader(self._bin_dir)
            exe = await self._downloader.ensure_runner()
            self._rpc = RunnerRPC(
                exe,
                self._data_dir / 'bots',
                self._sign_server(),
                self._on_runner_event,
                self._on_runner_exit,
            )
            await self._rpc.start()
            self._watchdog_task = asyncio.create_task(
                self._runner_watchdog(self._rpc), name='qlinux-runner-watchdog'
            )
            log.info('QLinux runner 就绪')
            # 恢复已有账号。仅创建 runner 侧 Bot 不会开始收包，必须再调用
            for bot_id in list(self._accounts):
                try:
                    acc = self._accounts[bot_id]
                    # 当前仍处于 _start_runner() 内，不能调用会再次等待
                    # ensure_started() 的统一封装，否则 runner 恢复时会自等待。
                    await self._rpc.call('bot.create', {'bot_id': bot_id}, timeout=30)
                    if acc.get('status') in {'online', 'connecting', 'reconnecting', 'resume_pending'}:
                        acc['status'] = 'reconnecting'
                        self._save_accounts()
                        self._login_active.add(bot_id)
                        try:
                            # 快速重登: 有效票据直接恢复会话, 失效才回退扫码。
                            # 旧版本这里强制 login.qr, 每次框架重启都要重新扫码。
                            await self._rpc.call('bot.login.resume', {'bot_id': bot_id}, timeout=10)
                        except Exception:
                            self._login_active.discard(bot_id)
                            raise
                except Exception:  # noqa: BLE001
                    log.exception('QLinux 账号恢复失败: %s', bot_id)
        finally:
            self._starting = False

    async def shutdown(self) -> None:
        rpc = self._rpc
        if rpc is None:
            return

        # 先让 Lagrange 正常注销 SSO 会话，再结束 runner。直接杀进程会让
        resume_bot_ids = {
            bot_id
            for bot_id, account in self._accounts.items()
            if account.get('status') in {'online', 'connecting', 'reconnecting'}
        }
        self._shutting_down = True
        watchdog = self._watchdog_task
        self._watchdog_task = None
        if watchdog and not watchdog.done():
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        if rpc.alive:
            stop_tasks = [
                asyncio.create_task(
                    rpc.call('bot.stop', {'bot_id': bot_id}, timeout=6),
                    name=f'qlinux-stop-{bot_id}',
                )
                for bot_id in list(self._accounts)
            ]
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
        for bot_id in resume_bot_ids:
            account = self._accounts.get(bot_id)
            if account:
                account['status'] = 'resume_pending'
        if resume_bot_ids:
            self._save_accounts()
        self._login_active.clear()
        try:
            await rpc.stop()
        finally:
            self._shutting_down = False
            if self._rpc is rpc:
                self._rpc = None

    async def _runner_watchdog(self, rpc: RunnerRPC) -> None:
        """定期探测空闲 runner 并触发统一恢复流程。"""
        consecutive_failures = 0
        try:
            while not self._shutting_down and self._rpc is rpc:
                # 探活只用于兜底。单次超时可能是签名/网络请求阻塞，不能因此
                # 立即杀掉整个 runner 和所有账号会话。
                await asyncio.sleep(60)
                if self._shutting_down or self._rpc is not rpc:
                    return
                try:
                    await rpc.call('ping', timeout=20)
                    consecutive_failures = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    consecutive_failures += 1
                    log.warning('QLinux runner 探活失败 (%d/3): %s', consecutive_failures, exc)
                    if consecutive_failures < 3:
                        continue
                    log.error('QLinux runner 连续三次探活失败，准备恢复')
                    await self._recover_runner(rpc)
                    return
        except asyncio.CancelledError:
            return

    async def _on_runner_exit(self, rpc: RunnerRPC) -> None:
        """runner stdout EOF/读取异常后立即恢复；看门狗仅作兜底。"""
        if self._shutting_down:
            return
        try:
            await self._recover_runner(rpc)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('QLinux runner 退出后自动恢复失败')

    def _unbind_account(self, bot_id: str) -> None:
        """撤销账号的本地 OneBot 动作与身份别名。"""
        acc = self._accounts.get(bot_id)
        if not acc:
            return
        uin = str(acc.get('uin') or '').strip()
        adapter = getattr(self._app, 'adapter', None)
        if adapter is not None:
            # 不依赖注册集合，进程崩溃或重载后仍要清理旧绑定。
            if uin:
                adapter.unregister_local_bot(uin)
            adapter.unregister_identity_alias(bot_id)
        if uin:
            self._registered_uins.discard(uin)

    def _mark_accounts_offline(self, reason: str = '') -> None:
        """runner 通道丢失后立即清理所有旧在线状态。"""
        changed = False
        for bot_id, acc in self._accounts.items():
            if acc.get('status') in {'online', 'connecting', 'reconnecting', 'password_login'}:
                acc['status'] = 'offline'
                if reason:
                    acc['last_error'] = reason
                changed = True
            self._unbind_account(bot_id)
            self._login_active.discard(bot_id)
        for fut in self._login_waits.values():
            if not fut.done():
                fut.cancel()
        self._login_waits.clear()
        if changed:
            self._save_accounts()

    # ---------- runner 事件入口 ----------

    def _on_runner_event(self, event: dict) -> None:
        """runner 事件统一入口: 登录流程事件走状态机, 消息事件进 OneBot 管线。"""
        etype = str(event.get('event') or '').lower()
        bot_id = str(event.get('bot_id', ''))
        log.debug('QLinux runner 事件: bot=%s type=%s', bot_id, etype)

        # 二维码缓存 (面板拉取用)
        if etype == 'qr.code':
            self.cache_qr(bot_id, event.get('png_base64', ''), event.get('url', ''))
            acc = self._accounts.get(bot_id)
            if acc:
                acc['status'] = 'waiting_scan'
                self._save_accounts()

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
                # BotLoginEvent 只表示鉴权阶段成功；真正可收发消息要等
                if not event.get('success') and self._is_qr_expired(state, error):
                    self._mark_qr_expired(bot_id, state, error)
                else:
                    acc['status'] = 'connecting' if event.get('success') else 'login_failed'
                    acc['last_state'] = state
                    if event.get('success'):
                        acc.pop('last_error', None)
                    else:
                        acc['last_error'] = error or '未知登录错误'
                        self._unbind_account(bot_id)
                    self._save_accounts()
            fut = self._login_waits.pop(bot_id, None)
            if fut and not fut.done():
                fut.set_result({'success': event.get('success'),
                                'state': state,
                                'error': error})
            return
        if etype == 'login.completed':
            # runner 对 Login() 的最终返回值：当 InfoSync/注册在线失败时，
            if not event.get('success'):
                acc = self._accounts.get(bot_id)
                if acc:
                    error = event.get('error') or ''
                    if self._is_qr_expired('', error) or self._is_qr_expired(
                        acc.get('last_state'), acc.get('last_error')
                    ):
                        self._mark_qr_expired(bot_id, acc.get('last_state') or '', error)
                    else:
                        acc['status'] = 'login_failed'
                        acc['last_error'] = error or '登录后注册在线失败'
                        self._unbind_account(bot_id)
                        self._save_accounts()
            self._login_active.discard(bot_id)
            return
        if etype == 'bot.online':
            self._login_active.discard(bot_id)
            acc = self._accounts.get(bot_id)
            if acc:
                acc['status'] = 'online'
                acc['uin'] = str(event.get('uin') or acc.get('uin', ''))
                acc['last_online'] = int(time.time())
                self._save_accounts()
            uin = str(event.get('uin') or (acc or {}).get('uin', '')) if acc else str(event.get('uin') or '')
            adapter = getattr(self._app, 'adapter', None)
            if adapter is not None and uin:
                # bot_id 是面板配置编号，uin 是 OneBot 标准 self_id；两者
                adapter.register_identity_alias(bot_id, uin)
            asyncio.get_running_loop().create_task(self._bind_account(bot_id))
        elif etype == 'bot.offline':
            # 运行期间收到下线/被踢只更新为离线，不能擅自重新登录。
            # 只有框架 shutdown 保存为 resume_pending 后，下一次启动才会恢复登录。
            acc = self._accounts.get(bot_id)
            reason = str(event.get('reason') or '')
            tips = str(event.get('tips') or '')
            if acc and not self._shutting_down:
                acc['status'] = 'offline'
                if reason == 'Kicked':
                    acc['last_error'] = f'被服务器踢下线: {tips or "未提供原因"}'
                elif reason == 'Disconnected':
                    acc['last_error'] = '网络连接断开'
                self._unbind_account(bot_id)
                self._save_accounts()
        elif etype == 'qr.state':
            acc = self._accounts.get(bot_id)
            state = event.get('state')
            if acc and self._is_qr_expired(state):
                self._mark_qr_expired(bot_id, state)
            elif acc and state in ('Confirmed',):
                acc['status'] = 'confirming'
                self._save_accounts()

        # OneBot 事件转换 → 框架事件总线
        payload = runner_event_to_onebot(event)
        if payload:
            loop = asyncio.get_running_loop()
            loop.create_task(self._ingest(payload))

    async def _ingest(self, payload: dict) -> None:
        try:
            payload = normalize_event(payload, str(payload.get('self_id') or '')) or dict(payload)
            payload = normalize_message_identity(payload, str(payload.get('self_id') or ''))
            # message_id 可能是哈希 ID，不能作为 QQ 协议消息序号。
            sequence = int(
                payload.get('real_seq')
                or payload.get('message_seq')
                or payload.get('sequence')
                or payload.get('msg_seq')
                or 0
            )
            payload.setdefault('sequence', sequence)
            payload.setdefault('nt_msg_seq', 0)
            payload.setdefault('peer', payload.get('group_id') or payload.get('user_id'))
            payload.setdefault('is_group', payload.get('message_type') == 'group')
            # 保留与原生 OneBot 相同的短期消息缓存。
            message_id = payload.get('message_id')
            if message_id not in (None, ''):
                self._message_cache.put(payload, str(payload.get('self_id') or ''))
            from core.protocols.onebot.contract import Channel

            accepted = await self._app.ingest_event(
                payload,
                default_self_id=str(payload.get('self_id', '')),
                source=Channel.LAGRANGE,
            )
            if not accepted:
                log.warning('QLinux 事件未进入框架队列: post_type=%s self_id=%s',
                            payload.get('post_type'), payload.get('self_id'))
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

        from core.protocols.onebot.contract import Channel

        adapter.register_local_bot(uin, _handler, channel=Channel.LAGRANGE)
        adapter.register_identity_alias(bot_id, uin)
        self._registered_uins.add(uin)
        log.info('QLinux 账号 %s (bot_id=%s) 已绑定本地动作', uin, bot_id)

    # ---------- 公开 API (web 面板与动作层调用) ----------

    async def create_account(self, bot_id: str) -> dict:
        """新建 Linux 协议账号实例 (只建 runner 侧 bot, 不触发登录)。"""
        await self.ensure_started()
        self._rpc_or_raise()
        await self._create_bot_on_runner(bot_id)
        acc = {'bot_id': bot_id, 'uin': '', 'status': 'created',
               'created_at': int(time.time()), 'last_online': 0}
        self._accounts[bot_id] = acc
        self._save_accounts()
        return acc

    async def login_qr(self, bot_id: str) -> dict:
        """发起扫码登录。二维码通过 runner 事件 'qr.code' 推给面板。"""
        await self.ensure_started()
        self._rpc_or_raise()
        if bot_id not in self._accounts:
            await self.create_account(bot_id)
        if bot_id in self._login_active:
            return {'started': False, 'already_running': True}
        acc = self._accounts[bot_id]
        acc['status'] = 'waiting_scan'
        self._save_accounts()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._login_waits[bot_id] = fut
        self._login_active.add(bot_id)
        try:
            result = await self._call_runner('bot.login.qr', {'bot_id': bot_id}, timeout=10)
        except Exception:
            self._login_waits.pop(bot_id, None)
            self._login_active.discard(bot_id)
            raise
        return result

    async def login_password(self, bot_id: str, uin: int, password: str) -> dict:
        """账密登录。可能触发 captcha/sms 事件, 由面板引导用户提交。"""
        await self.ensure_started()
        self._rpc_or_raise()
        if bot_id not in self._accounts:
            await self.create_account(bot_id)
        if bot_id in self._login_active:
            return {'started': False, 'already_running': True}
        acc = self._accounts[bot_id]
        acc['uin'] = str(uin)
        acc['status'] = 'password_login'
        self._save_accounts()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._login_waits[bot_id] = fut
        self._login_active.add(bot_id)
        try:
            result = await self._call_runner(
                'bot.login.password', {'bot_id': bot_id, 'uin': uin, 'password': password},
                timeout=15)
        except Exception:
            self._login_waits.pop(bot_id, None)
            self._login_active.discard(bot_id)
            raise
        return result

    async def submit_captcha(self, bot_id: str, ticket: str, randstr: str = '') -> dict:
        return await self._call_runner(
            'bot.submit.captcha',
            {'bot_id': bot_id, 'ticket': ticket, 'randstr': randstr},
        )

    async def submit_sms(self, bot_id: str, code: str) -> dict:
        return await self._call_runner('bot.submit.sms', {'bot_id': bot_id, 'code': code})

    async def stop_account(self, bot_id: str) -> dict:
        await self.ensure_started()
        self._rpc_or_raise()
        self._login_active.discard(bot_id)
        login_wait = self._login_waits.pop(bot_id, None)
        if login_wait and not login_wait.done():
            login_wait.cancel()
        result = await self._call_runner('bot.stop', {'bot_id': bot_id})
        acc = self._accounts.get(bot_id)
        if acc:
            acc['status'] = 'stopped'
            self._save_accounts()
        uin = str(acc.get('uin', '')) if acc else ''
        if uin and uin in self._registered_uins:
            adapter = getattr(self._app, 'adapter', None)
            if adapter:
                adapter.unregister_local_bot(uin)
                adapter.unregister_identity_alias(bot_id)
            self._registered_uins.discard(uin)
        return result

    async def delete_account(self, bot_id: str) -> dict:
        """停掉并删除 keystore (彻底移除账号)。"""
        with contextlib.suppress(Exception):
            await self.stop_account(bot_id)
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
        try:
            # runner 可能在两次动作之间退出；先走统一启动/恢复路径，
            # 避免 `_rpc` 暂时为空时绕过自动重启。
            await self.ensure_started()
            self._rpc_or_raise()
            if action in {'send_group_msg', 'send_private_msg'}:
                segs = params.get('message', [])
                target_key = 'group_uin' if action == 'send_group_msg' else 'friend_uin'
                param_key = 'group_id' if action == 'send_group_msg' else 'user_id'
                result = await self._call_runner('msg.send.segments', {
                    'bot_id': bot_id, target_key: int(params.get(param_key, 0)),
                    'segments': await self._ob_to_segments(segs)})
                sequence = int((result or {}).get('sequence', 0) or 0)
                target_id = int(params.get(param_key, 0) or 0)
                uin = int(self._accounts.get(bot_id, {}).get('uin', 0) or 0)
                message_id = build_message_id(
                    sequence,
                    group_id=target_id if action == 'send_group_msg' else None,
                    peer_id=target_id,
                    self_id=uin,
                )
                return action_ok({'message_id': message_id, 'seq': sequence})
            if action == 'send_packet':
                cmd = str(params.get('cmd') or '').strip()
                data = params.get('data')
                if not cmd or data in (None, ''):
                    return action_failed('send_packet 缺少 cmd 或 data', 1400)
                packet_params = {
                    'bot_id': bot_id,
                    'cmd': cmd,
                    'data': str(data),
                }
                try:
                    result = await self._call_runner('packet.send', packet_params)
                except RuntimeError as exc:
                    # runner 能正常响应但没有 packet.send 时，不能按通道
                    # 故障重启；重启同一二进制只会让在线账号短暂掉线。
                    if 'unknown method: packet.send' not in str(exc).lower():
                        raise
                    return action_failed('当前 QLinux runner 不支持原始发包，请升级 runner', 1405)
                return action_ok(result or {})
            if action == 'click_inline_keyboard_button':
                sequence = self._message_sequence(bot_id, params)
                if sequence <= 0:
                    return action_failed('点击按钮缺少有效的消息序号', 1400)
                packet = build_inline_keyboard_click_packet(
                    params.get('group_id'),
                    params.get('bot_appid'),
                    params.get('button_id'),
                    params.get('callback_data'),
                    sequence,
                )
                packet_params = {
                    'bot_id': bot_id,
                    'cmd': packet.cmd,
                    'data': packet.data.hex(),
                }
                try:
                    result = await self._call_runner('packet.send', packet_params)
                except RuntimeError as exc:
                    if 'unknown method: packet.send' not in str(exc).lower():
                        raise
                    return action_failed('当前 QLinux runner 不支持按钮发包，请升级 runner', 1405)
                if isinstance(result, dict) and result.get('status') == 'failed':
                    return result
                return action_ok(result or {})
            if action == 'send_msg':
                message_type = str(params.get('message_type') or '')
                if message_type == 'group' or (not message_type and params.get('group_id')):
                    return await self.handle_action(bot_id, 'send_group_msg', params)
                return await self.handle_action(bot_id, 'send_private_msg', params)
            if action in {'send_group_forward_msg', 'send_private_forward_msg', 'send_forward_msg'}:
                is_group = action == 'send_group_forward_msg' or (
                    action == 'send_forward_msg' and bool(params.get('group_id'))
                )
                rpc_params = {
                    'bot_id': bot_id,
                    'messages': params.get('messages') or [],
                }
                if is_group:
                    rpc_params['group_uin'] = int(params.get('group_id', 0))
                else:
                    rpc_params['friend_uin'] = int(params.get('user_id', 0))
                result = await self._call_runner('msg.send.forward', rpc_params)
                sequence = int((result or {}).get('sequence', 0) or 0)
                target_id = int((params.get('group_id') if is_group else params.get('user_id')) or 0)
                uin = int(self._accounts.get(bot_id, {}).get('uin', 0) or 0)
                message_id = build_message_id(
                    sequence,
                    group_id=target_id if is_group else None,
                    peer_id=target_id,
                    self_id=uin,
                )
                return action_ok({'message_id': message_id, 'seq': sequence})
            if action == 'get_login_info':
                result = await self._call_runner('bot.info', {'bot_id': bot_id})
                acc = self._accounts.get(bot_id, {})
                result = dict(result or {})
                result.setdefault('user_id', int(acc.get('uin', 0) or 0))
                result.setdefault('nickname', acc.get('nickname', ''))
                return action_ok(result)
            if action == 'get_status':
                acc = self._accounts.get(bot_id, {})
                online = acc.get('status') == 'online'
                return action_ok({'online': online, 'good': online, 'stat': {'packet_received': 0}})
            if action in {'get_cookies', 'get_credentials'}:
                result = await self._call_runner('bot.cookies', {
                    'bot_id': bot_id, 'domain': params.get('domain', 'qun.qq.com')})
                return action_ok(result or {})
            if action in {'get_client_key', 'get_credentials_key'}:
                result = await self._call_runner('bot.client.key', {'bot_id': bot_id})
                return action_ok(result or {})
            if action in {'set_online_status', 'set_diy_online_status'}:
                rpc = {'bot_id': bot_id, 'status': int(params.get('status', 0) or 0)}
                if action == 'set_diy_online_status':
                    rpc['face_id'] = int(params.get('face_id', 0) or 0)
                    rpc['text'] = str(params.get('wording') or params.get('text') or '')
                result = await self._call_runner('bot.status.set', rpc)
                return action_ok(result or {})
            if action == 'get_group_list':
                result = await self._call_runner('bot.group.list', {
                    'bot_id': bot_id, 'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result or [])
            if action == 'get_group_info':
                result = await self._call_runner('bot.group.info', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0)),
                    'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result)
            if action == 'get_group_member_list':
                result = await self._call_runner('bot.group.member.list', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0)),
                    'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result or [])
            if action == 'get_group_member_info':
                result = await self._call_runner('bot.group.member.info', {
                    'bot_id': bot_id,
                    'group_uin': int(params.get('group_id', 0)),
                    'member_uin': int(params.get('user_id', 0)),
                    'no_cache': bool(params.get('no_cache', False)),
                })
                return action_ok(result)
            if action == 'get_friend_list':
                result = await self._call_runner('bot.friend.list', {
                    'bot_id': bot_id, 'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result or [])
            if action == 'get_stranger_info':
                result = await self._call_runner('bot.stranger.info', {
                    'bot_id': bot_id, 'user_uin': int(params.get('user_id', 0))})
                return action_ok(result)
            if action in {'get_group_msg_history', 'get_group_message_history'}:
                result = await self._call_runner('msg.history.group', {
                    'bot_id': bot_id,
                    'group_uin': int(params.get('group_id', 0) or 0),
                    'message_seq': int(params.get('message_seq', 0) or 0),
                    'count': max(1, int(params.get('count', 20) or 20)),
                })
                return action_ok(result or [])
            if action in {'get_friend_msg_history', 'get_private_msg_history'}:
                result = await self._call_runner('msg.history.private', {
                    'bot_id': bot_id,
                    'user_uin': int(params.get('user_id', 0) or 0),
                    'message_seq': int(params.get('message_seq', 0) or 0),
                    'count': max(1, int(params.get('count', 20) or 20)),
                })
                return action_ok(result or [])
            if action in {'get_friend_request_list', 'get_friend_system_msg', 'get_doubt_friends_add_request'}:
                result = await self._call_runner('bot.friend.request.list', {'bot_id': bot_id})
                return action_ok(result or [])
            if action in {'set_group_sign', 'send_group_sign', 'group_clock_in'}:
                result = await self._call_runner('bot.group.clockin', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0) or 0)})
                return action_ok(result or {})
            if action in {'get_group_at_all_remain', 'get_group_at_all_remaining'}:
                result = await self._call_runner('bot.group.atall', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0) or 0)})
                return action_ok(result or {})
            if action in {'set_group_remark', 'set_group_description'}:
                result = await self._call_runner('bot.group.remark', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0)),
                    'remark': str(params.get('remark') or params.get('description') or ''),
                })
                return action_ok(result or {})
            if action in {'set_group_todo', 'complete_group_todo', 'cancel_group_todo'}:
                group_uin = int(params.get('group_id', 0) or 0)
                if action == 'set_group_todo':
                    method = 'bot.group.todo.set'
                    rpc = {'bot_id': bot_id, 'group_uin': group_uin,
                           'sequence': self._message_sequence(bot_id, params)}
                elif action == 'complete_group_todo':
                    method, rpc = 'bot.group.todo.finish', {'bot_id': bot_id, 'group_uin': group_uin}
                else:
                    method, rpc = 'bot.group.todo.remove', {'bot_id': bot_id, 'group_uin': group_uin}
                result = await self._call_runner(method, rpc)
                return action_ok(result or {})
            if action in {'get_group_todo', 'get_group_todo_list'}:
                result = await self._call_runner('bot.group.todo.get', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0) or 0)})
                return action_ok(result or {})
            if action in {'set_msg_emoji_like', 'set_group_reaction'}:
                result = await self._call_runner('bot.group.reaction', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0) or 0),
                    'sequence': self._message_sequence(bot_id, params),
                    'code': str(params.get('emoji_id') or params.get('code') or ''),
                    'enable': bool(params.get('set', params.get('enable', True))),
                })
                return action_ok(result or {})
            if action in {'set_friend_pin', 'set_group_pin'}:
                method = 'bot.friend.pin' if action == 'set_friend_pin' else 'bot.group.pin'
                key = 'friend_uin' if action == 'set_friend_pin' else 'group_uin'
                value = int(params.get('user_id' if action == 'set_friend_pin' else 'group_id', 0) or 0)
                result = await self._call_runner(method, {
                    'bot_id': bot_id, key: value, 'enable': bool(params.get('enable', True))})
                return action_ok(result or {})
            if action in {
                'set_group_kick', 'set_group_ban', 'set_group_whole_ban',
                'set_group_card', 'set_group_special_title', 'set_group_name',
                'set_group_leave', 'group_poke', 'friend_poke', 'send_poke',
            }:
                if action == 'send_poke':
                    action = 'group_poke' if params.get('group_id') else 'friend_poke'
                method, rpc_params = self._qlinux_admin_action(action, params)
                rpc_params['bot_id'] = bot_id
                result = await self._call_runner(method, rpc_params)
                return action_ok(result or {})
            if action == 'get_msg':
                try:
                    message_id = int(params.get('message_id', 0))
                except (TypeError, ValueError):
                    message_id = 0
                uin = str(self._accounts.get(bot_id, {}).get('uin', ''))
                cached = self._message_cache.get(message_id, uin)
                return action_ok(cached) if cached else action_failed('消息不存在', 1404)
            if action == 'delete_msg':
                scope = str(self._accounts.get(bot_id, {}).get('uin', ''))
                sequence = self._message_sequence(bot_id, params)
                cached = self._message_cache.get(sequence, scope) or {}
                group_uin = params.get('group_id') or cached.get('group_id')
                result = await self._call_runner('msg.recall', {
                    'bot_id': bot_id, 'group_uin': group_uin, 'sequence': sequence})
                return action_ok(result or {'message_id': sequence})
            # 将未在此处特化的 OneBot 动作交给 runner 通用分发。
            # 新版 QLinux runner 可能已支持扩展接口，不能在适配层提前拒绝。
            try:
                result = await self._call_runner('action', {
                    'bot_id': bot_id,
                    'action': action,
                    'params': params,
                })
            except Exception as exc:
                log.debug('QLinux runner 未实现动作 %s: %s', action, exc)
                return action_failed(f'QLinux 暂不支持动作: {action}', 1400)
            if isinstance(result, dict) and result.get('status') == 'failed':
                return result
            return action_ok(result if result is not None else {})
        except Exception as exc:  # noqa: BLE001
            log.warning('QLinux 动作失败: %s (%s)', action, exc)
            return action_failed(str(exc), 1500)

    @staticmethod
    def _qlinux_admin_action(action: str, params: dict) -> tuple[str, dict]:
        return admin_action(action, params)

    def _message_sequence(self, bot_id: str, params: dict) -> int:
        """解析消息 ID 对应的原始序号。"""
        values = [params.get(key) for key in (
            'msg_seq', 'msgSeq', 'message_seq', 'messageSeq',
            'real_seq', 'realSeq', 'sequence', 'seq',
            'message_id', 'messageId',
        ) if params.get(key) not in (None, '', 0, '0')]
        requested_id = 0
        for requested in values:
            try:
                candidate = int(str(requested).strip())
            except (TypeError, ValueError):
                token = str(requested).rsplit(':', 1)[-1].strip()
                try:
                    candidate = int(token)
                except (TypeError, ValueError):
                    continue
            if candidate:
                requested_id = candidate
                break
        scope = str(self._accounts.get(bot_id, {}).get('uin', ''))
        cached = self._message_cache.get(requested_id, scope) or {}
        value = next((cached.get(key) for key in (
            'real_seq', 'realSeq', 'message_seq', 'messageSeq',
            'msg_seq', 'msgSeq', 'sequence',
        ) if cached.get(key) not in (None, '', 0, '0')), requested_id)
        try:
            return int(str(value).strip() or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    async def _ob_to_segments(message) -> list[dict]:
        return await to_segments(message)

    # ---------- runner 侧 bot 创建 ----------

    async def _create_bot_on_runner(self, bot_id: str) -> None:
        await self._call_runner('bot.create', {'bot_id': bot_id}, timeout=30)
