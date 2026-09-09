"""QLinux 渠道 — Lagrange 多 bot runner 进程管理器。

职责:
1. runner 二进制管理: 检查本地 → 缺失时从 GitHub Releases 下载 (镜像回退) → 解压
2. runner 子进程托管: 启动 (SIGN_SERVER_URL 环境变量注入签名地址)、stdin/stdout JSON-RPC 通信
3. 多 bot 生命周期: bot.create / login.qr / login.password / submit.captcha / submit.sms / bot.stop
4. 事件转发: runner 事件 → OneBot v11 形状 → app.ingest_event() (与内嵌 QQ 同一条管线)
5. 动作绑定: register_local_bot → send_group_msg / send_private_msg / get_login_info 等
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import shutil
import stat
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import aiohttp

log = logging.getLogger('ElainaQQ.qlinux')

# ==================== 默认配置 ====================

RUNNER_VERSION = 'v1.0.0'
# 发布仓库: 用户可在配置中改 (先 fork 或自传 Releases 后改这里)
RUNNER_REPO = 'ElainaCore/lagrange-runner'
# 下载镜像回退链 (与插件市场同一套)
_MIRROR_PREFIXES = [
    '',  # 官方直连优先
    'https://ghproxy.cc/',
    'https://gh-proxy.com/',
    'https://gh.llkk.cc/',
]

_DEFAULT_SIGN_SERVER = 'https://esign.linsur.cn/'


def _default_runner_url() -> str:
    """根据当前平台返回 runner 压缩包下载地址。"""
    system = platform.system().lower()  # windows / linux / darwin
    if system == 'windows':
        asset = f'lagrange-runner-{RUNNER_VERSION}-win-x64.zip'
    elif system == 'linux':
        asset = f'lagrange-runner-{RUNNER_VERSION}-linux-x64.tar.gz'
    else:
        raise RuntimeError(f'QLinux 渠道不支持当前平台: {system}')
    return f'https://github.com/{RUNNER_REPO}/releases/download/{RUNNER_VERSION}/{asset}'


def _runner_exe_name() -> str:
    return 'runner-win.exe' if platform.system().lower() == 'windows' else 'runner-win'


# ==================== Runner 下载器 ====================


class RunnerDownloader:
    """从 GitHub Releases 下载 runner (镜像回退), 解压到 bin 目录。"""

    def __init__(self, bin_dir: Path, progress_cb: Callable[[int, int], None] | None = None):
        self._bin_dir = bin_dir
        self._progress_cb = progress_cb
        self._lock = asyncio.Lock()

    @property
    def exe_path(self) -> Path:
        return self._bin_dir / _runner_exe_name()

    def has_runner(self) -> bool:
        return self.exe_path.is_file() and self.exe_path.stat().st_size > 1_000_000

    async def ensure_runner(self) -> Path:
        """确保 runner 二进制存在; 缺失则下载并解压。"""
        if self.has_runner():
            return self.exe_path
        async with self._lock:
            if self.has_runner():  # 双检
                return self.exe_path
            await self._download_and_extract()
        return self.exe_path

    async def _download_and_extract(self) -> None:
        url = _default_runner_url()
        log.info('QLinux runner 不存在, 开始下载: %s', url)
        archive_path = self._bin_dir / ('runner-pkg.zip' if url.endswith('.zip') else 'runner-pkg.tar.gz')
        self._bin_dir.mkdir(parents=True, exist_ok=True)

        last_err: Exception | None = None
        for prefix in _MIRROR_PREFIXES:
            final_url = prefix + url if prefix else url
            try:
                await self._download(final_url, archive_path)
                self._extract(archive_path)
                self._make_executable()
                log.info('QLinux runner 下载完成: %s', self.exe_path)
                return
            except Exception as e:  # noqa: BLE001 — 逐镜像尝试
                log.warning('下载失败 (%s): %s', final_url or '官方', e)
                last_err = e

        raise RuntimeError(f'QLinux runner 下载失败 (所有镜像均不可用): {last_err}')

    async def _download(self, url: str, dest: Path) -> None:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get('Content-Length') or 0)
                done = 0
                with dest.open('wb') as f:
                    async for chunk in resp.content.iter_chunked(256 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        if self._progress_cb and total:
                            self._progress_cb(done, total)

    def _extract(self, archive_path: Path) -> None:
        if archive_path.suffix == '.zip':
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(self._bin_dir)
        else:
            with tarfile.open(archive_path) as tf:
                tf.extractall(self._bin_dir)
        archive_path.unlink(missing_ok=True)

    def _make_executable(self) -> None:
        if os.name != 'nt' and self.exe_path.is_file():
            self.exe_path.chmod(self.exe_path.stat().st_mode | stat.S_IEXEC)


# ==================== Runner 子进程 (JSON-RPC over stdio) ====================


class RunnerRPC:
    """单例 runner 子进程: 承载全部 bot 实例。

    协议: 每行一个 JSON。stdin 发请求 {id, method, params}; stdout 收
    响应 {id, result|error} 与事件 {event, bot_id, ...} (区分键为 event)。
    """

    def __init__(self, exe_path: Path, data_root: Path, sign_server: str,
                 event_handler: Callable[[dict], None]):
        self._exe_path = exe_path
        self._data_root = data_root
        self._sign_server = sign_server
        self._event_handler = event_handler  # 事件回调 (由 RunnerManager 提供)
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._id_counter = 0
        self._reader_task: asyncio.Task | None = None
        self._alive = False
        self._lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        return self._alive and self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.alive:
            return
        async with self._lock:
            if self.alive:
                return
            env = dict(os.environ)
            env['SIGN_SERVER_URL'] = self._sign_server
            env['RUNNER_DATA_ROOT'] = str(self._data_root)
            env.setdefault('DOTNET_TieredPGO', '1')
            log.info('启动 QLinux runner: %s (签名端: %s)', self._exe_path, self._sign_server)
            self._proc = await asyncio.create_subprocess_exec(
                str(self._exe_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=None,  # runner 自身日志透传到框架日志
                env=env,
            )
            self._alive = True
            self._reader_task = asyncio.create_task(self._read_loop(), name='qlinux-runner-reader')
            # 等待进程就绪 (ping 探活)
            await asyncio.wait_for(self.call('ping'), timeout=15)

    async def stop(self) -> None:
        self._alive = False
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (ProcessLookupError, asyncio.TimeoutError):
                if self._proc.returncode is None:
                    self._proc.kill()
        self._proc = None
        # 所有挂起请求立即失败
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError('runner 已停止'))
        self._pending.clear()

    async def call(self, method: str, params: dict | None = None, timeout: float = 60) -> Any:
        """发起 RPC 请求并等待响应。"""
        if not self.alive:
            raise RuntimeError('runner 未运行')
        self._id_counter += 1
        rid = f'q{self._id_counter}'
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        payload = json.dumps({'id': rid, 'method': method, 'params': params or {}},
                             ensure_ascii=False, separators=(',', ':'))
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(payload.encode('utf-8') + b'\n')
        await self._proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode('utf-8', errors='replace').strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    log.warning('QLinux runner 输出非 JSON: %s', line[:200])
                    continue
                if 'event' in data:
                    try:
                        self._event_handler(data)
                    except Exception:  # noqa: BLE001
                        log.exception('QLinux 事件处理异常')
                elif 'id' in data:
                    fut = self._pending.pop(str(data['id']), None)
                    if fut and not fut.done():
                        if 'error' in data:
                            fut.set_exception(RuntimeError(data['error']))
                        else:
                            fut.set_result(data.get('result'))
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception('QLinux runner 读取循环异常')
        finally:
            self._alive = False
            log.warning('QLinux runner 进程退出 (code=%s)', self._proc.returncode if self._proc else '?')
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError('runner 进程意外退出'))
            self._pending.clear()


# ==================== 事件 → OneBot v11 映射 ====================


def _msg_time() -> int:
    return int(time.time())


def _entities_to_ob(data: dict) -> list[dict]:
    """runner 消息实体 (entities) → OneBot v11 消息段。"""
    out: list[dict] = []
    for seg in data.get('entities', []):
        t = seg.get('type')
        if t == 'text':
            out.append({'type': 'text', 'data': {'text': seg.get('text', '')}})
        elif t == 'mention':
            qq = str(seg.get('uin', ''))
            out.append({'type': 'at', 'data': {'qq': 'all' if qq == '0' else qq}})
        elif t == 'image':
            out.append({'type': 'image', 'data': {
                'file': seg.get('url') or seg.get('file_id', ''),
                'url': seg.get('url', ''),
                'file_size': seg.get('size', 0),
            }})
        elif t == 'record':
            out.append({'type': 'record', 'data': {'file': seg.get('url') or seg.get('file_id', '')}})
        elif t == 'json':
            out.append({'type': 'json', 'data': {'data': seg.get('data', '')}})
        elif t == 'reply':
            out.append({'type': 'reply', 'data': {'id': str(seg.get('seq', ''))}})
    return out


def _ob_message_id(bot_id: str, sequence: int, group: bool) -> str:
    return f'{bot_id}:{group and "g" or "p"}:{sequence}'


def runner_event_to_onebot(event: dict) -> dict | None:
    """runner 事件 → OneBot v11 事件 payload (进入 app.ingest_event 的形状)。"""
    etype = event.get('event')
    bot_id = str(event.get('bot_id', ''))

    if etype == 'message':
        d = event.get('data', {})
        uin = str(event.get('uin') or d.get('self_uin') or bot_id)
        contact = d.get('contact', {})
        group_id = contact.get('group_uin')
        is_group = group_id is not None
        message_id = _ob_message_id(bot_id, int(d.get('sequence', 0)), is_group)
        sender_uin = int(contact.get('uin', 0) or 0)
        payload = {
            'time': int(d.get('time') or _msg_time()),
            'self_id': uin,
            'post_type': 'message',
            'message_type': 'group' if is_group else 'private',
            'sub_type': 'normal',
            'message_id': message_id,
            'user_id': sender_uin,
            'message': _entities_to_ob(d),
            'raw_message': ''.join(
                s.get('text', '') if s.get('type') == 'text' else f"[{s.get('type')}]"
                for s in d.get('entities', [])),
            'font': 0,
            'sender': {
                'user_id': sender_uin,
                'nickname': contact.get('nickname', ''),
                'card': contact.get('card', '') if is_group else '',
                'role': _map_role(contact.get('permission')) if is_group else None,
            },
        }
        if is_group:
            payload['group_id'] = int(group_id)
        return payload

    if etype == 'bot.online':
        return {
            'time': _msg_time(), 'self_id': str(event.get('uin') or bot_id),
            'post_type': 'meta_event', 'meta_event_type': 'lifecycle',
            'sub_type': 'connect',
        }
    if etype == 'bot.offline':
        return {
            'time': _msg_time(), 'self_id': str(event.get('uin') or bot_id),
            'post_type': 'notice', 'notice_type': 'bot_offline',
            'reason': event.get('reason', ''), 'tips': event.get('tips'),
        }
    # qr.code / qr.state / login.* / keystore.refreshed 是登录流程事件,
    # 由 RunnerManager 状态机消化, 不进 OneBot 管线
    return None


def _map_role(permission: str | None) -> str:
    return {'Owner': 'owner', 'Admin': 'admin'}.get(permission or '', 'member')
