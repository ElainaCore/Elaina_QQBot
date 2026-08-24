"""Public API for asynchronous plugins."""

from core.foundation.config import cfg as config
from core.foundation.logging import PLUGIN, get_logger, report_error
from core.plugins.context import PluginContext, current_plugin
from core.plugins.decorators import (
    api_interceptor,
    handler,
    handler_filter,
    interceptor,
    on_load,
    on_unload,
)
from core.plugins.web_pages import (
    register_page,
    register_route,
    unregister_page,
    unregister_route,
)
from core.protocols.onebot.api import (
    ApiCallRequest,
    OneBotAPI,
    bypass_api_interceptors,
    get_api,
)
from core.services.files import (
    ensure_dir,
    read_json,
    read_text,
    run_sync,
    write_json,
    write_text,
)


def get_app():
    from core.runtime.application import get_app as resolve_application

    return resolve_application()


__all__ = [
    'ApiCallRequest',
    'OneBotAPI',
    'PLUGIN',
    'PluginContext',
    'api_interceptor',
    'bypass_api_interceptors',
    'config',
    'current_plugin',
    'ensure_dir',
    'get_api',
    'get_app',
    'get_logger',
    'handler',
    'handler_filter',
    'interceptor',
    'on_load',
    'on_unload',
    'read_json',
    'read_text',
    'report_error',
    'register_page',
    'register_route',
    'run_sync',
    'unregister_page',
    'unregister_route',
    'write_json',
    'write_text',
]
