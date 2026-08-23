"""插件上下文与数据模型"""

import os

from core.base.logger import PLUGIN, get_logger

# 当前正在加载的插件上下文 (由 PluginManager 在加载期间赋值)
ctx = None


class PluginContext:
    """插件上下文 — 提供 data/ 读写能力"""

    __slots__ = ('name', 'plugin_dir', 'data_dir', 'log')

    def __init__(self, name, plugin_dir):
        self.name = name
        self.plugin_dir = plugin_dir
        self.data_dir = os.path.join(plugin_dir, 'data')
        self.log = get_logger(PLUGIN, name)
        os.makedirs(self.data_dir, exist_ok=True)

    def get_data_path(self, filename):
        return os.path.join(self.data_dir, filename)

    def get_resource_path(self, filename):
        return os.path.join(self.plugin_dir, filename)


class PluginInfo:
    """已加载插件的信息"""

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
        'is_large',
        'meta',
    )

    def __init__(self, name, plugin_dir):
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
        self.load_time = 0
        self.error = None
        self.ctx = None
        self.is_large = False
        self.meta = {}
