"""插件管理器 — 加载/卸载/分发/热重载 (v2 异步架构)"""

import asyncio
import contextlib
import json
import os
from collections import OrderedDict
from typing import Any

from core.base.logger import PLUGIN, get_logger
from core.onebot.api import set_api_interceptors
from core.plugin._dispatch import _DispatchMixin
from core.plugin._loader import _LoaderMixin
from core.plugin._plugin_bots import _PluginBotsMixin
from core.plugin._watcher import _WatcherMixin
from core.plugin.context import PluginInfo

log = get_logger(PLUGIN, '管理器')


class PluginManager(_LoaderMixin, _WatcherMixin, _DispatchMixin, _PluginBotsMixin):
    """插件管理器 — 通过 Mixin 组合加载/分发/监视能力"""

    def __init__(self, plugins_dir: str):
        self._dir = os.path.abspath(plugins_dir)
        self._plugins: OrderedDict[str, PluginInfo] = OrderedDict()
        self._all_handlers: list[dict[str, Any]] = []
        self._all_interceptors: list[dict[str, Any]] = []
        self._all_handler_filters: list[dict[str, Any]] = []
        self._all_api_interceptors: list[dict[str, Any]] = []
        # 分发索引桶 (按事件类型预分组, 避免每条事件遍历全部处理器)
        self._msg_handlers: list[dict[str, Any]] = []
        self._generic_handlers: list[dict[str, Any]] = []
        self._typed_handlers: dict[str, list[dict[str, Any]]] = {}
        self._event_handlers: dict[str, list[dict[str, Any]]] = {}
        self._disabled_plugins: set[str] = set()
        self._cooldowns: dict[tuple[str, ...], tuple[float, float]] = {}  # 处理器与会话标识映射到最近触发时间和冷却秒数
        self._last_cooldown_cleanup = 0.0
        self._lock = asyncio.Lock()
        self._file_mtimes: dict[str, float] = {}
        self._watcher_task = None
        self._watcher_running = False
        self._owner_ids: list[str] = []
        self._base_dir = os.path.dirname(self._dir)
        self._plugin_bots = {}
        self._load_plugin_bots()
        self._load_disabled_plugins()

    @property
    def plugins(self) -> dict:
        return dict(self._plugins)

    @property
    def handler_count(self) -> int:
        return len(self._all_handlers)

    # ==================== 索引构建 ====================

    def _rebuild_handler_list(self):
        handlers, intercepts, handler_filters, api_intercepts = [], [], [], []
        for plugin in self._plugins.values():
            if not plugin.enabled:
                continue
            for h in plugin.handlers:
                h['_plugin'] = plugin.name
                handlers.append(h)
            for ic in plugin.interceptors:
                ic['_plugin'] = plugin.name
                intercepts.append(ic)
            for handler_filter in plugin.handler_filters:
                handler_filter['_plugin'] = plugin.name
                handler_filters.append(handler_filter)
            for ic in plugin.api_interceptors:
                ic['_plugin'] = plugin.name
                api_intercepts.append(ic)
        self._all_handlers = handlers
        self._all_interceptors = intercepts
        self._all_handler_filters = sorted(
            handler_filters,
            key=lambda item: -item['priority'],
        )
        self._all_api_interceptors = sorted(api_intercepts, key=lambda item: -item['priority'])
        self._apply_bot_bindings()
        self._build_dispatch_index()
        set_api_interceptors(self._all_api_interceptors)

    # ==================== 权限 ====================

    def set_owner_ids(self, owner_ids: list):
        self._owner_ids = [str(uid) for uid in owner_ids]

    def _is_owner(self, event) -> bool:
        uid = str(getattr(event, 'user_id', '') or '')
        return uid in self._owner_ids if self._owner_ids else False

    # ==================== 管理接口 ====================

    def enable_plugin(self, name):
        changed = name in self._disabled_plugins
        self._disabled_plugins.discard(name)
        if changed:
            self._save_disabled_plugins()
        if name in self._plugins:
            self._plugins[name].enabled = True
            self._rebuild_handler_list()
            return True
        return changed

    def disable_plugin(self, name):
        changed = name not in self._disabled_plugins
        self._disabled_plugins.add(name)
        if changed:
            self._save_disabled_plugins()
        if name in self._plugins:
            self._plugins[name].enabled = False
            self._rebuild_handler_list()
            return True
        return changed

    def is_disabled(self, name: str) -> bool:
        return name in self._disabled_plugins

    def get_disabled_plugins(self) -> set:
        return set(self._disabled_plugins)

    def get_plugin_list(self):
        return [
            {
                'name': p.name,
                'enabled': p.enabled,
                'disabled_persist': p.name in self._disabled_plugins,
                'handlers': [h['name'] for h in p.handlers],
                'handler_count': len(p.handlers),
                'load_time': round(p.load_time, 3),
                'error': p.error,
                'is_large': p.is_large,
            }
            for p in self._plugins.values()
        ]

    def get_command_list(self):
        return [
            {
                'name': h['name'],
                'pattern': h['pattern'],
                'desc': h['desc'],
                'plugin': h.get('_plugin', ''),
                'owner_only': h['owner_only'],
                'priority': h['priority'],
            }
            for h in self._all_handlers
        ]

    async def shutdown(self) -> None:
        """停止文件监视并依次执行全部插件的卸载钩子。"""
        watcher_task = self._watcher_task
        self.stop_watcher()
        if watcher_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
        self._watcher_task = None
        async with self._lock:
            for name in list(self._plugins):
                await self._unload_plugin(name)
            self._rebuild_handler_list()

    def get_web_plugin_info(self) -> dict:
        """构建 {目录名: {commands, description, meta}}"""
        result = {}
        for p in self._plugins.values():
            cmds = [
                {
                    'name': h.get('name', ''),
                    'pattern': h.get('pattern', ''),
                    'desc': h.get('desc', ''),
                    'owner_only': h.get('owner_only', False),
                    'group_only': h.get('group_only', False),
                }
                for h in p.handlers
            ]
            desc = ''
            if p.module and getattr(p.module, '__doc__', None):
                desc = p.module.__doc__.strip().split('\n')[0]
            result[p.name] = {'commands': cmds, 'description': desc, 'meta': p.meta}
        return result

    def list_plugins(self) -> list:
        """列出所有可发现的插件 (含未加载的)"""
        result: list[dict[str, Any]] = []
        if not os.path.isdir(self._dir):
            return result
        for name in sorted(os.listdir(self._dir)):
            plugin_dir = os.path.join(self._dir, name)
            if not os.path.isdir(plugin_dir) or name.startswith(('_', '.')):
                continue
            info = self._plugins.get(name)
            result.append(
                {
                    'name': name,
                    'loaded': name in self._plugins,
                    'enabled': info.enabled if info else name not in self._disabled_plugins,
                    'handlers': len(info.handlers) if info else 0,
                }
            )
        return result

    # ==================== 禁用持久化 ====================

    def _load_disabled_plugins(self):
        path = os.path.join(self._dir, 'plugins_disabled.json')
        if not os.path.isfile(path):
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._disabled_plugins = set(data)
        except Exception as e:
            log.warning(f'加载禁用插件列表失败: {e}')

    def _save_disabled_plugins(self):
        path = os.path.join(self._dir, 'plugins_disabled.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(sorted(self._disabled_plugins), f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f'保存禁用插件列表失败: {e}')
