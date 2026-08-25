"""以单一入口异步发现和加载插件。"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import os
import sys
import time
import types

from core.foundation.logging import PLUGIN, get_logger, report_error
from core.plugins.context import PluginContext, PluginInfo, plugin_scope
from core.plugins.decorators import (
    PluginRegistrations,
    registration_scope,
)
from core.protocols.onebot.api import api_call_source

log = get_logger(PLUGIN, '管理器')
_ENTRY_FILE = 'main.py'


async def _run_hooks(
    funcs,
    plugin_name: str,
    context: PluginContext,
    *,
    phase: str,
    continue_on_error: bool = False,
    timeout: float = 30,
) -> None:
    for func in funcs:
        try:
            with plugin_scope(context), api_call_source(plugin_name):
                if timeout <= 0:
                    await func()
                else:
                    async with asyncio.timeout(timeout):
                        await func()
        except Exception as error:
            if continue_on_error:
                report_error(
                    PLUGIN,
                    plugin_name,
                    error,
                    context={'phase': phase, 'hook': func.__qualname__},
                )
                continue
            raise RuntimeError(
                f'插件 [{plugin_name}] 的 {phase} 钩子 [{func.__qualname__}] 执行失败: {error}'
            ) from error


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
    """将每个插件作为以 main.py 为入口的独立包加载。"""

    async def load_all(self) -> None:
        if not self._configuration_loaded:
            await asyncio.gather(
                asyncio.to_thread(self._load_plugin_bots),
                asyncio.to_thread(self._load_disabled_plugins),
            )
            self._configuration_loaded = True
        names = await asyncio.to_thread(_discover_plugins, self._dir)
        self._discovered_plugins = set(names)
        loaded = skipped = failed = 0
        for name in names:
            if name in self._disabled_plugins:
                skipped += 1
                log.info('插件 [%s] 已禁用', name)
                continue
            try:
                await self.load(name)
                loaded += 1
            except Exception as error:
                failed += 1
                report_error(PLUGIN, name, error, context={'阶段': '加载'})
        self._rebuild_handler_list()
        await asyncio.to_thread(self._snapshot_all_mtimes)
        log.info(
            '插件加载完成: %d/%d（失败 %d，禁用 %d），共 %d 个处理器',
            loaded,
            len(names),
            failed,
            skipped,
            self.handler_count,
        )

    async def load(self, name: str) -> None:
        plugin_dir = os.path.join(self._dir, name)
        entry_path = os.path.join(plugin_dir, _ENTRY_FILE)
        if not os.path.isfile(entry_path):
            raise FileNotFoundError(f'插件入口不存在: {entry_path}')

        async with self._lock:
            old_plugin = self._plugins.get(name)
            from core.plugins.web_pages import (
                has_resources_by_owner,
                resource_registration_scope,
                restore_resources_by_owner,
                snapshot_resources_by_owner,
            )

            old_resources = snapshot_resources_by_owner(name)
            plugin_context = PluginContext(name, plugin_dir)
            await plugin_context.prepare()
            if old_plugin is not None:
                await asyncio.to_thread(self._clear_bytecode_cache, plugin_dir)
            old_modules = self._pop_modules(name)
            started = time.perf_counter()
            registrations = PluginRegistrations()
            plugin = None
            try:
                with (
                    plugin_scope(plugin_context),
                    registration_scope(registrations),
                    resource_registration_scope() as new_resources,
                    api_call_source(name),
                ):
                    module = await asyncio.to_thread(
                        self._import_plugin,
                        name,
                        plugin_dir,
                        entry_path,
                    )
                    if registrations.count == 0 and not has_resources_by_owner(name):
                        raise RuntimeError(
                            f'插件 [{name}] 没有注册任何能力；'
                            '请从公开的 core.plugins API 导入装饰器'
                        )
                    await _run_hooks(
                        list(registrations.on_load),
                        name,
                        plugin_context,
                        phase='on_load',
                    )
                handlers, on_load, on_unload, interceptors, filters, api_interceptors = registrations.snapshot()
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
                if old_plugin is not None:
                    plugin.enabled = old_plugin.enabled

                # 新版本加载成功后才卸载旧版本。切换期间保存两代模块和
                # Web 注册项，确保任何一步失败都能恢复原有可用版本。
                new_modules = self._pop_modules(name)
                if old_plugin is not None:
                    self._restore_modules(name, old_modules)
                    with resource_registration_scope():
                        await _run_hooks(
                            old_plugin.on_unload_funcs,
                            name,
                            old_plugin.ctx,
                            phase='on_unload',
                            continue_on_error=True,
                        )
                    self._drop_modules(name)
                self._restore_modules(name, new_modules)
                restore_resources_by_owner(name, new_resources)
                self._plugins[name] = plugin
                self._discovered_plugins.add(name)
                self._rebuild_handler_list()
                log.info(
                    '插件 [%s] 已加载（%d 个处理器，%d 个拦截器，%.2f 秒）',
                    name,
                    len(plugin.handlers),
                    len(plugin.interceptors),
                    plugin.load_time,
                )
            except Exception as error:
                with resource_registration_scope():
                    await _run_hooks(
                        list(registrations.on_unload),
                        name,
                        plugin_context,
                        phase='rollback',
                        continue_on_error=True,
                    )
                self._drop_modules(name)
                self._restore_modules(name, old_modules)
                restore_resources_by_owner(name, old_resources)
                if plugin is not None and self._plugins.get(name) is plugin:
                    if old_plugin is None:
                        self._plugins.pop(name, None)
                    else:
                        self._plugins[name] = old_plugin
                    self._rebuild_handler_list()
                if isinstance(error, RuntimeError) and str(error).startswith(f'插件 [{name}]'):
                    raise
                raise RuntimeError(f'插件 [{name}] 加载失败: {error}') from error

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
        await _run_hooks(
            plugin.on_unload_funcs,
            name,
            plugin.ctx,
            phase='on_unload',
            continue_on_error=True,
        )
        from core.plugins.web_pages import clear_resources_by_owner

        clear_resources_by_owner(name)
        self._drop_modules(name)

    @staticmethod
    def _drop_modules(name: str) -> None:
        _LoaderMixin._pop_modules(name)

    @staticmethod
    def _pop_modules(name: str) -> dict[str, types.ModuleType]:
        prefix = f'plugins.{name}'
        removed = {}
        for module_name in tuple(sys.modules):
            if module_name == prefix or module_name.startswith(f'{prefix}.'):
                removed[module_name] = sys.modules.pop(module_name)
        package = sys.modules.get('plugins')
        if package is not None:
            package.__dict__.pop(name, None)
        return removed

    @staticmethod
    def _restore_modules(name: str, modules: dict[str, types.ModuleType]) -> None:
        if not modules:
            return
        sys.modules.update(modules)
        package = sys.modules.get('plugins')
        root = modules.get(f'plugins.{name}')
        if package is not None and root is not None:
            setattr(package, name, root)

    @staticmethod
    def _clear_bytecode_cache(plugin_dir: str) -> None:
        for root, dirs, files in os.walk(plugin_dir):
            dirs[:] = [item for item in dirs if item != '__pycache__' and not item.startswith('.')]
            for filename in files:
                if not filename.endswith('.py'):
                    continue
                with contextlib.suppress(OSError):
                    os.remove(importlib.util.cache_from_source(os.path.join(root, filename)))

    @staticmethod
    def _import_plugin(name: str, plugin_dir: str, entry_path: str):
        package_root = os.path.dirname(plugin_dir)
        package = sys.modules.get('plugins')
        if package is None:
            package = types.ModuleType('plugins')
            sys.modules['plugins'] = package
        package.__path__ = [package_root]

        module_name = f'plugins.{name}'
        spec = importlib.util.spec_from_file_location(
            module_name,
            entry_path,
            submodule_search_locations=[plugin_dir],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f'无法创建插件模块: {module_name}')
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
