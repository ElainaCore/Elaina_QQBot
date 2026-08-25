"""仅支持异步函数的插件注册装饰器。"""

import contextvars
import inspect
import re
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass(slots=True)
class PluginRegistrations:
    handlers: list[dict] = field(default_factory=list)
    on_load: list[Callable] = field(default_factory=list)
    on_unload: list[Callable] = field(default_factory=list)
    interceptors: list[dict] = field(default_factory=list)
    handler_filters: list[dict] = field(default_factory=list)
    api_interceptors: list[dict] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(
            len(items)
            for items in (
                self.handlers,
                self.on_load,
                self.on_unload,
                self.interceptors,
                self.handler_filters,
                self.api_interceptors,
            )
        )

    def snapshot(self):
        return (
            list(self.handlers),
            list(self.on_load),
            list(self.on_unload),
            list(self.interceptors),
            list(self.handler_filters),
            list(self.api_interceptors),
        )


_registrations: contextvars.ContextVar[PluginRegistrations | None] = contextvars.ContextVar(
    'plugin_registrations',
    default=None,
)


@contextmanager
def registration_scope(registrations: PluginRegistrations | None = None):
    current = registrations or PluginRegistrations()
    token = _registrations.set(current)
    try:
        yield current
    finally:
        _registrations.reset(token)


def _current_registrations() -> PluginRegistrations:
    current = _registrations.get()
    if current is None:
        raise RuntimeError('插件装饰器只能在插件加载期间使用')
    return current


def _async_only(func: Callable, role: str) -> Callable:
    if not inspect.iscoroutinefunction(func):
        raise TypeError(f'{role} 必须使用 async def 定义: {func.__module__}.{func.__qualname__}')
    return func


def handler(
    pattern,
    *,
    name='',
    desc='',
    priority=0,
    owner_only=False,
    group_only=False,
    private_only=False,
    event_types=None,
    cooldown=0,
    block=False,
    fallback=False,
    timeout=30,
):
    """注册异步事件处理器。"""

    def decorator(func):
        _async_only(func, 'handler')
        _current_registrations().handlers.append(
            {
                'func': func,
                'pattern': pattern,
                'compiled': re.compile(pattern, re.DOTALL),
                'name': name or func.__name__,
                'desc': desc,
                'priority': priority,
                'owner_only': owner_only,
                'group_only': group_only,
                'private_only': private_only,
                'event_types': frozenset(event_types) if event_types else None,
                'cooldown': cooldown,
                'block': block,
                'fallback': fallback,
                'timeout': timeout,
            }
        )
        return func

    return decorator


def on_load(func):
    _current_registrations().on_load.append(_async_only(func, 'on_load'))
    return func


def on_unload(func):
    _current_registrations().on_unload.append(_async_only(func, 'on_unload'))
    return func


def interceptor(priority=100, *, timeout=30):
    def decorator(func):
        _current_registrations().interceptors.append(
            {'func': _async_only(func, 'interceptor'), 'priority': priority, 'timeout': timeout}
        )
        return func

    return decorator


def handler_filter(priority=100, *, timeout=30):
    def decorator(func):
        _current_registrations().handler_filters.append(
            {'func': _async_only(func, 'handler_filter'), 'priority': priority, 'timeout': timeout}
        )
        return func

    return decorator


def api_interceptor(priority=100, *, timeout=30):
    def decorator(func):
        _current_registrations().api_interceptors.append(
            {'func': _async_only(func, 'api_interceptor'), 'priority': priority, 'timeout': timeout}
        )
        return func

    return decorator
