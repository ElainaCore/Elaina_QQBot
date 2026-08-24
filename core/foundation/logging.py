"""日志系统"""

import contextlib
import logging
import sys
from collections.abc import Callable
from typing import Any

from core.foundation.branding import PRODUCT_NAME, public_text

SYSTEM = 'system'
FRAMEWORK = 'framework'
EXTENSION = 'extension'
PLUGIN = 'plugin'

_FW_NAME = PRODUCT_NAME


class _PublicNameFilter(logging.Filter):
    """避免面向用户的日志暴露底层依赖实现名称。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = public_text(record.getMessage())
        record.args = ()
        return True


class _PublicNameFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return public_text(super().format(record))


def setup(framework_name: str = PRODUCT_NAME, level: int = logging.INFO):
    """初始化日志系统"""
    global _FW_NAME
    _FW_NAME = framework_name

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    formatter = _PublicNameFormatter(f'[{framework_name}] %(asctime)s - %(levelname)s - %(message)s', datefmt='%m-%d %H:%M:%S')
    # Windows 默认控制台可能仍使用 GBK，遇到插件日志中的非 ASCII 字符会触发
    # logging 内部异常。优先切换为 UTF-8，无法切换时使用可替代错误策略。
    stream = sys.stdout
    with contextlib.suppress(AttributeError, OSError, ValueError):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            reconfigure(encoding='utf-8', errors='backslashreplace')
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.addFilter(_PublicNameFilter())
    root.setLevel(level)
    root.addHandler(handler)

    for name in ('werkzeug', 'socketio', 'engineio', 'urllib3', 'uvicorn.access', 'aiohttp.access'):
        logging.getLogger(name).setLevel(logging.ERROR)


def get_logger(module_type: str = '', name: str = '') -> logging.Logger:
    """获取命名日志器"""
    parts = [_FW_NAME]
    if module_type:
        parts.append(module_type)
    if name:
        parts.append(name)
    return logging.getLogger('.'.join(parts))


# 错误回调
_error_callbacks: list[Callable[[dict[str, Any]], Any]] = []


def on_error(callback):
    """注册全局错误回调"""
    _error_callbacks.append(callback)


def report_error(module_type: str, name: str, error: Exception, context: dict | None = None):
    """报告错误 (context 为可选的附加调试信息)"""
    import datetime
    import traceback

    log = get_logger(module_type, name)
    public_error = public_text(error)
    public_traceback = public_text(traceback.format_exc())
    log.error(public_error)
    data: dict[str, Any] = {
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'module_type': module_type,
        'module_name': name,
        'content': public_error,
        'traceback': public_traceback,
    }
    if context:
        data['context'] = context
    for cb in _error_callbacks:
        with contextlib.suppress(Exception):
            cb(data)
