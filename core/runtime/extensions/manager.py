"""拓展模块管理器 — 自动发现、依赖安装、启停管理"""

import ast
import asyncio
import importlib.util
import inspect
import json
import os
import sys

from core.foundation.context import BaseContext
from core.foundation.logging import EXTENSION, get_logger, report_error
from core.runtime.extensions.hook import get_hook_manager
from core.services.files import write_json

log = get_logger(EXTENSION, '管理器')


def _async_lifecycle(module, name):
    callback = getattr(module, name, None)
    if callback is not None and not inspect.iscoroutinefunction(callback):
        raise TypeError(f'模块生命周期函数 {name} 必须使用 async def 定义: {module.__name__}')
    return callback


_DEFAULT_MANIFEST = {
    'name': '',
    'description': '',
    'version': '1.0.0',
    'author': '',
}
_LIFECYCLE_TIMEOUT = 30.0


async def _run_lifecycle(callback, *args):
    if callback is None:
        return None
    async with asyncio.timeout(_LIFECYCLE_TIMEOUT):
        return await callback(*args)


class ModuleContext(BaseContext):
    """模块上下文"""

    __slots__ = ('_hooks',)

    def __init__(self, name, module_dir, hook_manager):
        super().__init__(name, module_dir, EXTENSION)
        self._hooks = hook_manager

    @property
    def module_dir(self):
        return self._root_dir

    def hook(self, hook_name, *, priority=100, timeout=None):
        def decorator(func):
            self._hooks.register(hook_name, func, owner=self.name, priority=priority, timeout=timeout)
            return func

        return decorator

    def register_hook(self, hook_name, callback, *, priority=100, timeout=None):
        self._hooks.register(hook_name, callback, owner=self.name, priority=priority, timeout=timeout)

    async def emit(self, hook_name, *args, **kwargs):
        await self._hooks.emit(hook_name, *args, **kwargs)

    async def pipeline(self, hook_name, data):
        return await self._hooks.pipeline(hook_name, data)


class ModuleInfo:
    """已发现模块的信息"""

    __slots__ = (
        'name',
        'display_name',
        'description',
        'module_dir',
        'module',
        'version',
        'author',
        'instance',
        'ctx',
        'error',
    )

    def __init__(self, name, module_dir):
        self.name = name
        self.module_dir = module_dir
        self.display_name = name
        self.description = ''
        self.version = '1.0.0'
        self.author = ''
        self.module = None
        self.instance = None
        self.ctx = None
        self.error = None


