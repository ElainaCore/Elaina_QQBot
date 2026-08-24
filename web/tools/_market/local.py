"""本地插件源码管理。"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from aiohttp import web

from core.foundation.archives import is_within
from web.protocol import json_body
from web.tools._market.shared import _plugins_dir

MAX_SOURCE_SIZE = 2 * 1024 * 1024


def _source_path(path: object, *, must_exist: bool = False) -> str | None:
    if not isinstance(path, str) or not path.strip() or os.path.isabs(path):
        return None
    root = os.path.realpath(_plugins_dir())
    target = os.path.realpath(os.path.join(root, path))
    if not is_within(root, target) or not target.lower().endswith('.py'):
        return None
    if must_exist and not os.path.isfile(target):
        return None
    return target


def _read_source(path: str) -> str:
    if os.path.getsize(path) > MAX_SOURCE_SIZE:
        raise ValueError('源码文件超过 2 MB 限制')
    with open(path, encoding='utf-8') as file:
        return file.read()


def _scan_local_plugins(root: str) -> list[dict[str, Any]]:
    plugins = []
    if not os.path.isdir(root):
        return plugins
    for item in sorted(os.listdir(root)):
        item_path = os.path.join(root, item)
        if item.startswith(('.', '__')):
            continue
        if os.path.isdir(item_path):
            names = sorted(name for name in os.listdir(item_path) if name.endswith('.py') and not name.startswith('__'))
            plugins.extend({'name': f'{item}/{name[:-3]}', 'type': 'file', 'files': [name], 'path': f'{item}/{name}'} for name in names)
        elif item.endswith('.py'):
            plugins.append({'name': item[:-3], 'type': 'file', 'files': [item], 'path': item})
    return plugins


def _scan_local_source(root: str, directory: str) -> list[dict[str, Any]]:
    files = []
    for current, dirs, names in os.walk(directory):
        dirs[:] = [name for name in dirs if not name.startswith(('__', '.'))]
        for name in names:
            if name.startswith(('__', '.')):
                continue
            path = os.path.join(current, name)
            relative = os.path.relpath(path, root).replace('\\', '/')
            item = {'name': name, 'path': relative, 'size': os.path.getsize(path), 'editable': name.endswith('.py')}
            if item['editable']:
                try:
                    item['content'] = _read_source(path)
                except (OSError, UnicodeError, ValueError):
                    item['editable'] = False
            files.append(item)
    return files


def _save_local_source(target: str, content: str) -> None:
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.plugin-', suffix='.tmp', dir=os.path.dirname(target))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(content)
        os.replace(temporary, target)
    except Exception:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


async def handle_local_plugins(request: web.Request):
    root = _plugins_dir()
    plugins = await asyncio.to_thread(_scan_local_plugins, root)
    return web.json_response({'success': True, 'plugins': plugins})


async def handle_local_plugin_read(request: web.Request):
    body = await json_body(request)
    requested = body.get('path', '')
    full = _source_path(requested, must_exist=True)
    if full:
        try:
            content = await asyncio.to_thread(_read_source, full)
        except (OSError, UnicodeError, ValueError) as exc:
            return web.json_response({'success': False, 'message': str(exc)}, status=400)
        return web.json_response(
            {
                'success': True,
                'type': 'single',
                'files': [
                    {
                        'name': os.path.basename(full),
                        'path': requested,
                        'content': content,
                        'size': len(content),
                    }
                ],
            }
        )

    if not isinstance(requested, str) or not requested.strip() or os.path.isabs(requested):
        return web.json_response({'success': False, 'message': '无效路径'}, status=400)
    root = os.path.realpath(_plugins_dir())
    directory = os.path.realpath(os.path.join(root, requested))
    if not is_within(root, directory) or not os.path.isdir(directory):
        return web.json_response({'success': False, 'message': '不存在'}, status=404)

    files = await asyncio.to_thread(_scan_local_source, root, directory)
    return web.json_response({'success': True, 'type': 'folder', 'files': files})


async def handle_local_plugin_save(request: web.Request):
    body = await json_body(request)
    files = body.get('files', [])
    if not isinstance(files, list) or not files:
        return web.json_response({'success': False, 'message': '没有文件'}, status=400)
    saved, errors = [], []
    for item in files:
        path = item.get('path', '') if isinstance(item, dict) else ''
        content = item.get('content') if isinstance(item, dict) else None
        target = _source_path(path)
        if not target or not isinstance(content, str) or len(content.encode('utf-8')) > MAX_SOURCE_SIZE:
            errors.append(f'{path}: 无效或超过 2 MB')
            continue
        try:
            await asyncio.to_thread(_save_local_source, target, content)
            saved.append(path)
        except OSError as exc:
            errors.append(f'{path}: {exc}')
    return web.json_response(
        {
            'success': bool(saved),
            'message': f'已保存 {len(saved)} 个文件' + (f', {len(errors)} 个失败' if errors else ''),
            'saved': saved,
            'errors': errors,
        }
    )
