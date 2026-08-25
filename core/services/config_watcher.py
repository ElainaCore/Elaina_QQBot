"""配置文件监视服务 (异步架构)"""

import asyncio
import contextlib
import inspect
import os

from core.foundation.config import cfg
from core.foundation.logging import SYSTEM, get_logger

log = get_logger(SYSTEM, '配置监视')


class ConfigWatcherService:
    """异步检查配置文件变更并热加载"""

    def __init__(self, interval: float = 5.0, on_reload=None):
        self._interval = interval
        self._on_reload = on_reload
        self._running = False
        self._task = None
        self._mtimes: dict[str, tuple[int, int]] = {}

    def start(self):
        self._running = True
        self._task = asyncio.ensure_future(self._watch_loop())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def shutdown(self):
        """停止并等待监视任务退出。"""
        self.stop()
        task, self._task = self._task, None
        if task:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def mark_current(self, name: str) -> None:
        """记录由框架主动应用的配置版本，避免监视器重复重载。"""
        path = os.path.join(cfg._config_dir, f'{name}.yaml')
        try:
            stat = os.stat(path)
            self._mtimes[path] = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            self._mtimes.pop(path, None)

    def forget(self, name: str) -> None:
        path = os.path.join(cfg._config_dir, f'{name}.yaml')
        if os.path.isfile(path):
            self._mtimes[path] = (-1, -1)
        else:
            self._mtimes.pop(path, None)

    async def _watch_loop(self):
        config_dir = cfg._config_dir
        if not config_dir:
            return
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                changed = await asyncio.to_thread(self._detect_changes, config_dir)
                for name in changed:
                    try:
                        loaded = await asyncio.to_thread(cfg.reload, name)
                        if not loaded:
                            self.forget(name)
                            log.warning('配置热加载失败，继续使用旧配置: %s.yaml', name)
                            continue
                        result = self._on_reload(name) if self._on_reload else None
                        if inspect.isawaitable(result):
                            result = await result
                        restart_fields = list((result or {}).get('restart_required', ()))
                        if restart_fields:
                            log.warning('配置已读取，但以下字段需重启生效: %s', ', '.join(restart_fields))
                        else:
                            log.info('配置热加载已应用: %s.yaml', name)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        self.forget(name)
                        log.warning('配置热加载应用失败，将在下次扫描重试 [%s]: %s', name, error)
            except asyncio.CancelledError:
                break
            except Exception as error:
                log.warning('配置监视失败: %s', error)

    def _detect_changes(self, config_dir: str) -> list:
        changed = []
        try:
            for fname in os.listdir(config_dir):
                if not fname.endswith('.yaml') or fname.endswith('.example.yaml'):
                    continue
                path = os.path.join(config_dir, fname)
                stat = os.stat(path)
                fingerprint = (stat.st_mtime_ns, stat.st_size)
                if path in self._mtimes and fingerprint != self._mtimes[path]:
                    name = fname[:-5]
                    changed.append(name)
                self._mtimes[path] = fingerprint
        except Exception as error:
            log.warning('扫描配置文件失败: %s', error)
        return changed
