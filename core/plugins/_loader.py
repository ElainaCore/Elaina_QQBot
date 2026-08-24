"""Single-entry asynchronous plugin discovery and loading."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
import types

from core.foundation.logging import PLUGIN, get_logger, report_error
from core.plugins.context import PluginContext, PluginInfo, plugin_scope
from core.plugins.decorators import (
    _pending_api_interceptors,
    _pending_handler_filters,
    _pending_handlers,
    _pending_interceptors,
    _pending_on_load,
    _pending_on_unload,
)
from core.protocols.onebot.api import api_call_source

log = get_logger(PLUGIN, 'manager')
_ENTRY_FILE = 'main.py'


def _clear_pending() -> None:
    _pending_handlers.clear()
    _pending_on_load.clear()
    _pending_on_unload.clear()
    _pending_interceptors.clear()
    _pending_handler_filters.clear()
    _pending_api_interceptors.clear()


def _collect_pending():
    return (
        list(_pending_handlers),
        list(_pending_on_load),
        list(_pending_on_unload),
        list(_pending_interceptors),
        list(_pending_handler_filters),
        list(_pending_api_interceptors),
    )


async def _run_hooks(funcs, plugin_name: str, context: PluginContext) -> None:
    for func in funcs:
        try:
            with plugin_scope(context), api_call_source(plugin_name):
                await func()
        except Exception as error:
            report_error(PLUGIN, plugin_name, error)


def _submodule_key(func, plugin_name: str) -> str:
    module_name = str(getattr(func, '__module__', '') or '')
    prefix = f'plugins.{plugin_name}.'
    if not module_name.startswith(prefix):
        return ''
    relative = module_name[len(prefix) :].replace('.', '/')
    return f'{plugin_name}/{relative}'


def _read_plugin_meta(module) -> dict[str, str]:
    raw = getattr(module, '__plugin_meta__', None)
    if not isinstance(raw, dict):
        return {}
    allowed = {'name', 'author', 'description', 'version', 'github', 'homepage', 'license'}
    return {key: str(value) for key, value in raw.items() if key in allowed and value}


def _discover_plugins(plugins_dir: str) -> list[str]:
    if not os.path.isdir(plugins_dir):
        os.makedirs(plugins_dir, exist_ok=True)
        return []
    return sorted(
        name
        for name in os.listdir(plugins_dir)
        if not name.startswith(('_', '.'))
        and os.path.isfile(os.path.join(plugins_dir, name, _ENTRY_FILE))
    )


class _LoaderMixin:
    """Load every plugin as one package rooted at main.py."""

    async def load_all(self) -> None:
        if not self._configuration_loaded:
            await asyncio.gather(
                asyncio.to_thread(self._load_plugin_bots),
                asyncio.to_thread(self._load_disabled_plugins),
            )
            self._configuration_loaded = True
        names = await asyncio.to_thread(_discover_plugins, self._dir)
        self._discovered_plugins = set(names)
        loaded = skipped = 0
        for name in names:
            if name in self._disabled_plugins:
                skipped += 1
                log.info('plugin [%s] is disabled', name)
                continue
            try:
                await self.load(name)
                loaded += 1
            except Exception as error:
                report_error(PLUGIN, name, error)
        self._rebuild_handler_list()
        await asyncio.to_thread(self._snapshot_all_mtimes)
        log.info(
            'plugins loaded: %d/%d (disabled %d), %d handlers',
            loaded,
            len(names),
            skipped,
            self.handler_count,
        )

    async def load(self, name: str) -> None:
        plugin_dir = os.path.join(self._dir, name)
        entry_path = os.path.join(plugin_dir, _ENTRY_FILE)
        if not os.path.isfile(entry_path):
            raise FileNotFoundError(f'plugin entry does not exist: {entry_path}')

        async with self._lock:
            if name in self._plugins:
                await self._unload_plugin(name)
            _clear_pending()
            plugin_context = PluginContext(name, plugin_dir)
            await plugin_context.prepare()
            started = time.perf_counter()
            try:
                with plugin_scope(plugin_context), api_call_source(name):
                    module = await asyncio.to_thread(
                        self._import_plugin,
                        name,
                        plugin_dir,
                        entry_path,
                    )
                handlers, on_load, on_unload, interceptors, filters, api_interceptors = _collect_pending()
                for registry in (handlers, interceptors, filters, api_interceptors):
                    for item in registry:
                        item['_file'] = _submodule_key(item['func'], name).removeprefix(f'{name}/')
                handlers = self._filter_disabled(name, handlers)
                interceptors = self._filter_disabled(name, interceptors)
                filters = self._filter_disabled(name, filters)
                api_interceptors = self._filter_disabled(name, api_interceptors)
                plugin = _finalize_plugin(
                    name,
                    plugin_dir,
                    module,
                    plugin_context,
                    handlers,
                    on_load,
                    on_unload,
                    interceptors,
                    filters,
                    api_interceptors,
                    started,
                )
                await _run_hooks(plugin.on_load_funcs, name, plugin_context)
                self._plugins[name] = plugin
                self._discovered_plugins.add(name)
                self._rebuild_handler_list()
                get_logger(PLUGIN, name).info(
                    'loaded (%d handlers, %.2fs)',
                    len(plugin.handlers),
                    plugin.load_time,
                )
            except Exception:
                self._drop_modules(name)
                raise
            finally:
                _clear_pending()

    def _filter_disabled(self, plugin_name: str, items: list[dict]) -> list[dict]:
        return [
            item
            for item in items
            if (_submodule_key(item['func'], plugin_name) or plugin_name)
            not in self._disabled_plugins
        ]

    async def reload(self, name: str) -> bool:
        await self.load(name)
        await asyncio.to_thread(self._scan_plugin_mtimes, os.path.join(self._dir, name))
        return True

    async def unload(self, name: str) -> bool:
        async with self._lock:
            if name not in self._plugins:
                return False
            await self._unload_plugin(name)
            self._rebuild_handler_list()
            return True

    async def _unload_plugin(self, name: str) -> None:
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return
        await _run_hooks(plugin.on_unload_funcs, name, plugin.ctx)
        from core.plugins.web_pages import clear_routes_by_owner

        clear_routes_by_owner(name)
        self._drop_modules(name)

    @staticmethod
    def _drop_modules(name: str) -> None:
        prefix = f'plugins.{name}'
        for module_name in tuple(sys.modules):
            if module_name == prefix or module_name.startswith(f'{prefix}.'):
                sys.modules.pop(module_name, None)

    @staticmethod
    def _import_plugin(name: str, plugin_dir: str, entry_path: str):
        if 'plugins' not in sys.modules:
            package = types.ModuleType('plugins')
            package.__path__ = [os.path.dirname(plugin_dir)]
            sys.modules['plugins'] = package

        module_name = f'plugins.{name}'
        spec = importlib.util.spec_from_file_location(
            module_name,
            entry_path,
            submodule_search_locations=[plugin_dir],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f'cannot create plugin module: {module_name}')
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module


def _finalize_plugin(
    name,
    plugin_dir,
    module,
    context,
    handlers,
    on_load,
    on_unload,
    interceptors,
    handler_filters,
    api_interceptors,
    started,
):
    plugin = PluginInfo(name, plugin_dir)
    plugin.module = module
    plugin.ctx = context
    plugin.handlers = handlers
    plugin.on_load_funcs = on_load
    plugin.on_unload_funcs = on_unload
    plugin.interceptors = interceptors
    plugin.handler_filters = handler_filters
    plugin.api_interceptors = api_interceptors
    plugin.load_time = time.perf_counter() - started
    plugin.meta = _read_plugin_meta(module)
    return plugin
