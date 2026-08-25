"""系统信息采集 + 重启"""

import asyncio
import contextlib
import gc
import importlib.metadata
import logging
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any

import psutil
from aiohttp import web

from web.tools import _common

log = logging.getLogger('ElainaQQ.web.sysinfo')

_IS_WINDOWS = platform.system() == 'Windows'
_start_time = datetime.now()
_last_gc = 0.0
_GC_INTERVAL = 30
_info_cache: tuple[float, dict[str, Any] | None] = (0.0, None)
_INFO_CACHE_TTL = 5
_app = None
_cpu_model_cache = None
_io_sample_lock = threading.Lock()
_io_sample: tuple[float, dict[str, int], dict[str, int]] | None = None


def set_context(app_instance, start_time=None):
    global _app, _start_time
    _app = app_instance
    _common.set_app(app_instance)
    if start_time:
        _start_time = start_time


def _cpu_model():
    global _cpu_model_cache
    if _cpu_model_cache:
        return _cpu_model_cache
    model = ''
    try:
        if _IS_WINDOWS:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'HARDWARE\DESCRIPTION\System\CentralProcessor\0',
            )
            model = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
            winreg.CloseKey(key)
        else:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if line.startswith('model name'):
                        model = line.split(':', 1)[1].strip()
                        break
    except Exception:
        pass
    if not model:
        with contextlib.suppress(Exception):
            model = platform.processor() or ''
    if not model:
        model = f'{psutil.cpu_count(logical=True)} 核处理器'
    _cpu_model_cache = model
    return model


def _get_hw_info() -> dict:
    """CPU/内存/磁盘等硬件信息 (同步, 可在 executor 运行)"""
    global _last_gc
    proc = psutil.Process(os.getpid())
    now = time.time()
    if now - _last_gc >= _GC_INTERVAL:
        gc.collect(0)
        _last_gc = now

    mem = proc.memory_info()
    sys_mem = psutil.virtual_memory()
    rss_mb = mem.rss / (1024**2)
    mem_total_mb = sys_mem.total / (1024**2)

    try:
        cpu_cores = psutil.cpu_count(logical=True)
        cpu_pct = max(proc.cpu_percent(interval=0.05), 1.0)
        sys_cpu = max(psutil.cpu_percent(interval=0.05), 5.0)
    except Exception:
        cpu_cores, cpu_pct, sys_cpu = 1, 1.0, 5.0

    uptime = int((datetime.now() - _start_time).total_seconds())
    try:
        boot = datetime.fromtimestamp(psutil.boot_time())
        sys_uptime = int((datetime.now() - boot).total_seconds())
    except Exception:
        sys_uptime = uptime

    disk = psutil.disk_usage(os.path.abspath(os.getcwd()))
    io_info = _get_io_info()
    request_info = _get_request_info()

    plugins_count = bots_count = 0
    if _app:
        pm = getattr(_app, 'plugin_manager', None)
        if pm:
            plugins_count = getattr(pm, 'handler_count', 0)
        bots_count = len(_common.connected_ids())

    return {
        'cpu_percent': round(sys_cpu, 1),
        'framework_cpu_percent': round(cpu_pct, 1),
        'cpu_cores': cpu_cores,
        'cpu_model': _cpu_model(),
        'memory_percent': round(sys_mem.percent, 1),
        'memory_used': round(sys_mem.used / (1024**2), 1),
        'memory_total': round(mem_total_mb, 1),
        'framework_memory_percent': round((rss_mb / mem_total_mb) * 100 if mem_total_mb else 0, 1),
        'framework_memory_total': round(rss_mb, 1),
        'disk_info': {'total': disk.total, 'used': disk.used, 'free': disk.free, 'percent': disk.percent},
        'uptime': uptime,
        'system_uptime': sys_uptime,
        'start_time': _start_time.strftime('%Y-%m-%d %H:%M:%S'),
        'system_version': platform.platform(),
        'plugins_count': plugins_count,
        'bots_count': bots_count,
        'network_io': io_info['network'],
        'disk_io': io_info['disk'],
        'requests': request_info,
    }


def _sum_network(counters):
    values = list((counters or {}).values())
    return {
        'sent': sum(int(getattr(item, 'bytes_sent', 0) or 0) for item in values),
        'recv': sum(int(getattr(item, 'bytes_recv', 0) or 0) for item in values),
        'packets_sent': sum(int(getattr(item, 'packets_sent', 0) or 0) for item in values),
        'packets_recv': sum(int(getattr(item, 'packets_recv', 0) or 0) for item in values),
    }


def _sum_disk(counters):
    values = list((counters or {}).values())
    return {
        'read': sum(int(getattr(item, 'read_bytes', 0) or 0) for item in values),
        'write': sum(int(getattr(item, 'write_bytes', 0) or 0) for item in values),
        'read_count': sum(int(getattr(item, 'read_count', 0) or 0) for item in values),
        'write_count': sum(int(getattr(item, 'write_count', 0) or 0) for item in values),
        'read_time': sum(int(getattr(item, 'read_time', 0) or 0) for item in values),
        'write_time': sum(int(getattr(item, 'write_time', 0) or 0) for item in values),
    }


def _rate(current, previous, elapsed):
    return max(0, current - previous) / max(elapsed, 0.1)


