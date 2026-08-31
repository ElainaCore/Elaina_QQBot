"""框架更新 — 门面 (复用 _updater 包)"""

from web.tools._updater.handlers import (
    handle_check_update,
    handle_detect_environment,
    handle_get_changelog,
    handle_get_current_version,
    handle_get_mirrors,
    handle_get_update_progress,
    handle_set_custom_mirror,
    handle_start_update,
    handle_test_mirrors,
    handle_upload_update,
    set_context,
)

__all__ = [
    'set_context',
    'handle_get_changelog',
    'handle_get_current_version',
    'handle_check_update',
    'handle_start_update',
    'handle_get_update_progress',
    'handle_get_mirrors',
    'handle_test_mirrors',
    'handle_upload_update',
    'handle_set_custom_mirror',
    'handle_detect_environment',
]
