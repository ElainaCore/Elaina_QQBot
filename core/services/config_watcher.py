"""配置文件监视服务 (异步架构)"""

import asyncio
import os

from core.foundation.config import cfg
from core.foundation.logging import SYSTEM, get_logger

log = get_logger(SYSTEM, '配置监视')


class ConfigWatcherService:
    """异步检查配置文件变更并热加载"""

    def __init__(self, interval: float = 5.0):
        self._interval = interval
        self._running = False
        self._task = None
        self._mtimes: dict[str, float] = {}

    def start(self):
        self._running = True
        self._task = asyncio.ensure_future(self._watch_loop())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    async def _watch_loop(self):
        config_dir = cfg._config_dir
        if not config_dir:
            return
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                changed = await asyncio.to_thread(self._detect_changes, config_dir)
                for name in changed:
                    cfg.reload(name)
                    log.info(f'配置热加载: {name}.yaml')
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def _detect_changes(self, config_dir: str) -> list:
        changed = []
        try:
            for fname in os.listdir(config_dir):
                if not fname.endswith('.yaml') or fname.endswith('.example.yaml'):
                    continue
                path = os.path.join(config_dir, fname)
                mtime = os.path.getmtime(path)
                if path in self._mtimes and mtime != self._mtimes[path]:
                    name = fname[:-5]
                    changed.append(name)
                self._mtimes[path] = mtime
        except Exception:
            pass
        return changed