def _get_io_info() -> dict:
    global _io_sample
    now = time.monotonic()
    network = _sum_network(psutil.net_io_counters(pernic=True))
    disk = _sum_disk(psutil.disk_io_counters(perdisk=True))
    with _io_sample_lock:
        previous = _io_sample
        _io_sample = (now, network, disk)
    elapsed = now - previous[0] if previous else 0
    if not previous or elapsed <= 0:
        elapsed = 1
        old_network = network
        old_disk = disk
    else:
        old_network, old_disk = previous[1], previous[2]
    return {
        'network': {
            'tx_rate': round(_rate(network['sent'], old_network['sent'], elapsed), 1),
            'rx_rate': round(_rate(network['recv'], old_network['recv'], elapsed), 1),
            'total_tx': network['sent'],
            'total_rx': network['recv'],
            'packets_tx_rate': round(_rate(network['packets_sent'], old_network['packets_sent'], elapsed), 1),
            'packets_rx_rate': round(_rate(network['packets_recv'], old_network['packets_recv'], elapsed), 1),
        },
        'disk': {
            'read_rate': round(_rate(disk['read'], old_disk['read'], elapsed), 1),
            'write_rate': round(_rate(disk['write'], old_disk['write'], elapsed), 1),
            'read_iops': round(_rate(disk['read_count'], old_disk['read_count'], elapsed), 1),
            'write_iops': round(_rate(disk['write_count'], old_disk['write_count'], elapsed), 1),
            'total_read': disk['read'],
            'total_write': disk['write'],
            'read_latency_ms': round(_rate(disk['read_time'], old_disk['read_time'], elapsed), 1),
            'write_latency_ms': round(_rate(disk['write_time'], old_disk['write_time'], elapsed), 1),
        },
    }


def _get_request_info() -> dict:
    server = getattr(_app, '_http_server', None) if _app else None
    metrics = server.request_metrics() if server and hasattr(server, 'request_metrics') else {'total': 0, 'active': 0, 'rate': 0}
    return {
        'total': int(metrics.get('total', 0)),
        'active': int(metrics.get('active', 0)),
        'rate': round(float(metrics.get('rate', 0)), 2),
    }


def _dependency_info() -> dict:
    packages = [('aiohttp', 'aiohttp'), ('psutil', 'psutil'), ('PyYAML', 'PyYAML'), ('qrcode', 'qrcode')]
    dependencies = []
    for label, package in packages:
        try:
            version = importlib.metadata.version(package)
            dependencies.append({'name': label, 'installed': version, 'required': '已安装', 'status': 'ok'})
        except importlib.metadata.PackageNotFoundError:
            dependencies.append({'name': label, 'installed': '', 'required': '已安装', 'status': 'missing'})
    return {
        'python': {
            'version': platform.python_version(),
            'required': '>= 3.10',
            'status': 'ok' if sys.version_info >= (3, 10) else 'low',
        },
        'dependencies': dependencies,
    }


async def get_system_info() -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_hw_info)


async def handle_system_info(request: web.Request):
    global _info_cache
    try:
        now = time.time()
        ts, data = _info_cache
        if data and now - ts < _INFO_CACHE_TTL:
            return web.json_response(data)
        data = await get_system_info()
        _info_cache = (now, data)
        return web.json_response(data)
    except Exception as e:
        log.error(f'获取系统信息失败: {e}')
        return web.json_response({'error': str(e)}, status=500)


async def handle_dependencies(request: web.Request):
    try:
        return web.json_response(_dependency_info())
    except Exception as exc:
        return web.json_response({'error': str(exc)}, status=500)


# ──────────────── 重启 ────────────────

_UNIX_TEMPLATE = """import os, sys, time
def main():
    main_path = r"{main_py}"
    time.sleep(1)
    os.chdir(os.path.dirname(main_path))
    try: os.remove(__file__)
    except: pass
    os.execv(sys.executable, [sys.executable, main_path])
if __name__ == "__main__":
    main()
"""

_WIN_TEMPLATE = """import os, sys, time, subprocess
def main():
    time.sleep(3)
    main_path = r"{main_py}"
    os.chdir(os.path.dirname(main_path))
    subprocess.Popen([sys.executable, main_path], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    time.sleep(1)
    try: os.remove(__file__)
    except: pass
    sys.exit(0)
if __name__ == "__main__":
    main()
"""


def _start_restarter(base: str, restarter: str, script: str) -> None:
    os.makedirs(os.path.dirname(restarter), exist_ok=True)
    with open(restarter, 'w', encoding='utf-8') as file:
        file.write(script)
    if _IS_WINDOWS:
        subprocess.Popen(
            [sys.executable, restarter],
            cwd=base,
            creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0),
        )
    else:
        subprocess.Popen([sys.executable, restarter], cwd=base, start_new_session=True)


async def handle_restart(request: web.Request):
    if _app and _app.request_restart():
        return web.json_response({'success': True, 'message': '正在重启...'})

    base = _common.base_dir()
    main_py = os.path.join(base, 'main.py')
    if not os.path.exists(main_py):
        return web.json_response({'success': False, 'error': 'main.py 不存在'})

    restarter = os.path.join(base, 'data', 'bot_restarter.py')
    try:
        script = (_WIN_TEMPLATE if _IS_WINDOWS else _UNIX_TEMPLATE).format(main_py=main_py)
        await asyncio.to_thread(_start_restarter, base, restarter, script)
        if _IS_WINDOWS:
            threading.Thread(target=_exit_after_restart, daemon=True).start()
        return web.json_response({'success': True, 'message': '正在重启...'})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})


def _exit_after_restart() -> None:
    """等待重启器接管后退出当前 Windows 进程。"""
    time.sleep(1)
    os._exit(0)
