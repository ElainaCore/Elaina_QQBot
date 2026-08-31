"""QQ process discovery and explicitly requested native runtime operations."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import psutil
from aiohttp import web

from core.runtime.embedded.injector import NativeInjectionError, NativeInjectorUnavailable
from web.protocol import error, ok

_app = None
_QQ_PROCESS_NAMES = frozenset({'qq', 'qq.exe', 'linuxqq'})
_QQ_PIPE_PATTERN = re.compile(r'^mojo\.(\d+)\.control$', re.IGNORECASE)


def set_context(app_instance) -> None:
    global _app
    _app = app_instance


def _runtime_status(bot: dict[str, Any]) -> str:
    status = str(bot.get('status') or '')
    if status == 'online':
        return 'online'
    if status in {'logging_in', 'authorizing', 'waiting_qr'}:
        return 'connecting'
    if status == 'error':
        return 'error'
    if bot.get('pid'):
        return 'loaded'
    return 'available'


def _managed_records(manager) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    by_pid: dict[int, dict[str, Any]] = {}
    if manager is None:
        return records, by_pid
    for bot in manager.list_bots():
        pid = int(bot.get('pid') or 0) or None
        record = {
            'id': f"managed:{bot['bot_id']}",
            'pid': pid,
            'name': bot.get('name') or bot.get('qq') or bot['bot_id'],
            'process_name': 'QQ.exe' if os.name == 'nt' else 'qq',
            'path': bot.get('qq_path') or '',
            'managed': True,
            'injected': bool(pid),
            'can_load': not bool(pid),
            'can_unload': bool(pid),
            'can_attach': False,
            'attach_mode': 'managed',
            'bot_id': bot['bot_id'],
            'uin': bot.get('qq') or '',
            'status': _runtime_status(bot),
            'error': bot.get('error') or '',
            'bridge_port': bot.get('bridge_port'),
            'qq_version': bot.get('qq_version') or '',
            'qq_version_key': bot.get('qq_version_key') or '',
            'qrcode': bot.get('qrcode') or '',
            'qrcode_url': bot.get('qrcode_url') or '',
            'memory_rss_mb': bot.get('memory_rss_mb') or 0,
            'memory_processes': bot.get('memory_processes') or 0,
        }
        records.append(record)
        if pid:
            by_pid[pid] = record
    return records, by_pid


def _is_main_qq_process(process: psutil.Process) -> bool:
    """Identify a top-level QQ process using only public process metadata."""
    try:
        if process.name().lower() not in _QQ_PROCESS_NAMES:
            return False
    except (psutil.Error, OSError):
        return False
    try:
        parent = process.parent()
        return parent is None or parent.name().lower() not in _QQ_PROCESS_NAMES
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        # The process itself is visible and named QQ; an inaccessible or exited
        # parent must not hide it from the user.
        return True


def _loaded_pipe_pids() -> frozenset[int]:
    """Read SnowLuma-compatible pipe names without loading the Node addon."""
    if os.name != 'nt':
        return frozenset()
    try:
        names = os.listdir('\\\\.\\pipe\\')
    except OSError:
        return frozenset()
    return frozenset(int(match.group(1)) for name in names if (match := _QQ_PIPE_PATTERN.fullmatch(name)))


def _external_qq_processes(managed_by_pid: dict[int, dict[str, Any]], injector) -> list[dict[str, Any]]:
    """Discover QQ with psutil; this function never starts the native helper."""
    external: list[dict[str, Any]] = []
    owned_pids = injector.owned_pids if injector is not None else frozenset()
    loaded_pids = _loaded_pipe_pids() | owned_pids
    availability_error = injector.availability_error() if injector is not None else '进程注入器未初始化'
    for process in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            name = str(process.info.get('name') or '')
            if name.lower() not in _QQ_PROCESS_NAMES or not _is_main_qq_process(process):
                continue
            pid = int(process.info['pid'])
            if pid in managed_by_pid:
                managed_by_pid[pid]['path'] = str(process.info.get('exe') or '')
                continue
            injected = pid in loaded_pids
            owned = pid in owned_pids
            hook = getattr(_app, 'hook_bridge', None)
            bridge = hook(pid) if callable(hook) else None
            hooked = bool(bridge and bridge.status.control_open)
            process_error = ''
            if injected and not owned and not hooked:
                process_error = '运行时已加载，尚未接管；点击注入即可认领并接管'
            external.append(
                {
                    'id': f'external:{pid}',
                    'pid': pid,
                    'name': name,
                    'process_name': name,
                    'path': str(process.info.get('exe') or ''),
                    'managed': False,
                    'injected': injected,
                    'can_load': not availability_error,
                    'can_unload': owned,
                    'can_attach': injected and not hooked,
                    'attach_mode': 'native',
                    'bot_id': '',
                    'uin': bridge.status.uin if bridge else '',
                    'status': 'online' if hooked else ('loaded' if injected else 'detected'),
                    'error': process_error,
                    'bridge_port': None,
                    'qq_version': '',
                    'qq_version_key': '',
                    'qrcode': '',
                    'qrcode_url': '',
                    'memory_rss_mb': round(process.memory_info().rss / 1024 / 1024, 1),
                    'memory_processes': 1,
                }
            )
        except (psutil.Error, OSError, TypeError, ValueError):
            continue
    return external


async def handle_get_processes(request: web.Request) -> web.Response:
    manager = getattr(_app, 'embedded_qq', None)
    injector = getattr(_app, 'process_injector', None)
    managed, managed_by_pid = _managed_records(manager)
    external = _external_qq_processes(managed_by_pid, injector)
    records = [*managed, *external]
    records.sort(key=lambda item: (item.get('pid') is None, item.get('pid') or 0, item['name']))
    return ok(
        processes=records,
        detected_count=len(records),
        managed_count=len(managed),
        loadable_count=sum(1 for item in records if item['can_load']),
        online_count=sum(1 for item in records if item['status'] == 'online'),
        discovery='python-psutil+named-pipes',
        injector_started=bool(injector and injector.started),
    )


def _requested_external_qq(pid_text: str) -> tuple[int, psutil.Process, Path]:
    try:
        pid = int(pid_text)
        if pid <= 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError('PID 无效') from exc
    try:
        process = psutil.Process(pid)
        name = process.name().lower()
        executable = Path(process.exe()).resolve()
    except (psutil.Error, OSError) as exc:
        raise ValueError('QQ 进程不存在或无法访问') from exc
    if name not in _QQ_PROCESS_NAMES or executable.name.lower() not in _QQ_PROCESS_NAMES or not _is_main_qq_process(process):
        raise ValueError('目标不是受支持的 QQ 主进程')
    return pid, process, executable


def _injection_error_response(exc: Exception) -> web.Response:
    if isinstance(exc, NativeInjectorUnavailable):
        return error(str(exc), status=503, code=exc.code)
    if isinstance(exc, NativeInjectionError):
        status = 409 if exc.code in {'TARGET_NOT_QQ', 'HANDLE_NOT_OWNED'} else 502
        return error(str(exc), status=status, code=exc.code)
    if isinstance(exc, ValueError):
        return error(str(exc), status=400)
    return error(str(exc), status=500)


async def handle_load_process(request: web.Request) -> web.Response:
    """Load the native module only after an explicit authenticated request."""
    try:
        pid, _, executable = _requested_external_qq(request.match_info.get('pid', ''))
        injector = getattr(_app, 'process_injector', None)
        if injector is None:
            raise NativeInjectorUnavailable('进程注入器未初始化', 'UNAVAILABLE')
        result = await injector.load(pid)
        return ok(message='运行时已注入 QQ', pid=pid, executable=str(executable), result=result)
    except Exception as exc:
        return _injection_error_response(exc)


async def handle_unload_process(request: web.Request) -> web.Response:
    try:
        pid, _, executable = _requested_external_qq(request.match_info.get('pid', ''))
        injector = getattr(_app, 'process_injector', None)
        if injector is None:
            raise NativeInjectorUnavailable('进程注入器未初始化', 'UNAVAILABLE')
        result = await injector.unload(pid)
        return ok(message='运行时已从 QQ 卸载', pid=pid, executable=str(executable), result=result)
    except Exception as exc:
        return _injection_error_response(exc)


async def handle_refresh_process(request: web.Request) -> web.Response:
    try:
        pid, _, executable = _requested_external_qq(request.match_info.get('pid', ''))
        injector = getattr(_app, 'process_injector', None)
        if injector is None:
            raise NativeInjectorUnavailable('进程注入器未初始化', 'UNAVAILABLE')
        result = await injector.refresh(pid)
        return ok(message='QQ 运行时已重新加载', pid=pid, executable=str(executable), result=result)
    except Exception as exc:
        return _injection_error_response(exc)


async def handle_attach_process(request: web.Request) -> web.Response:
    """注入 + 接管：确保 DLL 已加载，然后连接接管桥开始事件转发。"""
    try:
        pid, _, executable = _requested_external_qq(request.match_info.get('pid', ''))
        injector = getattr(_app, 'process_injector', None)
        if injector is None:
            raise NativeInjectorUnavailable('进程注入器未初始化', 'UNAVAILABLE')
        result = await injector.load(pid)
        attach = await _app.attach_hook_bridge(pid)
        if not attach.get('attached'):
            return error(attach.get('error') or '接管失败', status=502, pid=pid,
                         executable=str(executable), result=result)
        return ok(message='QQ 已接管', pid=pid, executable=str(executable),
                  result={**result, 'hook': attach})
    except Exception as exc:
        return _injection_error_response(exc)


async def handle_detach_process(request: web.Request) -> web.Response:
    """断开接管桥（DLL 保留在 QQ 内，事件不再转发）。"""
    try:
        pid, _, executable = _requested_external_qq(request.match_info.get('pid', ''))
        result = await _app.detach_hook_bridge(pid)
        if result.get('error'):
            return error(result['error'], status=404, pid=pid)
        return ok(message='接管桥已断开', pid=pid, executable=str(executable), result=result)
    except Exception as exc:
        return _injection_error_response(exc)


async def handle_hook_status(request: web.Request) -> web.Response:
    try:
        return ok(bridges=getattr(_app, 'hook_bridges', lambda: [])())
    except Exception as exc:
        return _injection_error_response(exc)
