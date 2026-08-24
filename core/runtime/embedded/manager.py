"""内置 QQ 生命周期与账号隔离。"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import inspect
import itertools
import json
import logging
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import psutil
from aiohttp import web

from core.foundation.branding import public_text
from core.foundation.config import cfg
from core.protocols.onebot.api import api_call_source, get_supported_actions
from core.protocols.onebot.protocol import action_failed
from core.runtime.qq.catalog import QQ_VERSIONS
from core.runtime.qq.installer import QQInstaller
from core.runtime.qq.launcher import QQLauncher
from core.services.files import write_json

log = logging.getLogger('ElainaQQ.embedded_qq')


@dataclass
class EmbeddedBot:
    bot_id: str
    bridge_port: int = 0
    qq_version_key: str = ''
    uin: str = ''
    nickname: str = ''
    force_quick_login: bool = False
    enabled: bool = True
    status: str = 'offline'
    qr_code: str = ''
    qr_url: str = ''
    error: str = ''
    created_at: float = field(default_factory=time.time)
    last_seen: float = 0.0
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    output_task: asyncio.Task | None = field(default=None, repr=False)
    reclaim_task: asyncio.Task | None = field(default=None, repr=False)
    launch_mode: str = field(default='', repr=False)

    def persisted(self) -> dict[str, Any]:
        return {
            'bot_id': self.bot_id,
            'bridge_port': self.bridge_port,
            'qq_version_key': self.qq_version_key,
            'uin': self.uin,
            'nickname': self.nickname,
            'force_quick_login': self.force_quick_login,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'last_seen': self.last_seen,
        }


class EmbeddedQQManager:
    """每个账号启动独立 QQ 进程，同时共享一份 QQ 安装。"""

    def __init__(self, app):
        self.app = app
        self.bots: dict[str, EmbeddedBot] = {}
        self._lock = asyncio.Lock()
        self._xvfb_lock = asyncio.Lock()
        self._xvfb_process: asyncio.subprocess.Process | None = None
        self._xvfb_display = ''
        self._stopping: set[str] = set()
        self._memory_cache: dict[str, tuple[float, int, dict[str, Any]]] = {}
        self._control_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._control_futures: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
        self._red_packet_listeners: dict[str, Any] = {}
        self._red_packet_tasks: dict[str, set[asyncio.Task]] = {}
        self._bridge_runners: dict[str, web.AppRunner] = {}
        self._accounts_save_lock = asyncio.Lock()
        self._deleted_accounts_save_lock = asyncio.Lock()
        self._base_dir = Path(app._base_dir)
        self._accounts_file = self._base_dir / 'data' / 'embedded_qq' / 'accounts.json'
        self._deleted_accounts_file = self._accounts_file.with_name('deleted_accounts.json')
        self._accounts_file.parent.mkdir(parents=True, exist_ok=True)
        self._installer = QQInstaller(self._base_dir / 'data' / 'qq')
        self._deleted_bot_ids = self._load_deleted_accounts()
        self._load_accounts()

    @property
    def enabled(self) -> bool:
        return bool(cfg.get('settings', 'embedded_qq.enabled', True))

    @property
    def headless(self) -> bool:
        if sys.platform.startswith('linux'):
            return True
        return bool(cfg.get('settings', 'embedded_qq.headless', True))

    @property
    def single_process(self) -> bool:
        # Electron 单进程模式可减少进程数，但会破坏部分 QQNT 版本的登录或注入，因此仅按需启用。
        return bool(cfg.get('settings', 'embedded_qq.single_process', False))

    @property
    def rss_target_mb(self) -> int:
        try:
            value = int(cfg.get('settings', 'embedded_qq.rss_target_mb', 400) or 0)
        except (TypeError, ValueError):
            value = 400
        return max(0, value)

    @property
    def swap_reclaim(self) -> bool:
        return bool(cfg.get('settings', 'embedded_qq.swap_reclaim', True))

    @property
    def linux_cgroup_helper(self) -> Path:
        raw = str(
            cfg.get(
                'settings',
                'embedded_qq.cgroup_helper',
                '/usr/local/sbin/elainaqq-cgroup',
            )
            or ''
        )
        return Path(raw)

    @staticmethod
    def _valid_id(bot_id: str) -> bool:
        return bool(re.fullmatch(r'[A-Za-z0-9._-]{1,80}', bot_id))

    def _data_dir(self, bot_id: str) -> Path:
        raw = str(cfg.get('settings', 'embedded_qq.data_dir', 'data/qq') or 'data/qq')
        base = Path(raw)
        if not base.is_absolute():
            base = self._base_dir / base
        safe_id = re.sub(r'[^A-Za-z0-9._-]', '_', bot_id).strip('._') or 'account'
        result = base / safe_id
        result.mkdir(parents=True, exist_ok=True)
        return result

    def _data_dir_path(self, bot_id: str) -> Path:
        raw = str(cfg.get('settings', 'embedded_qq.data_dir', 'data/qq') or 'data/qq')
        base = Path(raw)
        if not base.is_absolute():
            base = self._base_dir / base
        safe_id = re.sub(r'[^A-Za-z0-9._-]', '_', bot_id).strip('._') or 'account'
        return (base / safe_id).resolve()

    def _load_accounts(self) -> None:
        records: list[dict[str, Any]] = []
        if self._accounts_file.is_file():
            try:
                raw = json.loads(self._accounts_file.read_text(encoding='utf-8'))
                if isinstance(raw, list):
                    records.extend(item for item in raw if isinstance(item, dict))
            except Exception as exc:
                log.warning('读取 QQ 账号配置失败: %s', exc)
        configured = cfg.get('settings', 'embedded_qq.accounts', []) or []
        if isinstance(configured, list):
            records.extend(item for item in configured if isinstance(item, dict))
        for item in records:
            bot_id = str(item.get('bot_id') or item.get('uin') or '').strip()
            if not bot_id or bot_id in self.bots or bot_id in self._deleted_bot_ids or not self._valid_id(bot_id):
                continue
            self.bots[bot_id] = EmbeddedBot(
                bot_id=bot_id,
                bridge_port=self._parse_bridge_port(item.get('bridge_port')),
                qq_version_key=str(item.get('qq_version_key') or item.get('version_key') or self._installer.manager.detect_platform() or ''),
                uin=str(item.get('uin') or ''),
                nickname=str(item.get('nickname') or ''),
                force_quick_login=bool(item.get('force_quick_login', False)),
                enabled=bool(item.get('enabled', True)),
                created_at=float(item.get('created_at') or time.time()),
                last_seen=float(item.get('last_seen') or 0),
            )
        for bot in self.bots.values():
            self._assign_bridge_port(bot)

    @property
    def bridge_port_start(self) -> int:
        """返回内置 QQ 本机桥接端口的起始值。"""
        try:
            value = int(cfg.get('settings', 'embedded_qq.bridge_port_start', 30010))
        except (TypeError, ValueError):
            value = 30010
        return min(65535, max(1024, value))

    @staticmethod
    def _parse_bridge_port(value: Any) -> int:
        try:
            port = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return port if 1 <= port <= 65535 else 0

    def _assign_bridge_port(self, bot: EmbeddedBot) -> int:
        """为账号稳定分配从配置起始值递增的桥接端口。"""
        start = self.bridge_port_start
        reserved = {item.bridge_port for item in self.bots.values() if item is not bot and start <= item.bridge_port <= 65535}
        main_port = self._parse_bridge_port(cfg.get('settings', 'server.port', 5201))
        if main_port:
            reserved.add(main_port)
        if start <= bot.bridge_port <= 65535 and bot.bridge_port not in reserved:
            return bot.bridge_port
        for port in range(start, 65536):
            if port not in reserved:
                bot.bridge_port = port
                return port
        raise RuntimeError(f'内置 QQ 桥接端口已耗尽: {start}-65535')

    def _load_deleted_accounts(self) -> set[str]:
        if not self._deleted_accounts_file.is_file():
            return set()
        try:
            raw = json.loads(self._deleted_accounts_file.read_text(encoding='utf-8'))
            return {str(item) for item in raw if self._valid_id(str(item))} if isinstance(raw, list) else set()
        except Exception as exc:
            log.warning('读取已删除 QQ 账号列表失败: %s', exc)
            return set()

    async def _save_deleted_accounts(self) -> None:
        async with self._deleted_accounts_save_lock:
            try:
                await write_json(self._deleted_accounts_file, sorted(self._deleted_bot_ids))
            except Exception as exc:
                log.error('保存已删除 QQ 账号列表失败: %s', exc)

    async def _save_accounts(self) -> None:
        async with self._accounts_save_lock:
            try:
                await write_json(self._accounts_file, [bot.persisted() for bot in self.bots.values()])
            except Exception as exc:
                log.error('保存 QQ 账号配置失败: %s', exc)

    def _normalize_version_key(self, version_key: str = '') -> str:
        key = str(version_key or self._installer.manager.detect_platform() or '').strip()
        if not key:
            raise ValueError('当前系统没有可用的 QQ 客户端版本')
        if key not in self._installer.manager.compatible_version_keys():
            raise ValueError('所选 QQ 版本与当前系统不兼容')
        return key

    async def create_bot(
        self,
        bot_id: str,
        nickname: str = '',
        uin: str = '',
        qq_version_key: str = '',
        force_quick_login: bool = False,
    ) -> EmbeddedBot:
        bot_id = str(bot_id or uin).strip()
        if not self._valid_id(bot_id):
            raise ValueError('bot_id 只能包含字母、数字、点、下划线和短横线，长度 1-80')
        if bot_id in self._deleted_bot_ids:
            self._deleted_bot_ids.discard(bot_id)
            await self._save_deleted_accounts()
        bot = self.bots.get(bot_id)
        if bot is None:
            bot = EmbeddedBot(
                bot_id=bot_id,
                bridge_port=0,
                qq_version_key=self._normalize_version_key(qq_version_key),
                uin=str(uin or ''),
                nickname=str(nickname or ''),
                force_quick_login=bool(force_quick_login),
            )
            self.bots[bot_id] = bot
            self._assign_bridge_port(bot)
        else:
            bot.nickname = str(nickname or bot.nickname)
            bot.uin = str(uin or bot.uin)
            if qq_version_key:
                if bot.process and bot.process.returncode is None:
                    raise ValueError('请先停止机器人再切换 QQ 版本')
                bot.qq_version_key = self._normalize_version_key(qq_version_key)
            bot.force_quick_login = bool(force_quick_login)
        if not bot.qq_version_key:
            bot.qq_version_key = self._normalize_version_key()
        await self._save_accounts()
        return bot

    async def set_bot_version(self, bot_id: str, version_key: str) -> EmbeddedBot:
        bot = self.bots.get(bot_id)
        if not bot:
            raise ValueError('账号不存在')
        if bot.process and bot.process.returncode is None:
            raise ValueError('请先停止机器人再切换 QQ 版本')
        bot.qq_version_key = self._normalize_version_key(version_key)
        bot.status = 'offline' if self._find_qq_path(bot) else 'not_installed'
        bot.error = ''
        await self._save_accounts()
        return bot

    async def set_force_quick_login(self, bot_id: str, enabled: bool) -> EmbeddedBot:
        bot = self.bots.get(bot_id)
        if not bot:
            raise ValueError('账号不存在')
        if bot.process and bot.process.returncode is None:
            raise ValueError('请先停止机器人再切换强制快速登录')
        bot.force_quick_login = bool(enabled)
        await self._save_accounts()
        return bot

    def _bridge_entry(self) -> Path:
        configured = os.environ.get('ELAINAQQ_BRIDGE_ENTRY') or cfg.get('settings', 'embedded_qq.bridge_entry', '')
        candidates = [Path(str(configured))] if configured else []
        candidates.append(self._base_dir / 'core' / 'runtime' / 'embedded' / 'bridge' / 'elainaqq-runtime.mjs')
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError('未找到 ElainaQQ QQ 运行时入口: core/runtime/embedded/bridge/elainaqq-runtime.mjs')

    def _qq_path(self, bot: EmbeddedBot) -> Path:
        candidate = self._find_qq_path(bot)
        if not candidate:
            info = QQ_VERSIONS.get(bot.qq_version_key, {})
            version = str(info.get('version') or bot.qq_version_key)
            raise FileNotFoundError(f'未安装机器人所选 QQ {version}，请先在 Web 面板安装')
        return candidate

    def _find_qq_path(self, bot: EmbeddedBot | None = None) -> Path | None:
        if bot and bot.qq_version_key:
            candidate = self._installer.get_qq_path(bot.qq_version_key)
            return candidate.resolve() if candidate and candidate.is_file() else None
        configured = cfg.get('settings', 'embedded_qq.qq_path', '') or os.environ.get('QQ_PATH', '')
        candidate = Path(str(configured)) if configured else self._installer.get_qq_path()
        if candidate and candidate.is_dir():
            names = ('QQ.exe', 'qq', 'QQ') if os.name == 'nt' else ('qq', 'QQ', 'QQ.exe')
            candidate = next((candidate / name for name in names if (candidate / name).is_file()), candidate)
        if not candidate or not candidate.is_file():
            return None
        return candidate.resolve()

    def qq_ready(self, bot: EmbeddedBot | None = None) -> bool:
        if sys.platform.startswith('linux'):
            return bool(self._find_qq_path(bot))
        return bool(cfg.get('settings', 'embedded_qq.command', '') or self._find_qq_path(bot))

    async def _ensure_xvfb(self) -> str:
        if not sys.platform.startswith('linux'):
            return ''
        async with self._xvfb_lock:
            if self._xvfb_process and self._xvfb_process.returncode is None:
                return self._xvfb_display

            executable = shutil.which('Xvfb')
            if not executable:
                raise RuntimeError('Linux 无头运行需要 Xvfb，请先安装 xorg-x11-server-Xvfb 或 xvfb')
            display_number = next(
                (number for number in range(90, 200) if not Path(f'/tmp/.X{number}-lock').exists() and not Path(f'/tmp/.X11-unix/X{number}').exists()), None
            )
            if display_number is None:
                raise RuntimeError('没有可用的 Xvfb display')

            display = f':{display_number}'
            process = await asyncio.create_subprocess_exec(
                executable,
                display,
                '-screen',
                '0',
                '1080x760x16',
                '+extension',
                'GLX',
                '+render',
                '-nolisten',
                'tcp',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            socket_path = Path(f'/tmp/.X11-unix/X{display_number}')
            for _ in range(50):
                if socket_path.exists():
                    self._xvfb_process = process
                    self._xvfb_display = display
                    return display
                if process.returncode is not None:
                    break
                await asyncio.sleep(0.1)
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            with contextlib.suppress(Exception):
                await process.wait()
            raise RuntimeError(f'Xvfb 启动失败: {display}')

    async def _stop_xvfb(self) -> None:
        async with self._xvfb_lock:
            process = self._xvfb_process
            self._xvfb_process = None
            self._xvfb_display = ''
            if not process or process.returncode is not None:
                return
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()

    def _command(self, bot: EmbeddedBot, data_dir: Path) -> tuple[list[str], dict[str, str]]:
        configured = cfg.get('settings', 'embedded_qq.command', '')
        if configured and not sys.platform.startswith('linux'):
            if isinstance(configured, list):
                return [str(item) for item in configured], {}
            return shlex.split(str(configured), posix=os.name != 'nt'), {}
        qq_path = self._qq_path(bot)
        launcher = QQLauncher(qq_path, self._bridge_entry())
        if sys.platform.startswith('linux'):
            command = launcher.command(
                data_dir,
                headless=True,
                quick_login=bot.uin if bot.force_quick_login else '',
                linux_display=self._xvfb_display,
            )
            command = self._linux_cgroup_command(bot, command)
            return command, dict(launcher.launch_env)
        if os.name != 'nt':
            try:
                qq_path.relative_to(self._installer.install_dir.resolve())
            except ValueError:
                launcher = launcher.writable_runtime(self._installer.base_dir / 'runtime', force_copy=True)
        try:
            command = launcher.command(
                data_dir,
                headless=self.headless,
                single_process=self.single_process,
                quick_login=bot.uin if bot.force_quick_login else '',
            )
            return command, dict(launcher.launch_env)
        except PermissionError:
            # 系统安装包通常归 root 所有；所有账号共享一份可写运行时副本，账号数据仍保持隔离。
            runtime_root = self._base_dir / 'data' / 'qq_runtime'
            launcher = launcher.writable_runtime(runtime_root)
            command = launcher.command(
                data_dir,
                headless=self.headless,
                single_process=self.single_process,
                quick_login=bot.uin if bot.force_quick_login else '',
            )
            return command, dict(launcher.launch_env)

    @staticmethod
    def _command_qq_path(command: list[str]) -> Path | None:
        for item in command:
            candidate = Path(str(item))
            if candidate.name.lower() in {'qq', 'qq.exe', 'linuxqq'} and candidate.is_file():
                return candidate.resolve()
        return None

    def _packet_backend_env(self) -> dict[str, str]:
        mode = str(
            os.environ.get('ELAINAQQ_PACKET_BACKEND')
            or cfg.get('settings', 'embedded_qq.packet_backend', 'auto')
            or 'auto'
        )
        result = {'ELAINAQQ_PACKET_BACKEND': mode}

        platform_name = 'win32' if os.name == 'nt' else 'darwin' if sys.platform == 'darwin' else 'linux'
        machine = platform.machine().lower()
        arch = 'arm64' if machine in {'arm64', 'aarch64'} else 'x64' if machine in {'amd64', 'x86_64'} else machine
        napcat_root = Path(
            os.environ.get('NAPCAT_ROOT')
            or str(self._base_dir.parent / 'NapCatQQ')
        )

        configured_native = (
            os.environ.get('ELAINAQQ_PACKET_NATIVE_PATH')
            or cfg.get('settings', 'embedded_qq.packet_native_path', '')
        )
        configured_offsets = (
            os.environ.get('ELAINAQQ_PACKET_OFFSETS_PATH')
            or cfg.get('settings', 'embedded_qq.packet_offsets_path', '')
        )
        native_path = Path(str(configured_native)) if configured_native else (
            napcat_root
            / 'packages'
            / 'napcat-native'
            / 'napi2native'
            / f'napi2native.{platform_name}.{arch}.node'
        )
        offsets_path = Path(str(configured_offsets)) if configured_offsets else (
            napcat_root / 'packages' / 'napcat-core' / 'external' / 'napi2native.json'
        )
        if configured_native and not native_path.is_absolute():
            native_path = self._base_dir / native_path
        if configured_offsets and not offsets_path.is_absolute():
            offsets_path = self._base_dir / offsets_path
        if native_path.is_file():
            result['ELAINAQQ_PACKET_NATIVE_PATH'] = str(native_path.resolve())
        if offsets_path.is_file():
            result['ELAINAQQ_PACKET_OFFSETS_PATH'] = str(offsets_path.resolve())
        return result

    def _env(
        self,
        bot: EmbeddedBot,
        data_dir: Path,
        command: list[str] | None = None,
        launch_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        manager_url = f'http://127.0.0.1:{self._assign_bridge_port(bot)}'
        env = os.environ.copy()
        configured_command = cfg.get('settings', 'embedded_qq.command', '') if not sys.platform.startswith('linux') else ''
        bridge_entry = ''
        if not configured_command:
            bridge_entry = str(self._bridge_entry())
        else:
            configured_bridge = os.environ.get('ELAINAQQ_BRIDGE_ENTRY') or cfg.get('settings', 'embedded_qq.bridge_entry', '')
            if configured_bridge and Path(str(configured_bridge)).is_file():
                bridge_entry = str(Path(str(configured_bridge)).resolve())

        env.update(
            {
                'ELAINAQQ_EMBEDDED': '1',
                'ELAINAQQ_BOT_ID': bot.bot_id,
                'ELAINAQQ_MANAGER_URL': manager_url,
                'ELAINAQQ_DATA_DIR': str(data_dir),
                'ELAINAQQ_BOT_UIN': bot.uin,
                'ELAINAQQ_ONEBOT_ACTIONS': json.dumps(get_supported_actions(), ensure_ascii=True),
                'HOME': str(data_dir),
                'ELAINAQQ_HEADLESS': '1' if self.headless else '0',
            }
        )
        env.update(self._packet_backend_env())
        if os.name == 'nt':
            # Windows 启动器不会转发任意 Chromium 参数；QQ 会从进程环境读取这些路径，
            # 因此每个内置账号仍能获得独立会话目录。
            app_data = data_dir / 'appdata'
            local_data = data_dir / 'localappdata'
            app_data.mkdir(parents=True, exist_ok=True)
            local_data.mkdir(parents=True, exist_ok=True)
            env.update(
                {
                    'APPDATA': str(app_data),
                    'LOCALAPPDATA': str(local_data),
                    'USERPROFILE': str(data_dir / 'profile'),
                }
            )
        if sys.platform.startswith('linux'):
            env.pop('NODE_OPTIONS', None)
            env.pop('NODE_PATH', None)
            env['MALLOC_ARENA_MAX'] = '2'
            env['MALLOC_TRIM_THRESHOLD_'] = '131072'
        if bridge_entry:
            env['ELAINAQQ_BRIDGE_ENTRY'] = bridge_entry
        if launch_env:
            env.update(launch_env)

        command_qq = self._command_qq_path(command or [])
        configured_qq = cfg.get('settings', 'embedded_qq.qq_path', '') or os.environ.get('QQ_PATH', '')
        if command_qq:
            env['QQ_PATH'] = str(command_qq)
        elif configured_qq:
            env['QQ_PATH'] = str(Path(str(configured_qq)).resolve())
        elif not configured_command:
            env['QQ_PATH'] = str(self._qq_path(bot))
        elif command:
            for item in command:
                executable = Path(item)
                if executable.is_file() and executable.name.lower() in {'qq', 'qq.exe', 'linuxqq'}:
                    env['QQ_PATH'] = str(executable.resolve())
                    break
        return env

    async def _start_bridge(self, bot: EmbeddedBot) -> None:
        """为单个内置 QQ 启动仅限本机访问的控制桥接服务。"""
        if bot.bot_id in self._bridge_runners:
            return

        async def read_payload(request: web.Request) -> dict[str, Any]:
            try:
                payload = await request.json()
            except (ValueError, UnicodeDecodeError) as exc:
                raise web.HTTPBadRequest(text='请求正文必须是 JSON 对象') from exc
            if not isinstance(payload, dict):
                raise web.HTTPBadRequest(text='JSON 根节点必须是对象')
            incoming_bot_id = str(payload.get('bot_id') or '')
            if incoming_bot_id and incoming_bot_id != bot.bot_id:
                raise web.HTTPForbidden(text='账号与桥接端口不匹配')
            payload['bot_id'] = bot.bot_id
            return payload

        async def handle_event(request: web.Request) -> web.Response:
            handled = await self.handle_event(await read_payload(request))
            if not handled:
                raise web.HTTPServiceUnavailable(text='内置 QQ 未初始化')
            return web.json_response({'success': True})

        async def handle_red_packet(request: web.Request) -> web.Response:
            handled = await self.handle_red_packet(await read_payload(request))
            if not handled:
                raise web.HTTPServiceUnavailable(text='内置 QQ 红包接口未初始化')
            return web.json_response({'success': True})

        async def poll_control(request: web.Request) -> web.Response:
            requested = str(request.query.get('bot_id') or '')
            if requested and requested != bot.bot_id:
                raise web.HTTPForbidden(text='账号与桥接端口不匹配')
            command = await self.next_control_command(bot.bot_id)
            if command is None:
                return web.Response(status=204)
            return web.json_response(command)

        async def resolve_control(request: web.Request) -> web.Response:
            payload = await read_payload(request)
            if not self.resolve_control_command(bot.bot_id, payload):
                raise web.HTTPNotFound(text='命令不存在或已过期')
            return web.json_response({'success': True})

        bridge_app = web.Application(client_max_size=4 * 1024 * 1024)
        bridge_app.add_routes(
            [
                web.post('/api/embedded/events', handle_event),
                web.post('/api/embedded/red-packets', handle_red_packet),
                web.get('/api/embedded/control/poll', poll_control),
                web.post('/api/embedded/control/result', resolve_control),
            ]
        )
        runner = web.AppRunner(bridge_app, access_log=None)
        await runner.setup()

        start = self.bridge_port_start
        assigned = self._assign_bridge_port(bot)
        reserved = {item.bridge_port for item in self.bots.values() if item is not bot and start <= item.bridge_port <= 65535}
        main_port = self._parse_bridge_port(cfg.get('settings', 'server.port', 5201))
        if main_port:
            reserved.add(main_port)
        candidates = itertools.chain(
            (assigned,),
            range(start, assigned),
            range(assigned + 1, 65536),
        )
        last_error: OSError | None = None
        for port in candidates:
            if port in reserved:
                continue
            site = web.TCPSite(runner, '127.0.0.1', port)
            try:
                await site.start()
            except OSError as exc:
                last_error = exc
                with contextlib.suppress(Exception):
                    await site.stop()
                continue
            bot.bridge_port = port
            self._bridge_runners[bot.bot_id] = runner
            await self._save_accounts()
            log.debug('内置 QQ 桥接服务已启动: 127.0.0.1:%s [%s]', port, bot.bot_id)
            return

        await runner.cleanup()
        raise RuntimeError(f'无法绑定内置 QQ 桥接端口 {start}-65535') from last_error

    async def _stop_bridge(self, bot_id: str) -> None:
        runner = self._bridge_runners.pop(bot_id, None)
        if runner is not None:
            with contextlib.suppress(Exception):
                await runner.cleanup()

    def _linux_cgroup_command(
        self,
        bot: EmbeddedBot,
        command: list[str],
    ) -> list[str]:
        if not sys.platform.startswith('linux') or self.rss_target_mb <= 0:
            return command
        helper = self.linux_cgroup_helper
        if not helper.is_file() or not shutil.which('sudo'):
            return command
        target = self.rss_target_mb * 1024 * 1024
        script = (
            'helper=$1; bot=$2; target=$3; shift 3; '
            'if ! sudo -n "$helper" enter "$bot" "$$" "$target"; then '
            'echo "[ElainaQQ] cgroup 初始化失败，继续启动 QQ" >&2; fi; '
            'exec "$@"'
        )
        return [
            '/bin/sh',
            '-c',
            script,
            'elainaqq',
            str(helper),
            bot.bot_id,
            str(target),
            *command,
        ]

    def _reclaim_linux_cgroup(
        self,
        bot_id: str,
        target: int,
        amount: int,
    ) -> bool:
        if not sys.platform.startswith('linux') or not self.swap_reclaim:
            return False
        helper = self.linux_cgroup_helper
        if not helper.is_file() or not shutil.which('sudo'):
            return False
        try:
            result = subprocess.run(
                [
                    'sudo',
                    '-n',
                    str(helper),
                    'reclaim',
                    bot_id,
                    str(target),
                    str(amount),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode:
                log.debug(
                    'Linux QQ cgroup 回收跳过 [%s]: %s',
                    bot_id,
                    (result.stderr or result.stdout).strip(),
                )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    async def start_enabled(self) -> None:
        if not self.enabled:
            return
        for bot_id, bot in list(self.bots.items()):
            if bot.enabled:
                await self.start(bot_id)

    async def start(self, bot_id: str) -> EmbeddedBot:
        async with self._lock:
            bot = self.bots.get(bot_id)
            if bot is None:
                bot = await self.create_bot(bot_id)
            if bot.process and bot.process.returncode is None:
                return bot
            if not self.qq_ready(bot):
                bot.enabled = True
                bot.status, bot.error = 'not_installed', ''
                bot.qr_code = bot.qr_url = ''
                await self._save_accounts()
                return bot
            bot.enabled = True
            bot.status, bot.error = 'logging_in', ''
            bot.qr_code = bot.qr_url = ''
            data_dir = self._data_dir(bot.bot_id)
            try:
                await self._start_bridge(bot)
                if sys.platform.startswith('linux'):
                    await self._ensure_xvfb()
                command, launch_env = await asyncio.to_thread(self._command, bot, data_dir)
                runtime = launch_env.get('ELAINAQQ_HEADLESS_RUNTIME', '')
                bot.launch_mode = runtime or 'elainaqq-runtime'
                command_qq = self._command_qq_path(command)
                kwargs: dict[str, Any] = {
                    'env': self._env(bot, data_dir, command, launch_env),
                    'cwd': str(
                        self._bridge_entry().parent if command_qq and sys.platform.startswith('linux') else command_qq.parent if command_qq else data_dir
                    ),
                    'stdout': asyncio.subprocess.PIPE,
                    'stderr': asyncio.subprocess.STDOUT,
                }
                if os.name == 'nt':
                    flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
                    if self.headless:
                        flags |= getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    kwargs['creationflags'] = flags
                else:
                    kwargs['start_new_session'] = True
                bot.process = await asyncio.create_subprocess_exec(*command, **kwargs)
                bot.output_task = asyncio.create_task(self._read_output(bot), name=f'qq-output-{bot.bot_id}')
                if sys.platform.startswith('linux'):
                    bot.reclaim_task = asyncio.create_task(
                        self._reclaim_process_memory(bot, bot.process),
                        name=f'qq-reclaim-{bot.bot_id}',
                    )
                await self._save_accounts()
                log.debug(
                    '内置 QQ 已启动: %s (PID=%s, mode=%s, bridge=127.0.0.1:%s)',
                    bot.bot_id,
                    bot.process.pid,
                    bot.launch_mode,
                    bot.bridge_port,
                )
            except Exception as exc:
                await self._stop_bridge(bot.bot_id)
                bot.status, bot.error = 'error', public_text(exc)
                await self._save_accounts()
                log.error('内置 QQ 启动失败 [%s]: %s', bot.bot_id, public_text(exc), exc_info=True)
            return bot

    @staticmethod
    def _process_tree_pids(root_pid: int, data_dir: Path) -> set[int]:
        pids: set[int] = {root_pid}
        with contextlib.suppress(psutil.Error, OSError):
            root = psutil.Process(root_pid)
            pids.update(child.pid for child in root.children(recursive=True))

        marker = os.path.normcase(str(data_dir.resolve()))
        for item in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                command = ' '.join(item.info.get('cmdline') or [])
                if marker not in os.path.normcase(command):
                    continue
                pids.add(item.pid)
                parent = item.parent()
                while parent and parent.name().lower() in {'qq', 'qq.exe', 'linuxqq'}:
                    pids.add(parent.pid)
                    parent = parent.parent()
            except (psutil.Error, OSError):
                continue
        return pids

    @staticmethod
    def _kill_pids(pids: set[int]) -> None:
        processes = []
        for pid in pids:
            with contextlib.suppress(psutil.Error, OSError):
                processes.append(psutil.Process(pid))
        for item in sorted(processes, key=lambda value: value.pid, reverse=True):
            with contextlib.suppress(psutil.Error, OSError):
                item.kill()
        with contextlib.suppress(psutil.Error, OSError):
            psutil.wait_procs(processes, timeout=5)

    async def _terminate_process_tree(
        self,
        process: asyncio.subprocess.Process,
        data_dir: Path,
        captured_pids: set[int],
    ) -> None:
        if os.name == 'nt':
            await asyncio.to_thread(
                subprocess.run,
                ['taskkill', '/PID', str(process.pid), '/T', '/F'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), 10)
        else:
            kill_process_group = cast(Any, os).killpg
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                kill_process_group(process.pid, signal.SIGTERM)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), 5)
            if process.returncode is None:
                force_signal = cast(Any, signal).SIGKILL
                with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                    kill_process_group(process.pid, force_signal)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), 5)
        remaining = captured_pids | self._process_tree_pids(process.pid, data_dir)
        await asyncio.to_thread(self._kill_pids, remaining)
        if process.returncode is None:
            with contextlib.suppress(Exception):
                process.kill()
            with contextlib.suppress(Exception):
                await process.wait()

    async def stop(self, bot_id: str, disable: bool = True) -> bool:
        bot = self.bots.get(bot_id)
        if not bot:
            return True
        if bot.reclaim_task and bot.reclaim_task is not asyncio.current_task():
            bot.reclaim_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bot.reclaim_task
        bot.reclaim_task = None
        process = bot.process
        if process:
            self._stopping.add(bot_id)
            try:
                data_dir = self._data_dir_path(bot.bot_id)
                captured_pids = await asyncio.to_thread(self._process_tree_pids, process.pid, data_dir)
                await self._terminate_process_tree(process, data_dir, captured_pids)
                bot.process = None
                if bot.output_task and bot.output_task is not asyncio.current_task():
                    with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(bot.output_task, 3)
                bot.output_task = None
            finally:
                self._stopping.discard(bot_id)
        self._unregister_bot_aliases(bot)
        self._cancel_control_commands(bot_id)
        await self._stop_bridge(bot_id)
        bot.status = 'offline'
        if disable:
            bot.enabled = False
        await self._save_accounts()
        if not any(item.process and item.process.returncode is None for item in self.bots.values()):
            await self._stop_xvfb()
        return True

    async def delete_bot(self, bot_id: str, cleanup_data: bool = False) -> bool:
        """删除一个内置 QQ 账号占位，并可选清理其独立登录目录。"""
        bot = self.bots.get(bot_id)
        if not bot:
            return False
        await self.stop(bot_id, disable=False)
        data_dir = self._data_dir_path(bot.bot_id)
        self.bots.pop(bot_id, None)
        self._deleted_bot_ids.add(bot_id)
        await self._save_deleted_accounts()
        await self._save_accounts()
        if cleanup_data and data_dir.exists():
            base_raw = str(cfg.get('settings', 'embedded_qq.data_dir', 'data/qq') or 'data/qq')
            base_dir = Path(base_raw)
            if not base_dir.is_absolute():
                base_dir = self._base_dir / base_dir
            base_dir = base_dir.resolve()
            if data_dir.parent != base_dir:
                raise ValueError('账号数据目录不在内置 QQ 数据根目录内')
            await asyncio.to_thread(shutil.rmtree, data_dir)
        return True

    async def stop_all(self) -> None:
        await asyncio.gather(*(self.stop(bot_id, disable=False) for bot_id in list(self.bots)), return_exceptions=True)
        await self._stop_xvfb()

    async def stop_version(self, version_key: str) -> None:
        targets = [bot.bot_id for bot in self.bots.values() if bot.qq_version_key == version_key]
        await asyncio.gather(*(self.stop(bot_id, disable=False) for bot_id in targets), return_exceptions=True)

    def _control_queue(self, bot_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue = self._control_queues.get(bot_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=32)
            self._control_queues[bot_id] = queue
        return queue

    async def next_control_command(
        self,
        bot_id: str,
        timeout: float = 25.0,
    ) -> dict[str, Any] | None:
        bot = self.bots.get(bot_id)
        if not bot or not bot.process or bot.process.returncode is not None:
            return None
        try:
            return await asyncio.wait_for(self._control_queue(bot_id).get(), timeout)
        except TimeoutError:
            return None

    def resolve_control_command(self, bot_id: str, payload: dict[str, Any]) -> bool:
        request_id = str(payload.get('request_id') or '')
        pending = self._control_futures.get(request_id)
        if not pending:
            return False
        pending_bot_id, future = pending
        if pending_bot_id != bot_id or future.done():
            return False
        result = payload.get('result')
        future.set_result(result if isinstance(result, dict) else {})
        return True

    def _cancel_control_commands(self, bot_id: str, message: str = '机器人已停止') -> None:
        for _request_id, (pending_bot_id, future) in list(self._control_futures.items()):
            if pending_bot_id == bot_id and not future.done():
                future.set_result(
                    action_failed(message, 1500)
                )
        queue = self._control_queues.pop(bot_id, None)
        if queue:
            while not queue.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()

    async def _control_call(
        self,
        bot_id: str,
        command: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        bot = self.bots.get(bot_id)
        if not bot or not bot.process or bot.process.returncode is not None:
            return action_failed('机器人未运行', 1404)
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._control_futures[request_id] = (bot_id, future)
        try:
            await asyncio.wait_for(
                self._control_queue(bot_id).put({'request_id': request_id, **command}),
                timeout=2,
            )
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            return action_failed('ElainaQQ QQ 运行时响应超时', 1500)
        finally:
            self._control_futures.pop(request_id, None)

    async def action(self, bot_id: str, action: str, params: dict | None = None) -> dict:
        return await self._control_call(
            bot_id,
            {'type': 'action', 'action': action, 'params': params or {}},
        )

    def register_red_packet_listener(self, owner: str, callback) -> None:
        """注册内置 QQ 原生红包回调；同一 owner 热重载时自动替换。"""
        owner = str(owner or '').strip()
        if not owner or not callable(callback):
            raise ValueError('红包监听需要有效的 owner 和回调方法')
        self.unregister_red_packet_listener(owner)
        self._red_packet_listeners[owner] = callback

    def unregister_red_packet_listener(self, owner: str) -> None:
        owner = str(owner or '').strip()
        self._red_packet_listeners.pop(owner, None)
        for task in self._red_packet_tasks.pop(owner, set()):
            if not task.done():
                task.cancel()

    async def _run_red_packet_listener(
        self,
        owner: str,
        callback,
        self_id: str,
        packet: dict[str, Any],
    ) -> None:
        try:
            with api_call_source(owner):
                result = callback(self_id, packet)
                if inspect.isawaitable(result):
                    await result
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('内置 QQ 红包监听异常: %s [%s]', owner, self_id)

    async def handle_red_packet(self, payload: dict[str, Any]) -> bool:
        """将内置红包转换为标准通知后，再执行原生能力回调。"""
        bot_id = str(payload.get('bot_id') or '').strip()
        bot = self.bots.get(bot_id)
        packet = payload.get('red_packet')
        if bot is None or not isinstance(packet, dict):
            return False
        bot.last_seen = time.time()
        self_id = str(payload.get('self_id') or bot.uin or bot_id)
        event = {
            'time': int(time.time()),
            'self_id': self_id,
            'post_type': 'notice',
            'notice_type': 'elaina_red_packet',
            'sub_type': 'receive',
            'user_id': packet.get('sender_id') or 0,
            'group_id': packet.get('group_id') or None,
            'red_packet': dict(packet),
        }
        if not await self.app.ingest_event(event, self_id):
            return False
        for owner, callback in tuple(self._red_packet_listeners.items()):
            task = asyncio.create_task(
                self._run_red_packet_listener(
                    owner, callback, self_id, dict(packet),
                ),
                name=f'red-packet-{owner}-{self_id}',
            )
            tasks = self._red_packet_tasks.setdefault(owner, set())
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        return True

    def _red_packet_bot_id(self, self_id: str) -> str:
        self_id = str(self_id or '').strip()
        if self_id in self.bots:
            return self_id
        for bot_id, bot in self.bots.items():
            if str(bot.uin or '') == self_id:
                return bot_id
        return ''

    async def grab_red_packet(self, self_id: str, bill_no: str) -> dict[str, Any]:
        """通过指定内置 QQ 账号直接调用原生 grabRedBag。"""
        bot_id = self._red_packet_bot_id(self_id)
        bill_no = str(bill_no or '').strip()
        if not bot_id:
            return {
                'ok': False, 'amount': 0, 'err_code': -5,
                'err_msg': '内置 QQ 账号不存在',
            }
        if not bill_no:
            return {
                'ok': False, 'amount': 0, 'err_code': -6,
                'err_msg': '缺少红包 bill_no',
            }
        response = await self._control_call(
            bot_id,
            {'type': 'grab_red_packet', 'bill_no': bill_no},
            timeout=5,
        )
        if response.get('status') == 'failed':
            return {
                'ok': False,
                'amount': 0,
                'err_code': int(response.get('retcode') or -7),
                'err_msg': str(response.get('message') or '红包领取接口失败'),
            }
        result = response.get('data')
        if isinstance(result, dict):
            return result
        return {
            'ok': False, 'amount': 0, 'err_code': -8,
            'err_msg': '红包领取接口返回格式错误',
        }

    async def refresh_qr(self, bot_id: str) -> dict:
        bot = self.bots.get(bot_id)
        if not bot:
            return {'success': False, 'error': '账号不存在'}
        result = await self._control_call(bot_id, {'type': 'refresh_qr'})
        if result.get('status') == 'failed':
            return {'success': False, 'error': str(result.get('message') or '刷新二维码失败')}
        return result

    def _sync_qr_code(self, bot: EmbeddedBot) -> None:
        if bot.status == 'online':
            bot.qr_code = bot.qr_url = ''
            return
        return

    def _unregister_bot_aliases(self, bot: EmbeddedBot, keep: str = '') -> None:
        """清理账号切换过程中遗留的临时 bot_id 或旧 QQ 注册。"""
        keep = str(keep or '')
        aliases = {str(bot.bot_id or ''), str(bot.uin or '')}
        for alias in aliases:
            if alias and alias != keep:
                self.app.adapter.unregister_local_bot(alias)
        self.app.adapter.unregister_identity_alias(bot.bot_id)

    async def on_onebot_connected(self, bot_id: str, self_id: str) -> None:
        bot = self.bots.get(bot_id)
        if not bot:
            return
        self_id = str(self_id or '').strip()
        self._unregister_bot_aliases(bot, self_id)
        bot.uin = str(self_id)
        self.app.adapter.register_identity_alias(bot.bot_id, bot.uin)
        bot.status = 'online'
        bot.enabled = True
        bot.error = ''
        bot.qr_code = bot.qr_url = ''
        bot.last_seen = time.time()
        await self._save_accounts()
        if sys.platform.startswith('linux') and bot.process:
            if not bot.reclaim_task or bot.reclaim_task.done():
                bot.reclaim_task = asyncio.create_task(
                    self._reclaim_process_memory(bot, bot.process, (10, 50)),
                    name=f'qq-reclaim-{bot.bot_id}',
                )

    async def handle_event(self, payload: dict) -> bool:
        """接收 ElainaQQ QQ 运行时回传的状态和 OneBot 事件。"""
        bot_id = str(payload.get('bot_id') or payload.get('self_id') or '').strip()
        if not bot_id:
            return False
        bot = self.bots.get(bot_id)
        if not bot:
            return False
        bot.last_seen = time.time()

        runtime = payload.get('runtime')
        if isinstance(runtime, dict):
            previous_status = bot.status
            previous_uin = bot.uin
            incoming_uin = str(runtime.get('loginUin') or runtime.get('uin') or bot.uin)
            if previous_uin and incoming_uin and previous_uin != incoming_uin:
                self.app.adapter.unregister_local_bot(previous_uin)
                self.app.adapter.unregister_identity_alias(bot.bot_id)
            if incoming_uin and incoming_uin != bot.bot_id:
                self.app.adapter.unregister_local_bot(bot.bot_id)
            bot.status = str(runtime.get('status') or bot.status)
            if bot.status in {'logging_in', 'waiting_qr', 'authorizing', 'online'}:
                bot.enabled = True
            bot.uin = incoming_uin
            bot.nickname = str(runtime.get('nickname') or bot.nickname)
            if 'qrcodeBase64' in runtime or 'qrcode' in runtime:
                qr_code = str(runtime.get('qrcodeBase64') or runtime.get('qrcode') or '')
                if qr_code:
                    bot.qr_code = qr_code
            if 'qrcodeUrl' in runtime:
                qr_url = str(runtime.get('qrcodeUrl') or '')
                if qr_url:
                    bot.qr_url = qr_url
            bot.error = str(runtime.get('error') or '')
            if bot.status == 'online':
                bot.qr_code = bot.qr_url = ''
            if bot.uin and bot.status == 'online':
                self.app.adapter.register_identity_alias(bot.bot_id, bot.uin)
                self.app.adapter.register_local_bot(
                    bot.uin,
                    lambda action, params, bot_key=bot.bot_id: self.action(
                        bot_key,
                        action,
                        params,
                    ),
                )
            elif bot.uin and bot.status in {'offline', 'error'}:
                self._unregister_bot_aliases(bot)
            await self._save_accounts()

            if bot.status != previous_status and bot.status in {'online', 'offline', 'error'}:
                status_event = {
                    'time': int(time.time()),
                    'self_id': bot.uin or bot_id,
                    'post_type': 'meta_event',
                    'meta_event_type': 'lifecycle',
                    'sub_type': 'connect' if bot.status == 'online' else 'disconnect',
                    'status': bot.status,
                }
                if not await self.app.ingest_event(status_event, bot.uin or bot_id):
                    return False

        event = payload.get('event')
        return not isinstance(event, dict) or await self.app.ingest_event(event, bot.uin or bot_id)

    async def _reclaim_process_memory(
        self,
        bot: EmbeddedBot,
        process: asyncio.subprocess.Process,
        delays: tuple[int, ...] = (15, 60, 180, 300),
    ) -> None:
        try:
            cycle = 0
            while True:
                delay = delays[min(cycle, len(delays) - 1)]
                await asyncio.sleep(delay)
                if bot.process is not process or process.returncode is not None:
                    return
                before = await asyncio.to_thread(self._process_memory_usage, process.pid)
                target = self.rss_target_mb * 1024 * 1024
                swap = psutil.swap_memory()
                required = max(before['rss'] - target, 64 * 1024 * 1024)
                use_swap = bool(
                    self.swap_reclaim
                    and bot.status == 'online'
                    and target > 0
                    and before['rss'] > target + 32 * 1024 * 1024
                    and swap.free > required + 256 * 1024 * 1024
                )
                cgroup_reclaimed = False
                if use_swap:
                    cgroup_reclaimed = await asyncio.to_thread(
                        self._reclaim_linux_cgroup,
                        bot.bot_id,
                        target,
                        max(before['rss'] - target, 32 * 1024 * 1024),
                    )
                reclaimed = await asyncio.to_thread(
                    self._reclaim_process_pages,
                    process.pid,
                    use_swap and not cgroup_reclaimed,
                )
                self._memory_cache.pop(bot.bot_id, None)
                if use_swap:
                    await asyncio.sleep(3)
                    after = await asyncio.to_thread(self._process_memory_usage, process.pid)
                    log.info(
                        'Linux QQ RSS 已受控 [%s]: %.1f MB -> %.1f MB，Swap %.1f MB',
                        bot.bot_id,
                        before['rss'] / 1024 / 1024,
                        after['rss'] / 1024 / 1024,
                        after['swap'] / 1024 / 1024,
                    )
                else:
                    log.debug(
                        'Linux QQ 已回收闲置文件页 [%s]: %.1f MB',
                        bot.bot_id,
                        reclaimed['file'] / 1024 / 1024,
                    )
                cycle += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug('Linux QQ 文件页回收跳过 [%s]: %s', bot.bot_id, exc)
        finally:
            if bot.reclaim_task is asyncio.current_task():
                bot.reclaim_task = None

    @staticmethod
    def _reclaim_process_pages(root_pid: int, include_anonymous: bool = False) -> dict[str, int]:
        if not hasattr(os, 'pidfd_open'):
            return {'file': 0, 'anonymous': 0}

        class IOVec(ctypes.Structure):
            _fields_ = [('iov_base', ctypes.c_void_p), ('iov_len', ctypes.c_size_t)]

        libc = ctypes.CDLL(None, use_errno=True)
        process_madvise = getattr(libc, 'process_madvise', None)
        if process_madvise is None:
            return {'file': 0, 'anonymous': 0}
        process_madvise.argtypes = (
            ctypes.c_int,
            ctypes.POINTER(IOVec),
            ctypes.c_size_t,
            ctypes.c_int,
            ctypes.c_uint,
        )
        process_madvise.restype = ctypes.c_ssize_t

        try:
            root = psutil.Process(root_pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return {'file': 0, 'anonymous': 0}

        file_advised = 0
        anonymous_advised = 0
        anonymous: list[tuple[int, list[IOVec]]] = []
        for item in processes:
            file_mappings: list[IOVec] = []
            anonymous_mappings: list[IOVec] = []
            try:
                lines = Path(f'/proc/{item.pid}/maps').read_text().splitlines()
                for line in lines:
                    fields = line.split(maxsplit=5)
                    if len(fields) < 2 or 'r' not in fields[1] or 'p' not in fields[1]:
                        continue
                    name = fields[5].strip() if len(fields) >= 6 else ''
                    if name.startswith(('[stack', '[vdso', '[vvar', '[vsyscall', '/dev/shm', 'memfd:', '/SYSV')):
                        continue
                    start, end = (int(value, 16) for value in fields[0].split('-'))
                    vector = IOVec(start, end - start)
                    if name.startswith('/'):
                        file_mappings.append(vector)
                    elif not name or name == '[heap]' or name.startswith('[anon:'):
                        anonymous_mappings.append(vector)
                pidfd = os.pidfd_open(item.pid)
                try:
                    if include_anonymous and anonymous_mappings:
                        vectors = (IOVec * len(anonymous_mappings))(*anonymous_mappings)
                        process_madvise(pidfd, vectors, len(vectors), 20, 0)
                    if file_mappings:
                        vectors = (IOVec * len(file_mappings))(*file_mappings)
                        result = process_madvise(pidfd, vectors, len(vectors), 21, 0)
                        if result > 0:
                            file_advised += result
                finally:
                    os.close(pidfd)
                if include_anonymous and anonymous_mappings:
                    anonymous.append((item.pid, anonymous_mappings))
            except (OSError, ValueError, psutil.Error):
                continue

        if include_anonymous and anonymous:
            time.sleep(2)
            for pid, mappings in anonymous:
                try:
                    vectors = (IOVec * len(mappings))(*mappings)
                    pidfd = os.pidfd_open(pid)
                    try:
                        result = process_madvise(pidfd, vectors, len(vectors), 21, 0)
                        if result > 0:
                            anonymous_advised += result
                    finally:
                        os.close(pidfd)
                except OSError:
                    continue
        return {'file': file_advised, 'anonymous': anonymous_advised}

    @staticmethod
    def _process_memory_usage(root_pid: int) -> dict[str, int]:
        try:
            root = psutil.Process(root_pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return {'rss': 0, 'swap': 0}
        rss = 0
        swap = 0
        for item in processes:
            try:
                rss += int(item.memory_info().rss)
                swap += int(getattr(item.memory_full_info(), 'swap', 0) or 0)
            except (psutil.Error, OSError):
                continue
        return {'rss': rss, 'swap': swap}

    async def on_onebot_disconnected(self, bot_id: str, self_id: str) -> None:
        bot = self.bots.get(bot_id)
        if not bot or (bot.uin and bot.uin != str(self_id)):
            return
        running = bool(bot.process and bot.process.returncode is None)
        bot.status = 'logging_in' if running else 'offline'
        await self._save_accounts()

    def _memory_snapshot(self, bot: EmbeddedBot) -> dict[str, Any]:
        process = bot.process
        empty = {
            'memory_mb': 0.0,
            'memory_rss_mb': 0.0,
            'memory_pss_mb': 0.0,
            'memory_uss_mb': 0.0,
            'memory_swap_mb': 0.0,
            'memory_processes': 0,
        }
        if not process or process.returncode is not None:
            self._memory_cache.pop(bot.bot_id, None)
            return empty
        now = time.monotonic()
        cached = self._memory_cache.get(bot.bot_id)
        if cached and cached[1] == process.pid and now - cached[0] < 2.0:
            return cached[2].copy()
        try:
            root = psutil.Process(process.pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return empty
        seen: set[int] = set()
        rss = 0
        pss = 0
        uss = 0
        swap = 0
        count = 0
        for item in processes:
            try:
                if item.pid in seen or not item.is_running():
                    continue
                seen.add(item.pid)
                info = item.memory_info()
                rss += int(getattr(info, 'rss', 0) or 0)
                with contextlib.suppress(psutil.Error, OSError):
                    full_info = item.memory_full_info()
                    pss += int(getattr(full_info, 'pss', 0) or 0)
                    uss += int(getattr(full_info, 'uss', 0) or 0)
                    swap += int(getattr(full_info, 'swap', 0) or 0)
                count += 1
            except (psutil.Error, OSError):
                continue
        mib = 1024 * 1024
        result = {
            'memory_mb': round(rss / mib, 1),
            'memory_rss_mb': round(rss / mib, 1),
            'memory_pss_mb': round(pss / mib, 1),
            'memory_uss_mb': round(uss / mib, 1),
            'memory_swap_mb': round(swap / mib, 1),
            'memory_processes': count,
        }
        self._memory_cache[bot.bot_id] = (now, process.pid, result)
        return result.copy()

    @staticmethod
    def _is_qq_noise(line: str) -> bool:
        stripped = line.strip()
        if len(stripped) >= 12 and not stripped.translate(str.maketrans('', '', '▄▀█ ')):
            return True
        return any(
            pattern in line
            for pattern in (
                'DroppedFrame(',
                'Failed to connect to the bus:',
                'org.freedesktop.DBus.NameHasOwner',
                'org.freedesktop.systemd1.Manager.StartTransientUnit',
                'No suitable EGL configs found',
                'Failed to get config for surface',
                'CreateOffscreenGLSurface failed',
                'Could not create surface for info collection',
                'CollectGraphicsInfo failed',
                'Exiting GPU process due to errors during initialization',
                '[QQ hotUpdate]',
                'not mini app.',
                '[preload] succeeded.',
                '状态变更: logging_in {"qrcodeUrl":',
                '[LOGIN] onQRCodeGetPicture, qrcodeUrl:',
                '[LOGIN] 轮询已开始',
                '[LOGIN] onQRCodeSessionFailed: 1 3',
                'AddContentDecryptionModules called',
                'Widevine CDM path from switch:',
                'Widevine CDM path not set',
                'Widevine CDM not available',
                'argv[',
                'Boot Command:',
                'Creating pipe:',
                'resourcesPath:',
                'loadSymbolFromShell: dlsym failed PerfTrace',
                '[I] <MMKV',
                '[I] <MemoryFile',
                'linux-bugly: init bugly',
                'InitBuglyManager',
                'SetLogger',
                'fatalSetup',
                'GetDllPath:',
                'pub_key_path:',
                'BuglyManager/',
                '[BuglyService.cpp][registBugly]',
                '[BuglyService.cpp][registSignalHandler]',
                'registBugly/',
                '[BuglyService.cpp][setParam]',
                'setParam/',
                'StartWithOptions ',
                'PostDelayedTask ',
                '请扫描下面的二维码',
                '二维码解码URL:',
                '如果控制台二维码无法扫码',
                '二维码已保存到',
            )
        )

    @staticmethod
    def _qq_output_level(line: str) -> int:
        """为 QQ 子进程输出分配日志等级，正常登录链路仅在调试模式显示。"""
        lowered = line.casefold()
        warning_markers = (
            'error',
            'failed',
            'exception',
            'fatal',
            '启动失败',
            '登录失败',
            '加载失败',
            '初始化失败',
            '崩溃',
        )
        return logging.WARNING if any(marker in lowered for marker in warning_markers) else logging.DEBUG

    @staticmethod
    def _crash_dump_start(line: str) -> bool:
        return any(
            pattern in line
            for pattern in (
                '[BuglyManager.cpp][UploadBugly]',
                '[NativeCrashHandler.cpp]',
                '[BuglyService.cpp][buglySignalHandler]',
                'FATAL:electron/shell/browser/electron_browser_main_parts.cc',
            )
        )

    @staticmethod
    def _crash_dump_end(line: str) -> bool:
        return '[NativeCrashHandler.cpp][onUploadEnd]' in line or '[UploadTask.cpp][onUploadEnd]' in line or 'upload success' in line.lower()

    async def _read_output(self, bot: EmbeddedBot) -> None:
        process = bot.process
        if not process or not process.stdout:
            return
        suppress_crash_dump = False
        crash_reported = False
        crash_summary: list[str] = []
        error_summary: list[str] = []
        try:
            async for raw in process.stdout:
                line = public_text(raw.decode('utf-8', 'replace').rstrip())
                if not line or bot.bot_id in self._stopping:
                    continue
                if '二维码解码URL:' in line:
                    bot.qr_url = line.split('二维码解码URL:', 1)[1].strip()
                    bot.status = 'waiting_qr'
                    self._sync_qr_code(bot)
                    await self._save_accounts()
                elif '二维码已保存到' in line:
                    self._sync_qr_code(bot)
                    await self._save_accounts()
                if self._crash_dump_start(line):
                    suppress_crash_dump = True
                    if 'FATAL:' in line or '[BuglyService.cpp][buglySignalHandler]' in line:
                        crash_reported = True
                        if len(crash_summary) < 4:
                            crash_summary.append(line[-240:])
                    continue
                if suppress_crash_dump:
                    if '[BuglyService.cpp][buglySignalHandler]' in line:
                        crash_reported = True
                        if len(crash_summary) < 4:
                            crash_summary.append(line[-240:])
                    if (
                        any(
                            marker in line
                            for marker in (
                                'Signal name:',
                                'Message of signal code:',
                                'Error number of signal:',
                            )
                        )
                        and len(crash_summary) < 4
                    ):
                        crash_summary.append(line[-160:])
                    if self._crash_dump_end(line):
                        suppress_crash_dump = False
                    continue
                if not self._is_qq_noise(line):
                    level = self._qq_output_level(line)
                    log.log(level, '[QQ %s] %s', bot.bot_id, line)
                    if level >= logging.WARNING:
                        error_summary.append(line[-240:])
                        del error_summary[:-4]
        finally:
            with contextlib.suppress(Exception):
                await process.wait()
            was_stopping = bot.bot_id in self._stopping
            if bot.process is process:
                bot.process = None
                self._unregister_bot_aliases(bot)
                self._cancel_control_commands(bot.bot_id, 'QQ 进程已退出')
                if bot.status not in ('offline', 'error'):
                    bot.status = 'offline'
                await self._save_accounts()
            await self._stop_bridge(bot.bot_id)
            if not was_stopping and process.returncode not in (None, 0):
                detail = ' | '.join(crash_summary if crash_reported else error_summary)
                detail = detail or '未输出 native 崩溃详情'
                log.warning(
                    'QQ 无头进程已退出 [%s]，退出码: %s，%s',
                    bot.bot_id,
                    process.returncode,
                    detail,
                )
            if not was_stopping and bot.enabled and process.returncode not in (None, 0):
                bot.status = 'error'
                detail = ' | '.join(crash_summary if crash_reported else error_summary)
                bot.error = f'QQ 无头进程退出，退出码: {process.returncode}'
                if detail:
                    bot.error += f'（{detail}）'
                await self._save_accounts()

    def list_bots(self) -> list[dict[str, Any]]:
        result = []
        for bot in self.bots.values():
            if not bot.qq_version_key:
                bot.qq_version_key = self._normalize_version_key()
            version_info = QQ_VERSIONS.get(bot.qq_version_key, {})
            self._sync_qr_code(bot)
            memory = self._memory_snapshot(bot)
            running = bool(bot.process and bot.process.returncode is None)
            connected = bool(bot.uin and (bot.uin in self.app.adapter.local_actions or self.app.adapter.get_bot_ws(bot.uin) is not None))
            if connected and bot.status != 'online':
                bot.status = 'online'
            enabled = bool(bot.enabled or running or bot.status in ('logging_in', 'waiting_qr', 'authorizing', 'online'))
            result.append(
                {
                    'bot_qq': bot.uin or bot.bot_id,
                    'name': bot.nickname or bot.uin or bot.bot_id,
                    'qq': bot.uin or bot.bot_id,
                    'bot_id': bot.bot_id,
                    'bridge_port': bot.bridge_port,
                    'connected': connected,
                    'status': bot.status,
                    'enabled': enabled,
                    'qrcode': bot.qr_code,
                    'qrcode_url': bot.qr_url,
                    'error': public_text(bot.error),
                    'pid': bot.process.pid if running and bot.process is not None else None,
                    'runtime_mode': bot.launch_mode,
                    'qq_version_key': bot.qq_version_key,
                    'qq_version': version_info.get('version', ''),
                    'qq_version_label': version_info.get('label', ''),
                    'force_quick_login': bot.force_quick_login,
                    'qq_installed': bool(self._find_qq_path(bot)),
                    'connection_type': 'Embedded QQ',
                    'avatar': f'https://q1.qlogo.cn/g?b=qq&nk={bot.uin}&s=100' if bot.uin else '',
                    **memory,
                }
            )
        return result
