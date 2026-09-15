"""OneBot 调用上下文与路由状态。"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

_main_loop = None
_adapter_ref = None
_routed_self_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'onebot_self_id', default=None,
)
_api_source: contextvars.ContextVar[tuple[str, dict[str, Any]]] = contextvars.ContextVar(
    'onebot_api_source', default=('', {}),
)
_skip_api_interceptors: contextvars.ContextVar[bool] = contextvars.ContextVar(
    'skip_onebot_api_interceptors', default=False,
)
_api_interceptors: tuple[dict, ...] = ()


@dataclass(slots=True)
class ApiCallRequest:
    """传给插件出站 API 中间件的调用对象。"""

    action: str
    params: dict
    self_id: str | None
    source_plugin: str = ''
    context: dict[str, Any] = field(default_factory=dict)
    local: bool = False


def set_api_interceptors(interceptors) -> None:
    """更新出站 API 中间件快照。"""
    global _api_interceptors
    _api_interceptors = tuple(interceptors or ())


def api_interceptors() -> tuple[dict, ...]:
    """返回当前出站 API 中间件。"""
    return _api_interceptors


@contextmanager
def api_call_source(plugin_name: str, event=None):
    """记录当前插件和事件上下文。"""
    values = {}
    if event is not None:
        for key in ('self_id', 'user_id', 'group_id', 'message_type', 'post_type'):
            value = getattr(event, key, None)
            if value is not None:
                values[key] = value
    token = _api_source.set((str(plugin_name or ''), values))
    try:
        yield
    finally:
        _api_source.reset(token)


def current_source() -> tuple[str, dict[str, Any]]:
    """返回当前插件和事件上下文。"""
    return _api_source.get()


@contextmanager
def bypass_api_interceptors():
    """跳过出站 API 中间件。"""
    token = _skip_api_interceptors.set(True)
    try:
        yield
    finally:
        _skip_api_interceptors.reset(token)


def interceptors_bypassed() -> bool:
    """判断当前调用是否跳过中间件。"""
    return _skip_api_interceptors.get()


@contextmanager
def routed_self_id(self_id: str | None):
    """固定当前调用的目标账号。"""
    if self_id is None:
        yield
        return
    token = _routed_self_id.set(str(self_id))
    try:
        yield
    finally:
        _routed_self_id.reset(token)


def current_self_id() -> str | None:
    """返回当前路由账号。"""
    return _routed_self_id.get()


def set_main_loop(loop) -> None:
    """保存框架主事件循环。"""
    global _main_loop
    _main_loop = loop


def set_adapter(adapter) -> None:
    """保存全局 OneBot 适配器。"""
    global _adapter_ref
    _adapter_ref = adapter


def get_adapter():
    """返回全局 OneBot 适配器。"""
    return _adapter_ref
