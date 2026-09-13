"""QLinux 渠道 — Lagrange 多 bot runner 进程管理器。"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import platform
import stat
import tarfile
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp

from core.foundation.archives import safe_extract_tar, safe_extractall
from core.protocols.onebot.contract import normalize_role
from core.protocols.onebot.event import normalize_event
from core.protocols.onebot.message import normalize_message

log = logging.getLogger('ElainaQQ.qlinux')

# ==================== 默认配置 ====================

RUNNER_VERSION = 'v1.0.6'
# 发布仓库 (与框架更新同一镜像体系拉取)
RUNNER_REPO = 'ElainaCore/lagrange-runner'

# 镜像缓存为空时的兑底链 (与插件市场同源)
_FALLBACK_MIRRORS = [
    '',
    'https://ghproxy.cc/',
    'https://gh-proxy.com/',
    'https://gh.llkk.cc/',
    'https://gh.idayer.com/',
]

_DEFAULT_SIGN_SERVER = 'https://esign.linsur.cn/'
_MAX_RUNNER_ARCHIVE_SIZE = 256 * 1024 * 1024
# Runner RPC 每行传输一个 JSON 对象，大型成员列表需要更大的读取上限。
_MAX_RUNNER_LINE_SIZE = 64 * 1024 * 1024
_MAX_RUNNER_FRAME_SIZE = 128 * 1024 * 1024


def _runner_asset() -> str:
    """根据当前系统返回 Releases 产物文件名。"""
    system = platform.system().lower()  # windows / linux / darwin
    if system == 'windows':
        return f'lagrange-runner-{RUNNER_VERSION}-win-x64.zip'
    if system == 'linux':
        return f'lagrange-runner-{RUNNER_VERSION}-linux-x64.tar.gz'
    raise RuntimeError(f'QLinux 渠道不支持当前平台: {system}')


def _runner_base_url() -> str:
    return f'https://github.com/{RUNNER_REPO}/releases/download/{RUNNER_VERSION}/{_runner_asset()}'


# 兼容旧引用
_default_runner_url = _runner_base_url


def _runner_exe_name() -> str:
    """压缩包内统一叫 lagrange-runner (无扩展名 = Linux ELF; .exe = Windows)。"""
    return 'lagrange-runner.exe' if platform.system().lower() == 'windows' else 'lagrange-runner'


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

    @property
    def version_path(self) -> Path:
        """返回成功解压后写入的 runner 版本标记路径。"""
        return self._bin_dir / '.runner-version'

    def has_runner(self) -> bool:
        if not (self.exe_path.is_file() and self.exe_path.stat().st_size > 1_000_000):
            return False
        try:
            return self.version_path.read_text(encoding='utf-8').strip() == RUNNER_VERSION
        except (OSError, UnicodeError):
            return False

    async def ensure_runner(self) -> Path:
        """确保 runner 二进制存在; 缺失则下载并解压。"""
        if self.has_runner():
            return self.exe_path
        async with self._lock:
            if self.has_runner():  # 双检
                return self.exe_path
            await self._download_and_extract()
        return self.exe_path

    async def _ranked_urls(self) -> list[str]:
        """镜像 URL 列表: 复用框架更新器的测速缓存 (30 分钟磁盘缓存), 空则用兑底链。"""
        base = _runner_base_url()
        try:
            from web.tools._updater.mirror import get_fast_mirrors
            from web.tools._updater.shared import _build_mirror_url

            cached = await get_fast_mirrors()  # [('mirror': prefix, ...)] 按延迟排序
            urls = [
                _build_mirror_url(base, m['mirror'] if isinstance(m, dict) else m)
                for m in cached
            ]
        except Exception as e:  # noqa: BLE001 — 框架更新器不可用时兑底
            log.warning('镜像测速不可用 (%s), 使用兑底镜像链', e)
            urls = []
        for prefix in _FALLBACK_MIRRORS:
            u = (prefix + base) if prefix else base
            if u not in urls:
                urls.append(u)
        # 官方直连永远在末尾兜底 (测速链可能已含直连选项)
        if base not in urls:
            urls.append(base)
        return urls

    async def _download_and_extract(self) -> None:
        base_url = _runner_base_url()
        urls = await self._ranked_urls()
        log.info('QLinux runner 不存在, 开始下载: %s (共 %d 个候选源)', base_url, len(urls))
        archive_path = self._bin_dir / ('runner-pkg.zip' if base_url.endswith('.zip') else 'runner-pkg.tar.gz')
        self._bin_dir.mkdir(parents=True, exist_ok=True)

        last_err: Exception | None = None
        for final_url in urls:
            try:
                # 下载或解压失败时清理旧版本，避免误判为可用。
                self.exe_path.unlink(missing_ok=True)
                self.version_path.unlink(missing_ok=True)
                await self._download(final_url, archive_path)
                self._extract(archive_path)
                self._make_executable()
                if not (self.exe_path.is_file() and self.exe_path.stat().st_size > 1_000_000):
                    raise RuntimeError('压缩包中未找到有效的 runner 二进制')
                # 原子替换版本标记，避免中断写入造成误判。
                marker_tmp = self.version_path.with_suffix('.tmp')
                marker_tmp.write_text(RUNNER_VERSION, encoding='utf-8')
                marker_tmp.replace(self.version_path)
                log.info('QLinux runner 下载完成: %s', self.exe_path)
                return
            except Exception as e:  # noqa: BLE001 — 逐镜像尝试
                archive_path.unlink(missing_ok=True)
                self.version_path.unlink(missing_ok=True)
                log.warning('下载失败 (%s): %s', final_url, e)
                last_err = e

        raise RuntimeError(f'QLinux runner 下载失败 (所有镜像均不可用): {last_err}')

    async def _download(self, url: str, dest: Path) -> None:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get('Content-Length') or 0)
            if total > _MAX_RUNNER_ARCHIVE_SIZE:
                raise ValueError('QLinux runner 压缩包超过大小限制')
            done = 0
            with dest.open('wb') as f:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    if done + len(chunk) > _MAX_RUNNER_ARCHIVE_SIZE:
                        raise ValueError('QLinux runner 压缩包超过大小限制')
                    f.write(chunk)
                    done += len(chunk)
                    if self._progress_cb and total:
                        self._progress_cb(done, total)

    def _extract(self, archive_path: Path) -> None:
        if archive_path.suffix == '.zip':
            with zipfile.ZipFile(archive_path) as zf:
                safe_extractall(zf, str(self._bin_dir), max_size=_MAX_RUNNER_ARCHIVE_SIZE)  # nosec B202
        else:
            with tarfile.open(archive_path) as tf:
                safe_extract_tar(tf, str(self._bin_dir), max_size=_MAX_RUNNER_ARCHIVE_SIZE)
        archive_path.unlink(missing_ok=True)

    def _make_executable(self) -> None:
        if os.name != 'nt' and self.exe_path.is_file():
            self.exe_path.chmod(self.exe_path.stat().st_mode | stat.S_IEXEC)


# ==================== Runner 子进程 (JSON-RPC over stdio) ====================


class RunnerRPC:
    """单例 runner 子进程: 承载全部 bot 实例。"""

    def __init__(self, exe_path: Path, data_root: Path, sign_server: str,
                 event_handler: Callable[[dict], None],
                 on_exit: Callable[[RunnerRPC], object] | None = None):
        self._exe_path = exe_path
        self._data_root = data_root
        self._sign_server = sign_server
        self._event_handler = event_handler  # 事件回调 (由 RunnerManager 提供)
        self._on_exit = on_exit
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._id_counter = 0
        self._reader_task: asyncio.Task | None = None
        self._alive = False
        self._stopping = False
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
            self._stopping = False
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
                limit=_MAX_RUNNER_LINE_SIZE,
            )
            self._alive = True
            self._reader_task = asyncio.create_task(self._read_loop(), name='qlinux-runner-reader')
            # 等待进程就绪 (ping 探活)
            try:
                await asyncio.wait_for(self.call('ping'), timeout=15)
            except BaseException:
                await self.stop()
                raise

    async def stop(self) -> None:
        self._stopping = True
        self._alive = False
        reader_task = self._reader_task
        self._reader_task = None
        if reader_task:
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (TimeoutError, ProcessLookupError):
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
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError('runner 标准输入不可用')
        self._id_counter += 1
        rid = f'q{self._id_counter}'
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        payload = json.dumps({'id': rid, 'method': method, 'params': params or {}},
                             ensure_ascii=False, separators=(',', ':'))
        try:
            self._proc.stdin.write(payload.encode('utf-8') + b'\n')
            await self._proc.stdin.drain()
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def _read_loop(self) -> None:
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError('runner 标准输出不可用')
        stdout = self._proc.stdout
        buffer = bytearray()
        dropped_bytes = 0
        try:
            while True:
                chunk = await stdout.read(64 * 1024)
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > _MAX_RUNNER_FRAME_SIZE:
                    newline = buffer.find(b'\n')
                    if newline < 0:
                        dropped_bytes += len(buffer)
                        buffer.clear()
                        continue
                    dropped_bytes += newline + 1
                    del buffer[: newline + 1]
                while True:
                    newline = buffer.find(b'\n')
                    if newline < 0:
                        break
                    raw = bytes(buffer[:newline])
                    del buffer[: newline + 1]
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
            if buffer.strip():
                log.warning('QLinux runner stdout 在 EOF 前收到未完整帧 (%d bytes)', len(buffer))
            if dropped_bytes:
                log.warning('QLinux runner 丢弃超限 stdout 数据: %d bytes', dropped_bytes)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception('QLinux runner 读取循环异常')
        finally:
            self._alive = False
            code = self._proc.returncode if self._proc else None
            log.warning('QLinux runner stdout 读取循环结束 (process_code=%s)', code)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError('runner 进程意外退出'))
            self._pending.clear()
            if not self._stopping and self._on_exit:
                try:
                    callback_result = self._on_exit(self)
                    if inspect.isawaitable(callback_result):
                        asyncio.create_task(callback_result)
                except Exception:  # noqa: BLE001
                    log.exception('QLinux runner 退出恢复回调失败')


# ==================== 事件 → OneBot v11 映射 ====================


def _msg_time() -> int:
    return int(time.time())


def _entities_to_ob(data: dict) -> list[dict]:
    """runner 消息实体 (entities) → OneBot v11 消息段。"""
    out: list[dict] = []
    entities = data.get('entities', [])
    if not isinstance(entities, list):
        return out
    for seg in entities:
        if not isinstance(seg, dict):
            continue
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
        else:
            # 新版 Lagrange 实体（file/video/markdown/forward 等）不应在
            segment_data = (
                dict(seg['data'])
                if isinstance(seg.get('data'), dict)
                else {key: value for key, value in seg.items() if key != 'type'}
            )
            out.append({'type': str(t or 'unknown'), 'data': segment_data})
    return out


def _ob_message_id(bot_id: str, sequence: int, group: bool) -> int:
    """返回规范的 OneBot v11 消息编号。"""
    del bot_id, group
    return int(sequence or 0)


def _normalize_onebot_payload(payload: dict, fallback_uin: str, bot_id: str) -> dict:
    """保持 runner 转发事件与原生事件一致。"""
    payload = dict(payload)
    payload.setdefault('self_id', str(fallback_uin or bot_id))
    normalized = normalize_event(payload, str(fallback_uin or bot_id))
    return normalized or payload


def runner_event_to_onebot(event: dict) -> dict | None:
    """runner 事件 → OneBot v11 事件 payload (进入 app.ingest_event 的形状)。"""
    etype = str(event.get('event') or '').lower()
    bot_id = str(event.get('bot_id', ''))

    # 新版 runner 可以直接转发已经规范化的 OneBot 事件；保留这条
    if etype in {'onebot', 'onebot.event'}:
        payload = event.get('payload') or event.get('data')
        if not isinstance(payload, dict):
            return None
        return _normalize_onebot_payload(
            payload, str(event.get('uin') or bot_id), bot_id)

    # runner 可以直接发送 notice/request/meta_event，也可以使用
    direct_data = event.get('data')
    direct_payload = event.get('payload')
    candidate = direct_payload if isinstance(direct_payload, dict) else direct_data
    if isinstance(candidate, dict) and candidate.get('post_type'):
        return _normalize_onebot_payload(
            candidate, str(event.get('uin') or bot_id), bot_id)

    if etype == 'message' or etype.startswith('message.') or etype.endswith('.message'):
        d = event.get('data', {})
        if not isinstance(d, dict):
            return None
        # 允许 runner 直接携带 OneBot message 数组，避免消息实体扩展
        if isinstance(d.get('message'), list) and d.get('post_type'):
            return _normalize_onebot_payload(
                d, str(event.get('uin') or bot_id), bot_id)
        uin = str(event.get('uin') or d.get('self_uin') or bot_id)
        contact = d.get('contact') if isinstance(d.get('contact'), dict) else {}
        group_id = contact.get('group_uin')
        is_group = group_id not in (None, '')
        sequence = int(d.get('sequence', 0) or 0)
        message_id = _ob_message_id(bot_id, sequence, is_group)
        sender_uin = int(contact.get('uin', 0) or 0)
        role = normalize_role(contact.get('permission')) if is_group else 'member'
        payload = {
            'time': int(d.get('time') or _msg_time()),
            'self_id': uin,
            'post_type': 'message',
            'message_type': 'group' if is_group else 'private',
            'sub_type': 'normal',
            'message_id': message_id,
            'message_seq': sequence,
            'real_seq': sequence,
            'user_id': sender_uin,
            'group_name': contact.get('group_name', '') if is_group else '',
            'message': normalize_message(_entities_to_ob(d)),
            'raw_message': ''.join(
                s.get('text', '') if s.get('type') == 'text' else f"[{s.get('type')}]"
                for s in d.get('entities', [])),
            'font': 0,
            'sender': {
                'user_id': sender_uin,
                'nickname': contact.get('nickname', ''),
                'card': contact.get('card', '') if is_group else '',
                'role': role,
                'permission': role,
                'title': contact.get('special_title', '') if is_group else '',
                'level': int(contact.get('group_level', 0) or 0) if is_group else 0,
            },
        }
        if is_group:
            payload['group_id'] = int(group_id)
        return payload

    # 兼容 runner 的显式 lifecycle/notice/request 事件。事件名称本身是
    if etype.startswith('notice.') or etype == 'notice':
        data = event.get('data') if isinstance(event.get('data'), dict) else {}
        return _normalize_onebot_payload(
            {
                **data,
                'post_type': 'notice',
                'notice_type': data.get('notice_type') or etype.partition('.')[2] or 'notify',
            },
            str(event.get('uin') or bot_id),
            bot_id,
        )
    if etype.startswith('request.') or etype == 'request':
        data = event.get('data') if isinstance(event.get('data'), dict) else {}
        return _normalize_onebot_payload(
            {
                **data,
                'post_type': 'request',
                'request_type': data.get('request_type') or etype.partition('.')[2] or 'unknown',
            },
            str(event.get('uin') or bot_id),
            bot_id,
        )
    if etype.startswith('meta.') or etype == 'meta_event':
        data = event.get('data') if isinstance(event.get('data'), dict) else {}
        return _normalize_onebot_payload(
            {
                **data,
                'post_type': 'meta_event',
                'meta_event_type': data.get('meta_event_type') or etype.partition('.')[2] or 'lifecycle',
            },
            str(event.get('uin') or bot_id),
            bot_id,
        )

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
    return None
