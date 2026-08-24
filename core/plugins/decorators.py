"""Strictly asynchronous plugin registration decorators."""

import inspect
import re
from collections.abc import Callable

_pending_handlers: list[dict] = []
_pending_on_load: list[Callable] = []
_pending_on_unload: list[Callable] = []
_pending_interceptors: list[dict] = []
_pending_handler_filters: list[dict] = []
_pending_api_interceptors: list[dict] = []


def _async_only(func: Callable, role: str) -> Callable:
    if not inspect.iscoroutinefunction(func):
        raise TypeError(f'{role} must use async def: {func.__module__}.{func.__qualname__}')
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
):
    """Register an asynchronous event handler."""

    def decorator(func):
        _async_only(func, 'handler')
        _pending_handlers.append(
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
            }
        )
        return func

    return decorator


def on_load(func):
    _pending_on_load.append(_async_only(func, 'on_load'))
    return func


def on_unload(func):
    _pending_on_unload.append(_async_only(func, 'on_unload'))
    return func


def interceptor(priority=100):
    def decorator(func):
        _pending_interceptors.append({'func': _async_only(func, 'interceptor'), 'priority': priority})
        return func

    return decorator


def handler_filter(priority=100):
    def decorator(func):
        _pending_handler_filters.append({'func': _async_only(func, 'handler_filter'), 'priority': priority})
        return func

    return decorator


def api_interceptor(priority=100):
    def decorator(func):
        _pending_api_interceptors.append({'func': _async_only(func, 'api_interceptor'), 'priority': priority})
        return func

    return decorator
