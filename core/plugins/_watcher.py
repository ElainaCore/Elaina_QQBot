"""插件文件监视与代码热重载。"""

import asyncio
import contextlib
import os

from core.foundation.logging import PLUGIN, get_logger, report_error

log = get_logger(PLUGIN, '管理器')


class _WatcherMixin:
    """监视插件文件变更并自动热重载。"""

    def _scan_plugin_mtimes(self, pdir):
        for root, _, files in os.walk(pdir):
            for f in files:
                if f.endswith('.py') and not f.startswith('_'):
                    fp = os.path.join(root, f)
                    with contextlib.suppress(OSError):
                        self._file_mtimes[fp] = os.path.getmtime(fp)

    def _snapshot_all_mtimes(self):
        self._file_mtimes.clear()
        for name in self._plugins:
            pdir = os.path.join(self._dir, name)
            if os.path.isdir(pdir):
                self._scan_plugin_mtimes(pdir)

    def _plugin_of(self, filepath):
        return os.path.relpath(filepath, self._dir).split(os.sep)[0]

    def _detect_changed_plugins(self):
        changed = set()
        for fp, old_mt in list(self._file_mtimes.items()):
            try:
                if os.path.getmtime(fp) != old_mt:
                    changed.add(self._plugin_of(fp))
            except OSError:
                changed.add(self._plugin_of(fp))
                self._file_mtimes.pop(fp, None)
        for name in self._plugins:
            pdir = os.path.join(self._dir, name)
            if not os.path.isdir(pdir):
                continue
            for root, _, files in os.walk(pdir):
                for f in files:
                    if f.endswith('.py') and not f.startswith('_') and os.path.join(root, f) not in self._file_mtimes:
                        changed.add(name)
        return changed

    async def _watcher_loop(self):
        while self._watcher_running:
            try:
                await asyncio.sleep(2)
                changed = await asyncio.to_thread(self._detect_changed_plugins)
                for name in changed:
                    if name in self._plugins:
                        try:
                            await self.reload(name)
                        except Exception as e:
                            report_error(PLUGIN, name, e)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def start_watcher(self):
        if self._watcher_task and not self._watcher_task.done():
            return
        self._watcher_running = True
        self._watcher_task = asyncio.create_task(
            self._watcher_loop(),
            name='plugin-file-watcher',
        )
        log.info('插件文件监视已启动')

    def stop_watcher(self):
        self._watcher_running = False
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
