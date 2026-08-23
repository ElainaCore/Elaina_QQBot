"""插件的发现、加载、卸载与模块清理。"""

import asyncio
import importlib
import importlib.util
import os
import sys
import time

import core.plugin.context as _ctx_mod
from core.base.logger import PLUGIN, get_logger, report_error
from core.plugin.context import PluginContext, PluginInfo
from core.plugin.decorators import (
    _pending_api_interceptors,
    _pending_handler_filters,
    _pending_handlers,
    _pending_interceptors,
    _pending_on_load,
    _pending_on_unload,
)

log = get_logger(PLUGIN, '管理器')

_ENTRY_NAMES = frozenset({'index.py', 'app.py', 'main.py'})


def _clear_pending():
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


async def _run_hooks(funcs, name):
    for func, is_coro in funcs:
        try:
            await func() if is_coro else await asyncio.to_thread(func)
        except Exception as e:
            report_error(PLUGIN, name, e)


def _sub_key(func, plugin_name, prefix):
    """从处理器所属模块生成可持久化的子模块禁用键。"""
    mod = getattr(func, '__module__', '') or ''
    if mod.startswith(prefix):
        return f'{plugin_name}/{mod[len(prefix) :].replace(".", "/")}'
    return ''


def _read_plugin_meta(module):
    if module is None:
        return {}
    raw = getattr(module, '__plugin_meta__', None)
    if not isinstance(raw, dict):
        return {}
    allowed = {'name', 'author', 'description', 'version', 'github', 'homepage', 'license'}
    return {k: str(v) for k, v in raw.items() if k in allowed and v}


