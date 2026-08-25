"""插件运行上下文和已加载插件元数据。"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from pathlib import Path

from core.foundation.logging import PLUGIN, get_logger


class PluginContext:
    """单个插件拥有的路径和服务。"""

    __slots__ = ('name', 'plugin_dir', 'data_dir', 'log')

    def __init__(self, name: str, plugin_dir: str):
        self.name = name
        self.plugin_dir = os.path.abspath(plugin_dir)
        self.data_dir = os.path.join(self.plugin_dir, 'data')
        self.log = get_logger(PLUGIN, name)

    async def prepare(self) -> None:
        from core.services.files import ensure_dir

        await ensure_dir(self.data_dir)

    def get_data_path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    def get_resource_path(self, filename: str) -> str:
        return os.path.join(self.plugin_dir, filename)

    @property
    def root(self) -> Path:
        return Path(self.plugin_dir)

    @property
    def data(self) -> Path:
        return Path(self.data_dir)


_current_plugin: contextvars.ContextVar[PluginContext | None] = contextvars.ContextVar(
    'current_plugin',
    default=None,
)


def current_plugin() -> PluginContext:
    context = _current_plugin.get()
    if context is None:
        raise RuntimeError('只能在插件执行期间访问插件上下文')
    return context


@contextmanager
def plugin_scope(context: PluginContext):
    token = _current_plugin.set(context)
    try:
        yield context
    finally:
        _current_plugin.reset(token)


class PluginInfo:
    """已加载插件的运行状态。"""

    __slots__ = (
        'name',
        'plugin_dir',
        'module',
        'handlers',
        'on_load_funcs',
        'on_unload_funcs',
        'interceptors',
        'handler_filters',
        'api_interceptors',
        'enabled',
        'load_time',
        'error',
        'ctx',
        'meta',
    )

    def __init__(self, name: str, plugin_dir: str):
        self.name = name
        self.plugin_dir = plugin_dir
        self.module = None
        self.handlers = []
        self.on_load_funcs = []
        self.on_unload_funcs = []
        self.interceptors = []
        self.handler_filters = []
        self.api_interceptors = []
        self.enabled = True
        self.load_time = 0.0
        self.error = None
        self.ctx = None
        self.meta = {}
