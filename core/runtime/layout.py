"""One-way cleanup for framework layouts removed by breaking releases."""

from __future__ import annotations

import shutil
from pathlib import Path

_LEGACY_CORE_PATHS = (
    'application.py',
    'embedded_qq.py',
    'qq_catalog.py',
    'qq_installer.py',
    'qq_launcher.py',
    'qq_manager.py',
    'base',
    'module',
    'onebot',
    'plugin',
    'server',
    'storage',
)


def purge_legacy_core_layout(base_dir: str | Path) -> list[str]:
    """Delete only framework paths explicitly retired by the current layout."""
    core_dir = Path(base_dir).resolve() / 'core'
    removed: list[str] = []
    for relative in _LEGACY_CORE_PATHS:
        target = core_dir / relative
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(f'core/{relative}')
    return removed