class _LoaderMixin:
    """插件加载/卸载/导入逻辑"""

    async def load_all(self):
        if not os.path.isdir(self._dir):
            os.makedirs(self._dir, exist_ok=True)
            log.warning(f'插件目录为空: {self._dir}')
            return
        dirs = sorted(d for d in os.listdir(self._dir) if os.path.isdir(os.path.join(self._dir, d)) and not d.startswith(('_', '.')))
        loaded = skipped = large = 0
        for name in dirs:
            try:
                entry = self._find_large_entry(os.path.join(self._dir, name))
                # 同时支持按插件目录和入口文件禁用。
                entry_key = f'{name}/{os.path.basename(entry)[:-3]}' if entry else ''
                if name in self._disabled_plugins or (entry_key and entry_key in self._disabled_plugins):
                    log.info(f'插件 [{name}] 已禁用, 跳过')
                    skipped += 1
                    continue
                if entry:
                    await self._load_large(name)
                    large += 1
                else:
                    if not self._list_py_files(os.path.join(self._dir, name)):
                        continue
                    await self.load(name)
                loaded += 1
            except Exception as e:
                report_error(PLUGIN, name, e)
        self._rebuild_handler_list()
        self._snapshot_all_mtimes()
        log.info(f'插件加载完成: {loaded}/{len(dirs)} 个 (大型 {large}, 跳过 {skipped}), 共 {self.handler_count} 个处理器')

    async def load(self, name):
        plugin_dir = os.path.join(self._dir, name)
        if not os.path.isdir(plugin_dir):
            get_logger(PLUGIN, name).error(f'[{name}] 插件目录不存在: {plugin_dir}')
            return
        py_files = self._list_py_files(plugin_dir)
        py_files = [p for p in py_files if f'{name}/{os.path.basename(p)[:-3]}' not in self._disabled_plugins]
        if not py_files:
            get_logger(PLUGIN, name).error(f'[{name}] 目录中无可用 .py 文件: {plugin_dir}')
            return
        async with self._lock:
            if name in self._plugins:
                await self._unload_plugin(name)
            plugin_ctx = PluginContext(name, plugin_dir)
            _ctx_mod.ctx = plugin_ctx
            start = time.perf_counter()
            all_h, all_load, all_unload, all_ic, all_hf, all_api_ic = [], [], [], [], [], []
            first_module = None
            failed_files = []
            try:
                for py_path in py_files:
                    _clear_pending()
                    fname = os.path.basename(py_path)[:-3]
                    mod_name = f'plugins.{name}.{fname}'
                    try:
                        spec = importlib.util.spec_from_file_location(mod_name, py_path, submodule_search_locations=[plugin_dir])
                        if spec is None or spec.loader is None:
                            raise ImportError(f'无法创建插件模块: {mod_name}')
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[mod_name] = module
                        spec.loader.exec_module(module)
                        if first_module is None:
                            first_module = module
                        h, lo, ul, ic, hf, api_ic = _collect_pending()
                        for item in h:
                            item['_file'] = fname
                        for item in ic:
                            item['_file'] = fname
                        for item in hf:
                            item['_file'] = fname
                        for item in api_ic:
                            item['_file'] = fname
                        all_h.extend(h)
                        all_load.extend(lo)
                        all_unload.extend(ul)
                        all_ic.extend(ic)
                        all_hf.extend(hf)
                        all_api_ic.extend(api_ic)
                    except Exception as e:
                        failed_files.append(fname)
                        sys.modules.pop(mod_name, None)
                        report_error(PLUGIN, f'{name}/{fname}', e)
                error = ''
                if failed_files:
                    error = f'部分文件导入失败: {", ".join(failed_files)}'
                elif not all_h and py_files:
                    error = '未注册任何处理器'
                plugin = _finalize_plugin(
                    name,
                    plugin_dir,
                    first_module,
                    plugin_ctx,
                    all_h,
                    all_load,
                    all_unload,
                    all_ic,
                    all_hf,
                    all_api_ic,
                    start,
                    error=error,
                )
                await _run_hooks(plugin.on_load_funcs, name)
                self._plugins[name] = plugin
                get_logger(PLUGIN, name).info(f'加载完成 ({len(py_files)} 个文件, {len(plugin.handlers)} 个处理器, {plugin.load_time:.2f}s)')
            finally:
                _clear_pending()
                _ctx_mod.ctx = None

    async def _load_large(self, name):
        plugin_dir = os.path.join(self._dir, name)
        entry = self._find_large_entry(plugin_dir)
        if not entry:
            return
        async with self._lock:
            if name in self._plugins:
                await self._unload_plugin(name)
            _clear_pending()
            plugin_ctx = PluginContext(name, plugin_dir)
            _ctx_mod.ctx = plugin_ctx
            start = time.perf_counter()
            try:
                module = self._import_plugin(name, plugin_dir, entry)
                h, lo, ul, ic, hf, api_ic = _collect_pending()
                # 根据子模块禁用配置过滤处理器。
                prefix = f'plugins.{name}.'
                h = [x for x in h if _sub_key(x['func'], name, prefix) not in self._disabled_plugins]
                ic = [x for x in ic if _sub_key(x['func'], name, prefix) not in self._disabled_plugins]
                hf = [x for x in hf if _sub_key(x['func'], name, prefix) not in self._disabled_plugins]
                api_ic = [x for x in api_ic if _sub_key(x['func'], name, prefix) not in self._disabled_plugins]
                plugin = _finalize_plugin(name, plugin_dir, module, plugin_ctx, h, lo, ul, ic, hf, api_ic, start, is_large=True)
                await _run_hooks(plugin.on_load_funcs, name)
                self._plugins[name] = plugin
                get_logger(PLUGIN, name).info(f'大型插件加载完成 ({len(h)} 个处理器, {plugin.load_time:.2f}s)')
            except Exception:
                sys.modules.pop(f'plugins.{name}', None)
                raise
            finally:
                _clear_pending()
                _ctx_mod.ctx = None

    async def reload(self, name):
        is_large = bool(self._find_large_entry(os.path.join(self._dir, name)))
        await (self._load_large(name) if is_large else self.load(name))
        self._rebuild_handler_list()
        pdir = os.path.join(self._dir, name)
        if os.path.isdir(pdir):
            self._scan_plugin_mtimes(pdir)
        info = self._plugins.get(name)
        log.info(f'🔄 插件热重载: {name} ({len(info.handlers) if info else 0} 个处理器)' if info else f'🔄 插件热重载: {name}')
        return True

    async def unload(self, name):
        async with self._lock:
            if name not in self._plugins:
                return False
            await self._unload_plugin(name)
            self._rebuild_handler_list()
            return True

    async def _unload_plugin(self, name):
        plugin = self._plugins.pop(name, None)
        if not plugin:
            return
        await _run_hooks(plugin.on_unload_funcs, name)
        try:
            from core.plugin.web_pages import clear_routes_by_owner

            clear_routes_by_owner(name)
        except Exception:
            pass
        prefix = f'plugins.{name}'
        for k in [k for k in sys.modules if k == prefix or k.startswith(prefix + '.')]:
            sys.modules.pop(k, None)

    # ==================== 发现与导入 ====================

    @staticmethod
    def _list_py_files(plugin_dir):
        return sorted(os.path.join(plugin_dir, f) for f in os.listdir(plugin_dir) if f.endswith('.py') and not f.startswith('_') and f not in _ENTRY_NAMES)

    @staticmethod
    def _find_large_entry(plugin_dir):
        for c in ('index.py', 'app.py', 'main.py'):
            p = os.path.join(plugin_dir, c)
            if os.path.isfile(p):
                return p
        return None

    @classmethod
    def _import_plugin(cls, name, plugin_dir, entry_path):
        mod_name = f'plugins.{name}'
        # 确保顶层插件包存在。
        if 'plugins' not in sys.modules:
            import types

            plugins_pkg = types.ModuleType('plugins')
            plugins_pkg.__path__ = [os.path.dirname(plugin_dir)]
            sys.modules['plugins'] = plugins_pkg

        spec = importlib.util.spec_from_file_location(mod_name, entry_path, submodule_search_locations=[plugin_dir])
        if spec is None or spec.loader is None:
            raise ImportError(f'无法创建插件模块: {mod_name}')
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module


def _finalize_plugin(
    name,
    plugin_dir,
    module,
    ctx,
    handlers,
    on_load,
    on_unload,
    interceptors,
    handler_filters,
    api_interceptors,
    start,
    *,
    is_large=False,
    error='',
):
    plugin = PluginInfo(name, plugin_dir)
    plugin.module, plugin.ctx = module, ctx
    plugin.handlers, plugin.on_load_funcs = handlers, on_load
    plugin.on_unload_funcs, plugin.interceptors = on_unload, interceptors
    plugin.handler_filters = handler_filters
    plugin.api_interceptors = api_interceptors
    plugin.is_large, plugin.load_time = is_large, time.perf_counter() - start
    plugin.meta = _read_plugin_meta(module)
    if error:
        plugin.error = error
    return plugin
