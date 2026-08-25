"""内置 QQ 子进程树终止、内存采样与 Linux 页面回收。"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, cast

import psutil

_MIB = 1024 * 1024
_EMPTY_MEMORY = {
    'memory_mb': 0.0,
    'memory_rss_mb': 0.0,
    'memory_pss_mb': 0.0,
    'memory_uss_mb': 0.0,
    'memory_swap_mb': 0.0,
    'memory_processes': 0,
}


def process_tree_pids(root_pid: int, data_dir: Path) -> set[int]:
    """收集根进程、子进程及使用指定账号目录的同组 QQ 进程。"""
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


def kill_pids(pids: set[int]) -> None:
    processes = []
    for pid in pids:
        with contextlib.suppress(psutil.Error, OSError):
            processes.append(psutil.Process(pid))
    for item in sorted(processes, key=lambda value: value.pid, reverse=True):
        with contextlib.suppress(psutil.Error, OSError):
            item.kill()
    with contextlib.suppress(psutil.Error, OSError):
        psutil.wait_procs(processes, timeout=5)


async def terminate_process_tree(
    process: asyncio.subprocess.Process,
    data_dir: Path,
    captured_pids: set[int],
) -> None:
    """按平台终止进程组，并补充清理尚未退出的关联进程。"""
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
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                kill_process_group(process.pid, cast(Any, signal).SIGKILL)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), 5)

    remaining = captured_pids | process_tree_pids(process.pid, data_dir)
    await asyncio.to_thread(kill_pids, remaining)
    if process.returncode is None:
        with contextlib.suppress(Exception):
            process.kill()
        with contextlib.suppress(Exception):
            await process.wait()


def reclaim_process_pages(root_pid: int, include_anonymous: bool = False) -> dict[str, int]:
    """使用 Linux process_madvise 回收进程树中的闲置页面。"""
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


def process_memory_usage(root_pid: int) -> dict[str, int]:
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


class ProcessMemoryMonitor:
    """为频繁状态查询提供短期缓存，避免重复遍历整个进程树。"""

    def __init__(self, ttl: float = 2.0):
        self._ttl = max(0.0, ttl)
        self._cache: dict[str, tuple[float, int, dict[str, Any]]] = {}

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def snapshot(self, key: str, process: asyncio.subprocess.Process | None) -> dict[str, Any]:
        if not process or process.returncode is not None:
            self.invalidate(key)
            return _EMPTY_MEMORY.copy()
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached[1] == process.pid and now - cached[0] < self._ttl:
            return cached[2].copy()
        try:
            root = psutil.Process(process.pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return _EMPTY_MEMORY.copy()

        seen: set[int] = set()
        rss = pss = uss = swap = count = 0
        for item in processes:
            try:
                if item.pid in seen or not item.is_running():
                    continue
                seen.add(item.pid)
                rss += int(getattr(item.memory_info(), 'rss', 0) or 0)
                with contextlib.suppress(psutil.Error, OSError):
                    full_info = item.memory_full_info()
                    pss += int(getattr(full_info, 'pss', 0) or 0)
                    uss += int(getattr(full_info, 'uss', 0) or 0)
                    swap += int(getattr(full_info, 'swap', 0) or 0)
                count += 1
            except (psutil.Error, OSError):
                continue
        result = {
            'memory_mb': round(rss / _MIB, 1),
            'memory_rss_mb': round(rss / _MIB, 1),
            'memory_pss_mb': round(pss / _MIB, 1),
            'memory_uss_mb': round(uss / _MIB, 1),
            'memory_swap_mb': round(swap / _MIB, 1),
            'memory_processes': count,
        }
        self._cache[key] = (now, process.pid, result)
        return result.copy()
