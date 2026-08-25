"""Hook 系统 — emit(广播) / pipeline(管道)"""

import inspect
from collections import defaultdict

from core.foundation.logging import FRAMEWORK, get_logger

log = get_logger(FRAMEWORK, 'Hook')


class HookManager:
    """通用 Hook 管理器"""

    __slots__ = ('_hooks', '_sorted')

    def __init__(self):
        self._hooks = defaultdict(list)
        self._sorted = {}

    def register(self, hook_name, callback, *, owner='unknown', priority=100):
        """注册 hook 回调"""
        if not inspect.iscoroutinefunction(callback):
            raise TypeError(f'钩子必须使用 async def 定义: {callback.__module__}.{callback.__qualname__}')
        self._hooks[hook_name].append((priority, owner, callback))
        self._sorted.pop(hook_name, None)

    def unregister(self, hook_name, callback):
        """注销单个回调"""
        entries = self._hooks.get(hook_name)
        if not entries:
            return
        self._hooks[hook_name] = [e for e in entries if e[2] is not callback]
        self._sorted.pop(hook_name, None)

    def unregister_owner(self, owner):
        """注销某个 owner 的所有 hook"""
        for name in list(self._hooks):
            orig = self._hooks[name]
            filtered = [e for e in orig if e[1] != owner]
            if len(filtered) == len(orig):
                continue
            self._sorted.pop(name, None)
            if filtered:
                self._hooks[name] = filtered
            else:
                del self._hooks[name]

    def _get_sorted(self, hook_name):
        cached = self._sorted.get(hook_name)
        if cached is not None:
            return cached
        result = sorted(self._hooks.get(hook_name, []), key=lambda x: x[0])
        self._sorted[hook_name] = result
        return result

    async def emit(self, hook_name, *args, **kwargs):
        """广播执行"""
        for _, owner, callback in self._get_sorted(hook_name):
            try:
                await callback(*args, **kwargs)
            except Exception as e:
                log.warning(f"[{owner}] 钩子 '{hook_name}' 执行失败: {e}")

    async def pipeline(self, hook_name, data):
        """管道执行"""
        if data is None:
            return None
        for _, owner, callback in self._get_sorted(hook_name):
            try:
                data = await callback(data)
                if data is None:
                    return None
            except Exception as e:
                log.warning(f"[{owner}] 钩子 '{hook_name}' 执行失败: {e}")
        return data

    def has(self, hook_name):
        return bool(self._hooks.get(hook_name))

    def list_hooks(self):
        return {name: [{'owner': e[1], 'priority': e[0]} for e in self._get_sorted(name)] for name in self._hooks if self._hooks[name]}

    def clear(self):
        self._hooks.clear()
        self._sorted.clear()


_instance = None


def bind_hook_manager(manager):
    """由应用装配层绑定共享的 Hook 管理器。"""
    global _instance
    _instance = manager


def get_hook_manager():
    global _instance
    if _instance is None:
        _instance = HookManager()
    return _instance
