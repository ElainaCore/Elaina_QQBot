"""QLinux 渠道管理器 — 账号持久化 + runner 托管 + OneBot 动作绑定。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path

from core.protocols.onebot.message import normalize_message
from core.protocols.onebot.protocol import action_failed, action_ok
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
        self._message_cache: dict[tuple[str, int], dict] = {}
        self._shutting_down = False
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
        if self._rpc and self._rpc.alive:
            return

        # 不能在 _starting 时直接返回: Web 请求可能紧接着访问 _rpc，
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
            self._rpc = RunnerRPC(
                exe,
                self._data_dir / 'bots',
                self._sign_server(),
                self._on_runner_event,
            )
            await self._rpc.start()
            log.info('QLinux runner 就绪')
            # 恢复已有账号。仅创建 runner 侧 Bot 不会开始收包，必须再调用
            for bot_id in list(self._accounts):
                try:
                    acc = self._accounts[bot_id]
                    await self._create_bot_on_runner(bot_id)
                    if acc.get('status') in {'online', 'connecting', 'reconnecting', 'resume_pending'}:
                        acc['status'] = 'reconnecting'
                        self._save_accounts()
                        # 兼容 v1.0.1 runner：login.qr 的实现本身调用
                        self._login_active.add(bot_id)
                        try:
                            await self._rpc.call('bot.login.qr', {'bot_id': bot_id}, timeout=10)
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
                acc['status'] = 'connecting' if event.get('success') else 'login_failed'
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
        if etype == 'login.completed':
            # runner 对 Login() 的最终返回值：当 InfoSync/注册在线失败时，
            if not event.get('success'):
                acc = self._accounts.get(bot_id)
                if acc:
                    acc['status'] = 'login_failed'
                    acc['last_error'] = event.get('error') or '登录后注册在线失败'
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
            # Login() 在旧票据失效时会先发出 offline，再自动转入二维码登录。
            acc = self._accounts.get(bot_id)
            if acc and not self._shutting_down:
                acc['status'] = 'offline'
                self._save_accounts()
                uin = str(acc.get('uin') or '')
                adapter = getattr(self._app, 'adapter', None)
                if adapter is not None and uin in self._registered_uins:
                    adapter.unregister_local_bot(uin)
                    self._registered_uins.discard(uin)
                    adapter.unregister_identity_alias(bot_id)
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
            # Keep the same short-lived message lookup that native OneBot
            message_id = payload.get('message_id')
            if message_id not in (None, ''):
                try:
                    key = (str(payload.get('self_id') or ''), int(message_id))
                except (TypeError, ValueError):
                    key = None
                if key:
                    self._message_cache[key] = dict(payload)
                    while len(self._message_cache) > 2000:
                        self._message_cache.pop(next(iter(self._message_cache)))
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
            result = await self._rpc.call('bot.login.qr', {'bot_id': bot_id}, timeout=10)
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
            result = await self._rpc.call(
                'bot.login.password', {'bot_id': bot_id, 'uin': uin, 'password': password},
                timeout=15)
        except Exception:
            self._login_waits.pop(bot_id, None)
            self._login_active.discard(bot_id)
            raise
        return result

    async def submit_captcha(self, bot_id: str, ticket: str, randstr: str = '') -> dict:
        rpc = self._rpc_or_raise()
        return await rpc.call(
            'bot.submit.captcha', {'bot_id': bot_id, 'ticket': ticket, 'randstr': randstr})

    async def submit_sms(self, bot_id: str, code: str) -> dict:
        rpc = self._rpc_or_raise()
        return await rpc.call('bot.submit.sms', {'bot_id': bot_id, 'code': code})

    async def stop_account(self, bot_id: str) -> dict:
        self._rpc_or_raise()
        self._login_active.discard(bot_id)
        login_wait = self._login_waits.pop(bot_id, None)
        if login_wait and not login_wait.done():
            login_wait.cancel()
        result = await self._rpc_or_raise().call('bot.stop', {'bot_id': bot_id})
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
        self._rpc_or_raise()
        try:
            if action in {'send_group_msg', 'send_private_msg'}:
                segs = params.get('message', [])
                target_key = 'group_uin' if action == 'send_group_msg' else 'friend_uin'
                param_key = 'group_id' if action == 'send_group_msg' else 'user_id'
                result = await self._rpc.call('msg.send.segments', {
                    'bot_id': bot_id, target_key: int(params.get(param_key, 0)),
                    'segments': await self._ob_to_segments(segs)})
                sequence = int((result or {}).get('sequence', 0) or 0)
                return action_ok({'message_id': sequence, 'seq': sequence})
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
                result = await self._rpc.call('msg.send.forward', rpc_params)
                sequence = int((result or {}).get('sequence', 0) or 0)
                return action_ok({'message_id': sequence, 'seq': sequence})
            if action == 'get_login_info':
                result = await self._rpc.call('bot.info', {'bot_id': bot_id})
                acc = self._accounts.get(bot_id, {})
                result = dict(result or {})
                result.setdefault('user_id', int(acc.get('uin', 0) or 0))
                result.setdefault('nickname', acc.get('nickname', ''))
                return action_ok(result)
            if action == 'get_status':
                acc = self._accounts.get(bot_id, {})
                online = acc.get('status') == 'online'
                return action_ok({'online': online, 'good': online, 'stat': {'packet_received': 0}})
            if action == 'get_group_list':
                result = await self._rpc.call('bot.group.list', {
                    'bot_id': bot_id, 'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result or [])
            if action == 'get_group_info':
                result = await self._rpc.call('bot.group.info', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0)),
                    'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result)
            if action == 'get_group_member_list':
                result = await self._rpc.call('bot.group.member.list', {
                    'bot_id': bot_id, 'group_uin': int(params.get('group_id', 0)),
                    'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result or [])
            if action == 'get_group_member_info':
                result = await self._rpc.call('bot.group.member.info', {
                    'bot_id': bot_id,
                    'group_uin': int(params.get('group_id', 0)),
                    'member_uin': int(params.get('user_id', 0)),
                    'no_cache': bool(params.get('no_cache', False)),
                })
                return action_ok(result)
            if action == 'get_friend_list':
                result = await self._rpc.call('bot.friend.list', {
                    'bot_id': bot_id, 'no_cache': bool(params.get('no_cache', False))})
                return action_ok(result or [])
            if action == 'get_stranger_info':
                result = await self._rpc.call('bot.stranger.info', {
                    'bot_id': bot_id, 'user_uin': int(params.get('user_id', 0))})
                return action_ok(result)
            if action in {
                'set_group_kick', 'set_group_ban', 'set_group_whole_ban',
                'set_group_card', 'set_group_special_title', 'set_group_name',
                'set_group_leave', 'group_poke', 'friend_poke', 'send_poke',
            }:
                if action == 'send_poke':
                    action = 'group_poke' if params.get('group_id') else 'friend_poke'
                method, rpc_params = self._qlinux_admin_action(action, params)
                rpc_params['bot_id'] = bot_id
                result = await self._rpc.call(method, rpc_params)
                return action_ok(result or {})
            if action == 'get_msg':
                try:
                    message_id = int(params.get('message_id', 0))
                except (TypeError, ValueError):
                    message_id = 0
                cached = self._message_cache.get((str(self._accounts.get(bot_id, {}).get('uin', '')), message_id))
                return action_ok(cached) if cached else action_failed('消息不存在', 1404)
            if action == 'delete_msg':
                message_id = params.get('message_id', 0)
                try:
                    sequence = int(message_id)
                except (TypeError, ValueError):
                    # Accept ids emitted by older QLinux runners too.
                    sequence = int(str(message_id).rsplit(':', 1)[-1] or 0)
                cached = self._message_cache.get((str(self._accounts.get(bot_id, {}).get('uin', '')), sequence), {})
                group_uin = params.get('group_id') or cached.get('group_id')
                result = await self._rpc.call('msg.recall', {
                    'bot_id': bot_id, 'group_uin': group_uin, 'sequence': sequence})
                return action_ok(result or {'message_id': sequence})
            return action_failed(f'QLinux 暂不支持动作: {action}', 1400)
        except Exception as exc:  # noqa: BLE001
            log.warning('QLinux 动作失败: %s (%s)', action, exc)
            return action_failed(str(exc), 1500)

    @staticmethod
    def _qlinux_admin_action(action: str, params: dict) -> tuple[str, dict]:
        """Translate common OneBot group actions to runner operations."""
        if action == 'set_group_kick':
            return 'bot.group.kick', {
                'group_uin': int(params.get('group_id', 0)),
                'member_uin': int(params.get('user_id', 0)),
                'reject_add': bool(params.get('reject_add_request', False)),
                'reason': str(params.get('reason') or ''),
            }
        if action == 'set_group_ban':
            return 'bot.group.ban', {
                'group_uin': int(params.get('group_id', 0)),
                'member_uin': int(params.get('user_id', 0)),
                'duration': max(0, int(params.get('duration', 1800))),
            }
        if action == 'set_group_whole_ban':
            return 'bot.group.whole_ban', {
                'group_uin': int(params.get('group_id', 0)),
                'enable': bool(params.get('enable', True)),
            }
        if action == 'set_group_card':
            return 'bot.group.card', {
                'group_uin': int(params.get('group_id', 0)),
                'member_uin': int(params.get('user_id', 0)),
                'card': str(params.get('card') or ''),
            }
        if action == 'set_group_special_title':
            return 'bot.group.special_title', {
                'group_uin': int(params.get('group_id', 0)),
                'member_uin': int(params.get('user_id', 0)),
                'title': str(params.get('special_title') or ''),
            }
        if action == 'set_group_name':
            return 'bot.group.name', {
                'group_uin': int(params.get('group_id', 0)),
                'name': str(params.get('group_name') or ''),
            }
        if action == 'set_group_leave':
            return 'bot.group.leave', {'group_uin': int(params.get('group_id', 0))}
        if action == 'group_poke':
            return 'bot.group.poke', {
                'group_uin': int(params.get('group_id', 0)),
                'member_uin': int(params.get('user_id', 0)),
            }
        if action == 'friend_poke':
            return 'bot.friend.poke', {'user_uin': int(params.get('user_id', 0))}
        raise ValueError(f'QLinux 暂不支持动作: {action}')

    @staticmethod
    async def _ob_to_segments(message) -> list[dict]:
        """OneBot v11 消息段 → runner segments。"""
        out: list[dict] = []
        for seg in normalize_message(message):
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
                    b64 = await asyncio.to_thread(_fetch_b64_sync, b64)
                out.append({'type': 'image', 'data_base64': b64})
            elif t == 'json':
                out.append({'type': 'json', 'data': d.get('data', '')})
            elif t in {'record', 'video', 'file', 'markdown', 'xml'}:
                out.append({'type': t, 'data': dict(d)})
            elif t == 'reply':
                out.append({'type': 'reply', 'id': str(d.get('id') or d.get('seq') or '')})
            else:
                # runner 扩展段以统一 data 对象透传，不让新消息类型只在
                out.append({'type': str(t or 'unknown'), 'data': dict(d)})
        return out

    # ---------- runner 侧 bot 创建 ----------

    async def _create_bot_on_runner(self, bot_id: str) -> None:
        rpc = self._rpc_or_raise()
        await rpc.call('bot.create', {'bot_id': bot_id}, timeout=30)


def _fetch_b64_sync(url: str) -> str:
    """在线程池中执行的图片 URL → base64 下载。"""
    import base64 as _b64
    import urllib.request
    from urllib.parse import urlsplit

    max_size = 16 * 1024 * 1024
    parsed = urlsplit(str(url or ''))
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('图片 URL 必须使用 HTTP 或 HTTPS')
    req = urllib.request.Request(url, headers={'User-Agent': 'ElainaQQ/QLinux'})
    with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310
        declared = int(response.headers.get('Content-Length') or 0)
        if declared > max_size:
            raise ValueError('图片超过 16 MB 限制')
        chunks = []
        size = 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_size:
                raise ValueError('图片超过 16 MB 限制')
            chunks.append(chunk)
        return _b64.b64encode(b''.join(chunks)).decode()
