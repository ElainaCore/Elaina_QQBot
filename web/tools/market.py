"""插件市场 — 门面 (复用 _market 包)"""

from web.tools._market import shared as _shared
from web.tools._market.install import (
    handle_market_install,
    handle_market_preview,
    handle_market_uninstall,
)
from web.tools._market.install import (
    set_context as set_install_context,
)
from web.tools._market.local import (
    handle_local_plugin_read,
    handle_local_plugin_save,
    handle_local_plugins,
)
from web.tools._market.market import (
    handle_market_categories,
    handle_market_detail,
    handle_market_get_mirror,
    handle_market_list,
    handle_market_refresh,
    handle_market_set_mirror,
    handle_market_test_mirror,
)

__all__ = [
    'set_context',
    'handle_market_list',
    'handle_market_categories',
    'handle_market_detail',
    'handle_market_refresh',
    'handle_market_preview',
    'handle_market_install',
    'handle_market_uninstall',
    'handle_local_plugins',
    'handle_local_plugin_read',
    'handle_local_plugin_save',
    'handle_market_get_mirror',
    'handle_market_set_mirror',
    'handle_market_test_mirror',
]


def set_context(app_instance, base_dir: str):
    _shared.set_context(base_dir)
    set_install_context(app_instance)
