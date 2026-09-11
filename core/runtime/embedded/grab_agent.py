"""GrabAgentInjector：把 qq-grab-agent.dll 注入 QQ 主进程并通过命名管道通信。"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import json
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger('ElainaQQ.grab_agent')

_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.CreateFileW.restype = wt.HANDLE
_kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
_kernel32.ReadFile.restype = wt.BOOL
_kernel32.ReadFile.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPVOID]
_kernel32.PeekNamedPipe.restype = wt.BOOL
_kernel32.PeekNamedPipe.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]
_kernel32.WriteFile.restype = wt.BOOL
_kernel32.WriteFile.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPVOID]
_kernel32.CloseHandle.restype = wt.BOOL
_kernel32.CloseHandle.argtypes = [wt.HANDLE]
_kernel32.CreateRemoteThread.restype = wt.HANDLE
_kernel32.CreateRemoteThread.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.LPVOID, wt.LPVOID, wt.DWORD, wt.LPVOID]
_kernel32.VirtualAllocEx.restype = wt.LPVOID
_kernel32.VirtualAllocEx.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD, wt.DWORD]
_kernel32.WriteProcessMemory.restype = wt.BOOL
_kernel32.WriteProcessMemory.argtypes = [wt.HANDLE, wt.LPVOID, wt.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_kernel32.GetModuleHandleW.restype = wt.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
_kernel32.GetProcAddress.restype = wt.LPVOID
_kernel32.GetProcAddress.argtypes = [wt.HMODULE, ctypes.c_char_p]
_kernel32.OpenProcess.restype = wt.HANDLE
_kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_PIPE_NAME = r'\\.\pipe\elaina_grab_agent_v2'
_PIPE_EV_NAME = r'\\.\pipe\elaina_grab_agent_v2_ev'
_AGENT_DLL_NAME = 'qq-grab-agent.dll'

ProcessAccess = 0x1FFFFF  # PROCESS_ALL_ACCESS (newer Windows)
_MEM_COMMIT = 0x1000
_MEM_RESERVE = 0x2000
_PAGE_READWRITE = 0x04


class GrabAgentError(RuntimeError):
    pass


class GrabAgentInjector:
    """注入 agent.dll 并维持管道会话。一个 QQ pid 一个实例。"""

    def __init__(self, native_dir: str | Path) -> None:
        self._dll_path = Path(native_dir) / _AGENT_DLL_NAME

    @property
    def dll_path(self) -> Path:
        return self._dll_path

    @property
    def available(self) -> bool:
        return self._dll_path.is_file()

    def inject(self, pid: int) -> None:
        """向目标 pid 注入 agent（已注入时 LoadLibrary 幂等）。"""
        if not self.available:
            raise GrabAgentError(f'agent DLL 不存在: {self._dll_path}')
        handle = _kernel32.OpenProcess(ProcessAccess, False, pid)
        if not handle:
            raise GrabAgentError(f'无法打开 QQ 进程 {pid}（需管理员）: os error {ctypes.get_last_error()}')
        try:
            payload = (str(self._dll_path.resolve()) + '\x00').encode('utf-16-le')
            remote = _kernel32.VirtualAllocEx(handle, None, len(payload), _MEM_COMMIT | _MEM_RESERVE, _PAGE_READWRITE)
            if not remote:
                raise GrabAgentError(f'VirtualAllocEx 失败: {ctypes.get_last_error()}')
            written = ctypes.c_size_t(0)
            if not _kernel32.WriteProcessMemory(handle, remote, payload, len(payload), ctypes.byref(written)):
                raise GrabAgentError(f'WriteProcessMemory 失败: {ctypes.get_last_error()}')
            kernel32 = _kernel32.GetModuleHandleW('kernel32.dll')
            proc = _kernel32.GetProcAddress(kernel32, b'LoadLibraryW')
            if not proc:
                raise GrabAgentError('无法定位 LoadLibraryW')
            thread = _kernel32.CreateRemoteThread(handle, None, 0, proc, remote, 0, None)
            if not thread:
                raise GrabAgentError(f'CreateRemoteThread 失败: {ctypes.get_last_error()}')
            _kernel32.CloseHandle(thread)
        finally:
            _kernel32.CloseHandle(handle)

    # -- 管道会话 ---------------------------------------------------------

    def connect(self, timeout: float = 10.0) -> GrabAgentSession:
        import time
        deadline = time.monotonic() + timeout
        cmd_h = None
        ev_h = None
        try:
            while time.monotonic() < deadline:
                if cmd_h is None:
                    h = _kernel32.CreateFileW(
                        _PIPE_NAME, _GENERIC_WRITE, 0, None,
                        _OPEN_EXISTING, 0, None)
                    if h and h != wt.HANDLE(-1).value:
                        cmd_h = int(h)
                if cmd_h is not None and ev_h is None:
                    h2 = _kernel32.CreateFileW(
                        _PIPE_EV_NAME, _GENERIC_READ, 0, None,
                        _OPEN_EXISTING, 0, None)
                    if h2 and h2 != wt.HANDLE(-1).value:
                        ev_h = int(h2)
                if cmd_h is not None and ev_h is not None:
                    return GrabAgentSession(cmd_h, ev_h)
                time.sleep(0.5)
            raise GrabAgentError('agent 管道连接超时（agent 未注入或 hook 失败）')
        except BaseException:
            # 连接中途失败必须关闭已拿到的句柄，否则 agent 的 cmd server
            if cmd_h is not None:
                _kernel32.CloseHandle(cmd_h)
            if ev_h is not None:
                _kernel32.CloseHandle(ev_h)
            raise


class GrabAgentSession:
    """与 agent 的一条管道会话（字节流帧：4B len + JSON）。"""

    def __init__(self, cmd_handle: int, ev_handle: int) -> None:
        self._handle = cmd_handle
        self._ev_handle = ev_handle
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def request(self, payload: dict, timeout_seconds: float = 40.0) -> dict:
        """发送命令，等待匹配事件或错误。grab 命令等待 grab_result。"""
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        frame = len(data).to_bytes(4, 'little') + data
        written = wt.DWORD(0)
        if not _kernel32.WriteFile(self._handle, frame, len(frame), ctypes.byref(written), None):
            raise GrabAgentError(f'管道写入失败: {ctypes.get_last_error()}')
        want_result = payload.get('op') == 'grab'
        return self._wait_event(want_result, timeout_seconds)

    def _wait_event(self, want_result: bool, timeout_seconds: float) -> dict:
        import time
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            ev = self._read_event()
            if ev is None:
                time.sleep(0.2)
                continue
            kind = ev.get('event')
            if kind == 'grab_result':
                return ev
            if want_result and kind == 'status':
                # grab 等待中遇到的过期 status 心跳响应：暂存，不能当作 grab 结果
                self._events.append(ev)
                continue
            if kind == 'status':
                return ev
            self._events.append(ev)
        raise GrabAgentError('等待 agent 响应超时')

    def _read_event(self) -> dict | None:
        # Transient reconnect: the agent's ev-pipe server needs a moment to
        for attempt in range(2):
            ev = self._read_event_once()
            if ev is not None or attempt == 1:
                return ev
            time.sleep(0.3)
        return None

    def _read_event_once(self) -> dict | None:
        with self._lock:
            avail = wt.DWORD(0)
            if not _kernel32.PeekNamedPipe(self._ev_handle, None, 0, None, ctypes.byref(avail), None):
                err = ctypes.get_last_error()
                if err in (233, 232):
                    raise GrabAgentError(f'事件管道已断开 (err={err})')
                return None
            if avail.value < 4:
                return None
            buf = (ctypes.c_char * 4)()
            got = wt.DWORD(0)
            if not _kernel32.ReadFile(self._ev_handle, buf, 4, ctypes.byref(got), None):
                return None
            n = int.from_bytes(buf.raw, 'little')
            if n == 0 or n > (1 << 20):
                return None
            body = (ctypes.c_char * n)()
            got2 = wt.DWORD(0)
            # body may arrive in chunks; loop until complete
            while got2.value < n:
                chunk = wt.DWORD(0)
                dst = ctypes.cast(ctypes.byref(body, got2.value), wt.LPVOID)
                if not _kernel32.ReadFile(self._ev_handle, dst, n - got2.value, ctypes.byref(chunk), None):
                    return None
                if chunk.value == 0:
                    return None
                got2.value += chunk.value
            try:
                ev = json.loads(bytes(body).decode('utf-8', 'replace'))
                log.info('agent event: %s', str(ev)[:2000])
                return ev
            except json.JSONDecodeError:
                return None

    def drain_events(self) -> list[dict]:
        out, self._events = self._events, []
        return out

    def close(self) -> None:
        with contextlib.suppress(Exception):
            _kernel32.CloseHandle(self._handle)
        self._handle = 0
        with contextlib.suppress(Exception):
            _kernel32.CloseHandle(self._ev_handle)
        self._ev_handle = 0
