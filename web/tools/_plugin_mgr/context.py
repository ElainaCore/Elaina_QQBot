"""插件管理处理器共享的运行时上下文。"""

import os

from aiohttp import web

from core.foundation.archives import is_within

_app = None
_base_dir = ''


def set_context(app_instance, base_dir: str) -> None:
    global _app, _base_dir
    _app = app_instance
    _base_dir = base_dir


def get_pm():
    return getattr(_app, 'plugin_manager', None) if _app else None


def get_mm():
    return getattr(_app, 'module_manager', None) if _app else None


def plugins_dir() -> str:
    return os.path.join(_base_dir, 'plugins')


def modules_dir() -> str:
    return os.path.join(_base_dir, 'modules')


def validate_path(rel_or_abs, root):
    root_abs = os.path.abspath(root)
    candidate = rel_or_abs
    if not os.path.isabs(candidate):
        candidate = (
            os.path.join(root, candidate)
            if not candidate.startswith(os.path.basename(root))
            else os.path.join(_base_dir, candidate)
        )
    absolute_path = os.path.abspath(candidate)
    if not is_within(root_abs, absolute_path):
        return False, ''
    return True, absolute_path


def validate_config_path(rel_or_abs):
    for root in (plugins_dir(), modules_dir()):
        valid, absolute_path = validate_path(rel_or_abs, root)
        if valid:
            return absolute_path, None
    return '', web.json_response({'success': False, 'message': '无效路径'}, status=403)


def detect_config_format(extension):
    if extension in ('.yaml', '.yml'):
        return 'yaml'
    if extension == '.json':
        return 'json'
    return 'raw'
