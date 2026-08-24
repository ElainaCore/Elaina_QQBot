"""Non-blocking filesystem helpers shared by the framework and plugins."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar('T')


def replace_directory(
    staged: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    preserve: tuple[str, ...] = ('data',),
) -> None:
    """Atomically replace a directory while retaining selected runtime data."""
    staged_path = Path(os.path.abspath(staged))
    target_path = Path(os.path.abspath(target))
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        for name in preserve:
            source = target_path / name
            destination = staged_path / name
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
            elif source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    backup = Path(tempfile.mkdtemp(prefix=f'.{target_path.name}-backup-', dir=target_path.parent))
    backup.rmdir()
    had_target = target_path.exists()
    if had_target:
        shutil.move(str(target_path), str(backup))
    try:
        shutil.move(str(staged_path), str(target_path))
    except Exception:
        if had_target and backup.exists() and not target_path.exists():
            shutil.move(str(backup), str(target_path))
        raise
    else:
        if backup.is_dir():
            shutil.rmtree(backup)
        elif backup.exists():
            backup.unlink()


async def run_sync(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Run unavoidable blocking work without occupying the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def ensure_dir(path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
    return target


async def read_text(path: str | os.PathLike[str], *, encoding: str = 'utf-8') -> str:
    return await asyncio.to_thread(Path(path).read_text, encoding=encoding)


def _write_text(path: Path, content: str, encoding: str, atomic: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not atomic:
        path.write_text(content, encoding=encoding)
        return
    temporary = path.with_name(f'.{path.name}.tmp')
    temporary.write_text(content, encoding=encoding)
    os.replace(temporary, path)


async def write_text(
    path: str | os.PathLike[str],
    content: str,
    *,
    encoding: str = 'utf-8',
    atomic: bool = True,
) -> None:
    await asyncio.to_thread(_write_text, Path(path), content, encoding, atomic)


async def read_json(
    path: str | os.PathLike[str],
    *,
    default: T | None = None,
) -> Any | T | None:
    target = Path(path)

    def load():
        if not target.is_file():
            return default
        with target.open(encoding='utf-8') as file:
            return json.load(file)

    return await asyncio.to_thread(load)


async def write_json(
    path: str | os.PathLike[str],
    value: Any,
    *,
    indent: int = 2,
) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=indent) + '\n'
    await write_text(path, content)