class ModuleManager:
    """拓展模块管理器"""

    def __init__(self, modules_dir=None, hook_manager=None):
        if modules_dir:
            self._dir = os.path.abspath(modules_dir)
        else:
            self._dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'modules')
        self._hook_manager = hook_manager or get_hook_manager()
        self._modules = {}
        self._lock = asyncio.Lock()
        self._enabled_file = os.path.join(self._dir, 'modules_enabled.json')
        self._enabled_map = {}

    async def discover(self):
        """扫描 modules/ 下所有模块目录"""
        await asyncio.to_thread(self._discover_sync)

    def _discover_sync(self):
        self._enabled_map = self._load_enabled_map()
        if not os.path.isdir(self._dir):
            os.makedirs(self._dir, exist_ok=True)
            return
        for name in sorted(os.listdir(self._dir)):
            mod_dir = os.path.join(self._dir, name)
            if not os.path.isdir(mod_dir) or name.startswith('_'):
                continue
            if not self._find_entry(mod_dir):
                continue
            info = ModuleInfo(name, mod_dir)
            meta = self._read_manifest(mod_dir)
            info.display_name = meta.get('name') or name
            for key in ('description', 'version', 'author'):
                val = meta.get(key)
                if val is not None:
                    setattr(info, key, str(val))
            self._modules[name] = info
        log.info(f'发现 {len(self._modules)} 个模块: {", ".join(f"{n}@{m.version}" for n, m in self._modules.items()) or "(无)"}')

    def _load_enabled_map(self):
        if not os.path.isfile(self._enabled_file):
            return {}
        try:
            with open(self._enabled_file, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def _save_enabled_map(self):
        try:
            await write_json(self._enabled_file, self._enabled_map)
        except Exception as e:
            log.warning(f'保存模块开关状态失败: {e}')

    def is_module_enabled_persist(self, name):
        return self._enabled_map.get(name, False)

    async def set_module_enabled_persist(self, name, enabled):
        self._enabled_map[name] = bool(enabled)
        await self._save_enabled_map()

    async def start_enabled(self):
        """启动已启用的模块"""
        to_start = [n for n in self._modules if self.is_module_enabled_persist(n)]
        if not to_start:
            return
        for name in to_start:
            try:
                await self.enable(name, _persist=False)
            except Exception as e:
                report_error(EXTENSION, name, e)

    async def enable(self, name, _persist=True):
        """启用模块"""
        async with self._lock:
            info = self._modules.get(name)
            if not info:
                log.warning(f'模块不存在: {name}')
                return False
            if info.instance is not None:
                return True
            try:
                ctx = ModuleContext(info.display_name or name, info.module_dir, self._hook_manager)
                info.ctx = ctx
                module = await asyncio.to_thread(self._import_module, name, info.module_dir)
                info.module = module
                setup_fn = _async_lifecycle(module, 'setup')
                result = await _run_lifecycle(setup_fn, ctx)
                info.instance = result if result is not None else True
                info.error = None
                if _persist:
                    await self.set_module_enabled_persist(name, True)
                log.info(f'模块已启用: {info.display_name}@{info.version}')
                return True
            except Exception as e:
                self._hook_manager.unregister_owner(info.display_name or name)
                info.instance = info.ctx = info.module = None
                sys.modules.pop(f'modules.{name}', None)
                info.error = str(e)
                report_error(EXTENSION, name, e)
                return False

    async def disable(self, name, _persist=True):
        """禁用模块"""
        async with self._lock:
            info = self._modules.get(name)
            if not info or info.instance is None:
                if _persist:
                    await self.set_module_enabled_persist(name, False)
                return False
            try:
                teardown_fn = _async_lifecycle(info.module, 'teardown')
                if teardown_fn:
                    await _run_lifecycle(teardown_fn)
            except Exception as e:
                report_error(EXTENSION, name, e)
            self._hook_manager.unregister_owner(info.display_name or name)
            info.instance = info.ctx = None
            sys.modules.pop(f'modules.{name}', None)
            if _persist:
                await self.set_module_enabled_persist(name, False)
            log.info(f'模块已禁用: {info.display_name}')
            return True

    async def reload(self, name):
        """重载模块"""
        info = self._modules.get(name)
        if not info:
            return False
        was_enabled = info.instance is not None
        if was_enabled:
            await self.disable(name, _persist=False)
        return await self.enable(name, _persist=False)

    def get(self, name):
        info = self._modules.get(name)
        return info.instance if info and info.instance is not None else None

    def is_enabled(self, name):
        info = self._modules.get(name)
        return info.instance is not None if info else False

    def list_modules(self):
        return [
            {
                'name': i.name,
                'display_name': i.display_name,
                'description': i.description,
                'version': i.version,
                'author': i.author,
                'enabled': i.instance is not None,
                'persist_enabled': self.is_module_enabled_persist(i.name),
                'error': i.error,
            }
            for i in self._modules.values()
        ]

    @staticmethod
    def _find_entry(mod_dir):
        path = os.path.join(mod_dir, 'main.py')
        return path if os.path.isfile(path) else None

    @staticmethod
    def _import_module(name, mod_dir):
        entry = os.path.join(mod_dir, 'main.py')
        if not os.path.isfile(entry):
            raise FileNotFoundError(f'模块入口不存在: {mod_dir}')
        mod_name = f'modules.{name}'
        spec = importlib.util.spec_from_file_location(mod_name, entry, submodule_search_locations=[mod_dir])
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _read_manifest(mod_dir):
        entry = os.path.join(mod_dir, 'main.py')
        if not os.path.isfile(entry):
            return dict(_DEFAULT_MANIFEST)
        try:
            with open(entry, encoding='utf-8') as f:
                tree = ast.parse(f.read())
            for node in ast.iter_child_nodes(tree):
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == '__module_meta__'
                ):
                    return ast.literal_eval(node.value)
        except Exception:
            pass
        return dict(_DEFAULT_MANIFEST)

    async def shutdown(self):
        """关闭所有已启用模块"""
        for name in [n for n, i in self._modules.items() if i.instance is not None]:
            await self.disable(name, _persist=False)
