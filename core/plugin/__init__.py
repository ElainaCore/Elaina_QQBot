"""插件系统 — v2 异步架构"""

from core.plugin.decorators import (
    api_interceptor,
    handler,
    handler_filter,
    interceptor,
    on_load,
    on_unload,
)
from core.plugin.manager import PluginManager

__all__ = [
    'api_interceptor',
    'handler',
    'handler_filter',
    'interceptor',
    'on_load',
    'on_unload',
    'PluginManager',
]
