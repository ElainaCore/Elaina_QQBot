"""SnowLuma 兼容的 QQ 进程注入生命周期（纯 Python ctypes 实现）。

Python 直接调用 Win32 API，把 ``core/native/qq-win32-x64.dll`` 加载进已运行的
QQ 主进程。DLL 在 QQ 进程内部复用其自带的 Electron/Node 环境并启动 Elaina
桥接。框架因此不再携带或解压 node.exe，也不派生任何辅助 Node 进程。

对外接口保持 ``load(pid)`` / ``unload(pid)`` / ``refresh(pid)`` / ``close()``，
调用方（``web/tools/processes.py`` 与前端）无需感知实现切换。
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import os
import platform
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import psutil

_QQ_PROCESS_NAMES = frozenset({'qq', 'qq.exe', 'linuxqq'})
_DLL_MODULE_NAME = 'qq-win32-x64.dll'
_QQ_PIPE_PATTERN = re.compile(r'^mojo\.(\d+)\.control$', re.IGNORECASE)
_LOAD_THREAD_TIMEOUT_MS = 20_000
_UNLOAD_THREAD_TIMEOUT_MS = 10_000
_INVALID_HANDLE = ctypes.c_void_p(-1).value

if os.name == 'nt':
    import ctypes.wintypes as wt

    _MEM_COMMIT = 0x00001000
    _MEM_RESERVE = 0x00002000
    _MEM_RELEASE = 0x00008000
    _PAGE_READWRITE = 0x04
    _PROCESS_CREATE_THREAD = 0x0002
    _PROCESS_VM_OPERATION = 0x0008
    _PROCESS_VM_WRITE = 0x0020
    _PROCESS_QUERY_INFORMATION = 0x0400
    # 仅申请对应操作所需的最小权限集合。
    _OPEN_RIGHTS_LOAD = (
        _PROCESS_CREATE_THREAD | _PROCESS_VM_OPERATION | _PROCESS_VM_WRITE | _PROCESS_QUERY_INFORMATION
    )
    _OPEN_RIGHTS_UNLOAD = _PROCESS_CREATE_THREAD | _PROCESS_VM_OPERATION | _PROCESS_QUERY_INFORMATION
    _TH32CS_SNAP_MODULE = 0x00000008
    _TH32CS_SNAPMODULE32 = 0x00000010
    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_TIMEOUT = 0x00000102
    _ERROR_ACCESS_DENIED = 5

    class _ModuleEntry32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', ctypes.wintypes.DWORD),
            ('th32ModuleID', ctypes.wintypes.DWORD),
            ('th32ProcessID', ctypes.wintypes.DWORD),
            ('GlblcntUsage', ctypes.wintypes.DWORD),
            ('ProccntUsage', ctypes.wintypes.DWORD),
            ('modBaseAddr', ctypes.POINTER(ctypes.c_byte)),
            ('modBaseSize', ctypes.wintypes.DWORD),
            ('hModule', ctypes.wintypes.HMODULE),
            ('szModule', ctypes.wintypes.WCHAR * 256),
            ('szExePath', ctypes.wintypes.WCHAR * 260),
        ]

    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.VirtualAllocEx.restype = wt.LPVOID
    _k32.VirtualAllocEx.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD, wt.DWORD]
    _k32.VirtualFreeEx.restype = wt.BOOL
    _k32.VirtualFreeEx.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD]
    _k32.WriteProcessMemory.restype = wt.BOOL
    _k32.WriteProcessMemory.argtypes = [
        wt.HANDLE,
        wt.LPVOID,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    _k32.CreateRemoteThread.restype = wt.HANDLE
    _k32.CreateRemoteThread.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.LPVOID, wt.LPVOID, wt.DWORD, wt.LPVOID]
    _k32.WaitForSingleObject.restype = wt.DWORD
    _k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    _k32.GetExitCodeThread.restype = wt.BOOL
    _k32.GetExitCodeThread.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    _k32.GetModuleHandleW.restype = wt.HMODULE
    _k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    _k32.GetProcAddress.restype = wt.LPVOID
    _k32.GetProcAddress.argtypes = [wt.HMODULE, wt.LPCSTR]
    _k32.IsWow64Process.restype = wt.BOOL
    _k32.IsWow64Process.argtypes = [wt.HANDLE, ctypes.POINTER(wt.BOOL)]
    _k32.CloseHandle.restype = wt.BOOL
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _k32.Module32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_ModuleEntry32W)]
    _k32.Module32NextW.restype = wt.BOOL
    _k32.Module32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_ModuleEntry32W)]
else:  # pragma: no cover - 非 Windows 平台仅保留类型占位
    _k32 = None


def _win32_error() -> int:
    return ctypes.get_last_error() if _k32 is not None else 0


class NativeInjectionError(RuntimeError):
    """A native injector operation failed."""

    def __init__(self, message: str, code: str = '') -> None:
        super().__init__(message)
        self.code = code


class NativeInjectorUnavailable(NativeInjectionError):  # noqa: N818 - 保留旧名称以兼容调用方
    """The current host cannot run the injector."""


class NativeQQInjector:
    """用 Python ctypes 把注入 DLL 加载进 QQ，并持有本框架的卸载记录。"""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.native_dir = self.base_dir / 'core' / 'native'
        self.dll_path = self.native_dir / _DLL_MODULE_NAME
        self._owned_pids: set[int] = set()
        self._before_unload: list[Callable[[int], Awaitable[None] | None]] = []

    # ------------------------------------------------------------------
    # 状态与注册
    # ------------------------------------------------------------------

    def availability_error(self) -> str:
        if os.name != 'nt' or platform.machine().lower() not in {'amd64', 'x86_64'}:
            return '进程注入当前仅支持 Windows x64'
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            return 'Python 必须是 64 位版本才能注入 64 位 QQ'
        if not self.dll_path.is_file():
            return f'QQ 注入模块不存在: {self.dll_path}'
        return ''

    @property
    def available(self) -> bool:
        return not self.availability_error()

    @property
    def started(self) -> bool:
        """兼容字段：注入层无独立进程，等价于“当前主机可注入”。"""
        return self.available

    @property
    def owned_pids(self) -> frozenset[int]:
        """本框架本次成功加载、仍存活的 QQ PID 集合。"""
        for pid in list(self._owned_pids):
            if not psutil.pid_exists(pid):
                self._owned_pids.discard(pid)
        return frozenset(self._owned_pids)

    def register_before_unload(self, callback: Callable[[int], Awaitable[None] | None]) -> Callable[[], None]:
        """注册卸载前回调（例如关闭该 PID 的 OneBot/桥接会话），返回注销函数。"""
        self._before_unload.append(callback)

        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._before_unload.remove(callback)

        return _remove

    # ------------------------------------------------------------------
    # 对外异步接口
    # ------------------------------------------------------------------

    async def load(self, pid: int) -> dict[str, Any]:
        self._require_available()
        pid = self._normalize_pid(pid)
        result = await asyncio.to_thread(self._load_sync, pid)
        if result.get('owned'):
            self._owned_pids.add(pid)
        return result

    async def unload(self, pid: int) -> dict[str, Any]:
        self._require_available()
        pid = self._normalize_pid(pid)
        await self._run_before_unload(pid)
        return await asyncio.to_thread(self._unload_sync, pid)
    async def refresh(self, pid: int) -> dict[str, Any]:
        self._require_available()
        pid = self._normalize_pid(pid)
        if pid in self.owned_pids:
            await self.unload(pid)
        elif pid in self._pipe_pids():
            raise NativeInjectionError('运行时已加载，但当前框架不持有它的卸载句柄', 'HANDLE_NOT_OWNED')
        return await self.load(pid)

    async def close(self) -> None:
        """框架关闭时回收本框架加载的所有运行时。"""
        for pid in list(self._owned_pids):
            with contextlib.suppress(Exception):
                await self.unload(pid)
        self._owned_pids.clear()

    # ------------------------------------------------------------------
    # 同步实现（全部在线程中执行，绝不阻塞事件循环）
    # ------------------------------------------------------------------

    def _load_sync(self, pid: int) -> dict[str, Any]:
        self._verify_target_sync(pid)
        pipes = self._pipe_pids()
        owned = pid in self._owned_pids
        if owned or pid in pipes:
            # 管道存在说明 DLL 已经在 QQ 内：不重复 LoadLibrary，避免引用计数叠加。
            # 认领（adopt）所有权：无论 DLL 由谁加载，本框架从此接管其生命周期。
            self._owned_pids.add(pid)
            return {'pid': pid, 'loaded': True, 'owned': True, 'alreadyLoaded': True, 'adopted': not owned}

        handle = _k32.OpenProcess(_OPEN_RIGHTS_LOAD, False, pid)
        if not handle:
            self._raise_open_error(pid)
        try:
            self._ensure_target_x64(handle)
            if self._find_remote_module(pid) is not None:
                # 模块已在（例如由旧框架实例加载）：不持有句柄，不重复加载。
                return {'pid': pid, 'loaded': True, 'owned': False, 'alreadyLoaded': True}

            remote_path = self._write_dll_path(handle)
            try:
                self._call_load_library(handle, pid, remote_path)
            finally:
                _k32.VirtualFreeEx(handle, remote_path, 0, _MEM_RELEASE)
        finally:
            _k32.CloseHandle(handle)
        return {'pid': pid, 'loaded': True, 'owned': True, 'alreadyLoaded': False, 'method': 'remote-loadlibraryw'}

    def _unload_sync(self, pid: int) -> dict[str, Any]:
        if pid not in self._owned_pids:
            if pid in self._pipe_pids():
                raise NativeInjectionError('运行时已加载，但当前框架不持有它的卸载句柄', 'HANDLE_NOT_OWNED')
            return {'pid': pid, 'loaded': False, 'owned': False, 'alreadyUnloaded': True}

        handle = _k32.OpenProcess(_OPEN_RIGHTS_UNLOAD, False, pid)
        if not handle:
            self._raise_open_error(pid)
        try:
            module = self._find_remote_module(pid)
            if module is None:
                self._owned_pids.discard(pid)
                return {'pid': pid, 'loaded': False, 'owned': False, 'alreadyUnloaded': True}
            self._call_free_library(handle, pid, module)
        finally:
            _k32.CloseHandle(handle)

        if self._find_remote_module(pid) is not None:
            raise NativeInjectionError('FreeLibrary 调用后 DLL 仍在 QQ 进程中', 'UNLOAD_FAILED')
        self._owned_pids.discard(pid)
        return {'pid': pid, 'loaded': False, 'owned': False, 'alreadyUnloaded': False}

    # ------------------------------------------------------------------
    # 目标验证
    # ------------------------------------------------------------------

    def _verify_target_sync(self, pid: int) -> str:
        """独立验证目标 PID：进程名、主进程身份、可执行文件与权限。"""
        try:
            process = psutil.Process(pid)
            name = process.name()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            raise NativeInjectionError('QQ 进程不存在', 'TARGET_NOT_QQ') from None
        except psutil.AccessDenied as exc:
            raise self._elevation_error() from exc
        if name.lower() not in _QQ_PROCESS_NAMES:
            raise NativeInjectionError('目标不是 QQ 进程', 'TARGET_NOT_QQ')
        if not self._is_main_qq_process(process):
            raise NativeInjectionError('目标不是 QQ 主进程（可能是 QQ 的子进程）', 'TARGET_NOT_QQ')
        try:
            exe = process.exe()
        except psutil.AccessDenied as exc:
            raise self._elevation_error() from exc
        except (psutil.Error, OSError) as exc:
            raise NativeInjectionError('无法读取 QQ 进程路径', 'TARGET_NOT_QQ') from exc
        if not exe or not Path(exe).is_file():
            raise NativeInjectionError('QQ 可执行文件不存在或无法访问', 'TARGET_NOT_QQ')
        return exe

    @staticmethod
    def _is_main_qq_process(process: psutil.Process) -> bool:
        """QQNT 的渲染/子进程父进程也是 QQ.exe；主进程的父进程不是。"""
        try:
            parent = process.parent()
            if parent is None:
                return True
            parent_name = parent.name()
        except (psutil.Error, OSError):
            # 父进程不可见不代表目标不是主进程，不能因此隐藏它。
            return True
        return parent_name.lower() not in _QQ_PROCESS_NAMES

    def _elevation_error(self) -> NativeInjectionError:
        if self._framework_is_admin():
            return NativeInjectionError('没有权限访问目标 QQ 进程', 'ACCESS_DENIED')
        return NativeInjectionError('QQ 以管理员权限运行，请以管理员身份重启框架后再操作', 'ELEVATION_REQUIRED')

    @staticmethod
    def _framework_is_admin() -> bool:
        if os.name != 'nt':
            return os.geteuid() == 0  # type: ignore[attr-defined]
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    @staticmethod
    def _ensure_target_x64(handle: int) -> None:
        wow64 = ctypes.wintypes.BOOL(False)
        if not _k32.IsWow64Process(handle, ctypes.byref(wow64)):
            raise NativeInjectionError(f'无法确认目标进程架构，Win32 错误码 {_win32_error()}', 'QUERY_FAILED')
        if wow64.value:
            raise NativeInjectionError('目标 QQ 进程是 32 位 (WOW64)，无法注入 64 位运行时', 'TARGET_NOT_X64')

    @staticmethod
    def _raise_open_error(pid: int) -> None:
        error = _win32_error()
        if error == _ERROR_ACCESS_DENIED and not NativeQQInjector._framework_is_admin():
            raise NativeInjectionError('QQ 以管理员权限运行，请以管理员身份重启框架后再操作', 'ELEVATION_REQUIRED')
        raise NativeInjectionError(f'无法打开 QQ 进程 (PID {pid})，Win32 错误码 {error}', 'OPEN_FAILED')

    # ------------------------------------------------------------------
    # Win32 注入细节
    # ------------------------------------------------------------------

    def _write_dll_path(self, handle: int) -> int:
        """在 QQ 进程内分配内存并写入 DLL 的绝对 Unicode 路径。"""
        payload = str(self.dll_path.resolve()) + '\x00'
        encoded = payload.encode('utf-16-le')
        size = len(encoded)
        remote = _k32.VirtualAllocEx(handle, None, size, _MEM_COMMIT | _MEM_RESERVE, _PAGE_READWRITE)
        if not remote:
            raise NativeInjectionError(f'无法在 QQ 进程内分配内存，Win32 错误码 {_win32_error()}', 'ALLOC_FAILED')
        written = ctypes.c_size_t(0)
        if not _k32.WriteProcessMemory(handle, remote, encoded, size, ctypes.byref(written)):
            with contextlib.suppress(Exception):
                _k32.VirtualFreeEx(handle, remote, 0, _MEM_RELEASE)
            raise NativeInjectionError(f'无法写入 DLL 路径到 QQ 进程，Win32 错误码 {_win32_error()}', 'WRITE_FAILED')
        return remote

    def _call_load_library(self, handle: int, pid: int, remote_path: int) -> None:
        """在 QQ 进程内调用 LoadLibraryW 并等待加载线程结束。"""
        kernel32 = _k32.GetModuleHandleW('kernel32.dll')
        if not kernel32:
            raise NativeInjectionError('无法获取 kernel32 模块句柄', 'LOAD_FAILED')
        proc = _k32.GetProcAddress(kernel32, b'LoadLibraryW')
        if not proc:
            raise NativeInjectionError('无法定位 LoadLibraryW', 'LOAD_FAILED')
        thread = _k32.CreateRemoteThread(handle, None, 0, proc, remote_path, 0, None)
        if not thread:
            raise NativeInjectionError(
                f'无法在 QQ 进程内创建加载线程，Win32 错误码 {_win32_error()}', 'LOAD_FAILED'
            )
        try:
            waited = _k32.WaitForSingleObject(thread, _LOAD_THREAD_TIMEOUT_MS)
            if waited == _WAIT_TIMEOUT:
                raise NativeInjectionError('DLL 加载线程超时，QQ 可能已无响应', 'LOAD_TIMEOUT')
            if waited != _WAIT_OBJECT_0:
                raise NativeInjectionError(f'等待加载线程失败，Win32 错误码 {_win32_error()}', 'LOAD_FAILED')
            exit_code = wt.DWORD(0)
            if not _k32.GetExitCodeThread(thread, ctypes.byref(exit_code)):
                raise NativeInjectionError(f'无法读取加载线程退出码，Win32 错误码 {_win32_error()}', 'LOAD_FAILED')
            if not exit_code.value:
                # x64 下 GetExitCodeThread 只能看到低 32 位：模块基址低 32 位
                # 恰好为 0 时会误报失败，用模块枚举复核后再下结论。
                if self._find_remote_module(pid) is not None:
                    return
                raise NativeInjectionError(
                    'LoadLibraryW 返回 NULL：QQ 进程内加载 DLL 失败（检查 DLL 依赖与位数）',
                    'LOAD_FAILED',
                )
        finally:
            _k32.CloseHandle(thread)

    def _call_free_library(self, handle: int, pid: int, module: int) -> None:
        """在 QQ 进程内对 DLL 基址调用 FreeLibraryAndExitThread。"""
        kernel32 = _k32.GetModuleHandleW('kernel32.dll')
        if not kernel32:
            raise NativeInjectionError('无法获取 kernel32 模块句柄', 'UNLOAD_FAILED')
        proc = _k32.GetProcAddress(kernel32, b'FreeLibraryAndExitThread')
        if not proc:
            raise NativeInjectionError('无法定位 FreeLibraryAndExitThread', 'UNLOAD_FAILED')
        thread = _k32.CreateRemoteThread(handle, None, 0, proc, module, 0, None)
        if not thread:
            raise NativeInjectionError(
                f'无法在 QQ 进程内创建卸载线程，Win32 错误码 {_win32_error()}', 'UNLOAD_FAILED'
            )
        try:
            waited = _k32.WaitForSingleObject(thread, _UNLOAD_THREAD_TIMEOUT_MS)
            if waited == _WAIT_TIMEOUT:
                raise NativeInjectionError('DLL 卸载线程超时', 'UNLOAD_FAILED')
            if waited != _WAIT_OBJECT_0:
                raise NativeInjectionError(f'等待卸载线程失败，Win32 错误码 {_win32_error()}', 'UNLOAD_FAILED')
        finally:
            _k32.CloseHandle(thread)

    def _find_remote_module(self, pid: int) -> int | None:
        """枚举 QQ 进程模块，返回 qq-win32-x64.dll 的 HMODULE（未加载则 None）。"""
        if _k32 is None:  # pragma: no cover
            return None
        snapshot = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAP_MODULE | _TH32CS_SNAPMODULE32, pid)
        if snapshot in (None, 0, _INVALID_HANDLE):
            # 模块快照可能因权限失败；此时无法定位模块，返回 None 由调用方决策。
            return None
        try:
            entry = _ModuleEntry32W()
            entry.dwSize = ctypes.sizeof(_ModuleEntry32W)
            if not _k32.Module32FirstW(snapshot, ctypes.byref(entry)):
                return None
            while True:
                if entry.szModule.lower() == _DLL_MODULE_NAME:
                    return int(entry.hModule) if entry.hModule else None
                if not _k32.Module32NextW(snapshot, ctypes.byref(entry)):
                    return None
        finally:
            _k32.CloseHandle(snapshot)

    # ------------------------------------------------------------------
    # 公共工具
    # ------------------------------------------------------------------

    def _pipe_pids(self) -> frozenset[int]:
        """读取 mojo.<pid>.control 命名管道，判断 DLL 是否已在 QQ 内运行。"""
        if os.name != 'nt':
            return frozenset()
        try:
            names = os.listdir('\\\\.\\pipe\\')
        except OSError:
            return frozenset()
        return frozenset(int(match.group(1)) for name in names if (match := _QQ_PIPE_PATTERN.fullmatch(name)))

    async def _run_before_unload(self, pid: int) -> None:
        """依次通知已注册的会话（如 OneBot 桥接）在卸载前自行关闭。"""
        for callback in list(self._before_unload):
            try:
                result = callback(pid)
                if result is not None:
                    await result
            except Exception:
                # 单个会话关闭失败不阻断卸载流程。
                continue

    def _normalize_pid(self, pid: Any) -> int:
        try:
            normalized = int(pid)
        except (TypeError, ValueError) as exc:
            raise NativeInjectionError('PID 无效', 'INVALID_PID') from exc
        if normalized <= 0 or normalized > 0xFFFFFFFF:
            raise NativeInjectionError('PID 无效', 'INVALID_PID')
        return normalized

    def _require_available(self) -> None:
        problem = self.availability_error()
        if problem:
            raise NativeInjectorUnavailable(problem, 'UNAVAILABLE')
