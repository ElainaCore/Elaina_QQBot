"""带容量限制的插件与模块压缩包上传。"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
import zipfile
from typing import cast

from aiohttp import BodyPartReader, web

from core.base.zipsafe import is_within, safe_extractall, validate_archive

MAX_SOURCE_UPLOAD = 2 * 1024 * 1024
MAX_ARCHIVE_UPLOAD = 128 * 1024 * 1024


def _manager():
    from web.tools import plugin_mgr

    return plugin_mgr


async def _save_part(field: BodyPartReader, suffix: str, limit: int) -> tuple[str, int]:
    fd, path = tempfile.mkstemp(prefix='elaina-upload-', suffix=suffix)
    size = 0
    try:
        with os.fdopen(fd, 'wb') as file:
            while chunk := await field.read_chunk(size=256 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError(f'上传文件超过 {limit // 1024 // 1024} MB 限制')
                file.write(chunk)
        return path, size
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(path)
        raise


def _replace_tree(staged: str, target: str) -> None:
    backup = target + '.bak'
    if os.path.exists(backup):
        shutil.rmtree(backup) if os.path.isdir(backup) else os.remove(backup)
    had_target = os.path.exists(target)
    if had_target:
        shutil.move(target, backup)
    try:
        shutil.move(staged, target)
    except Exception:
        if had_target and os.path.exists(backup) and not os.path.exists(target):
            shutil.move(backup, target)
        raise


def _safe_component(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[^\w\u4e00-\u9fa5.-]', '_', value).strip('._')
    return cleaned or fallback


async def handle_upload_plugin(request: web.Request):
    manager = _manager()
    reader = await request.multipart()
    upload_path = filename = None
    directory = 'alone'
    try:
        async for raw_field in reader:
            field = cast(BodyPartReader, raw_field)
            if field.name == 'file':
                filename = os.path.basename((field.filename or '').replace('\\', '/'))
                suffix = os.path.splitext(filename)[1].lower()
                if suffix not in ('.py', '.zip'):
                    return web.json_response({'success': False, 'message': '仅支持 .py 或 .zip 文件'}, status=400)
                limit = MAX_SOURCE_UPLOAD if suffix == '.py' else MAX_ARCHIVE_UPLOAD
                upload_path, _ = await _save_part(field, suffix, limit)
            elif field.name == 'directory':
                directory = (await field.text()).strip() or 'alone'

        if not upload_path or not filename:
            return web.json_response({'success': False, 'message': '没有文件'}, status=400)

        plugins_root = os.path.realpath(manager.plugins_dir())
        if filename.lower().endswith('.py'):
            target_dir = os.path.realpath(os.path.join(plugins_root, directory))
            if not is_within(plugins_root, target_dir):
                return web.json_response({'success': False, 'message': '无效目录'}, status=403)
            os.makedirs(target_dir, exist_ok=True)
            safe_name = _safe_component(filename, 'plugin.py')
            if not safe_name.endswith('.py'):
                safe_name += '.py'
            destination = os.path.join(target_dir, safe_name)
            base, index = os.path.splitext(safe_name)[0], 1
            while os.path.exists(destination):
                destination = os.path.join(target_dir, f'{base}_{index}.py')
                index += 1
            os.replace(upload_path, destination)
            upload_path = None
            return web.json_response(
                {
                    'success': True,
                    'message': f'上传成功: {os.path.basename(destination)}',
                    'path': destination.replace('\\', '/'),
                }
            )

        if not zipfile.is_zipfile(upload_path):
            return web.json_response({'success': False, 'message': '无效的 zip 文件'}, status=400)
        os.makedirs(plugins_root, exist_ok=True)
        extraction_root = tempfile.mkdtemp(prefix='.plugin-upload-', dir=plugins_root)
        try:
            with zipfile.ZipFile(upload_path) as archive:
                validate_archive(archive, max_size=512 * 1024 * 1024)
                names = [name.replace('\\', '/') for name in archive.namelist() if name.strip('/')]
                if not names:
                    return web.json_response({'success': False, 'message': 'zip 文件为空'}, status=400)
                safe_extractall(archive, extraction_root, max_size=512 * 1024 * 1024)
            top_dirs = {name.strip('/').split('/')[0] for name in names if '/' in name.strip('/')}
            top_files = {name for name in names if '/' not in name.strip('/')}
            if len(top_dirs) == 1 and not top_files:
                source_name = next(iter(top_dirs))
                staged = os.path.join(extraction_root, source_name)
                plugin_name = _safe_component(source_name, 'plugin')
            else:
                plugin_name = _safe_component(os.path.splitext(filename)[0], 'plugin')
                staged = extraction_root
            target = os.path.join(plugins_root, plugin_name)
            if not is_within(plugins_root, target):
                return web.json_response({'success': False, 'message': '无效插件路径'}, status=400)
            _replace_tree(staged, target)
            return web.json_response(
                {
                    'success': True,
                    'message': f'插件 {plugin_name} 上传成功',
                    'plugin_name': plugin_name,
                }
            )
        finally:
            if extraction_root:
                shutil.rmtree(extraction_root, ignore_errors=True)
    except ValueError as error:
        return web.json_response({'success': False, 'message': str(error)}, status=413)
    except Exception as error:
        return web.json_response({'success': False, 'message': str(error)}, status=500)
    finally:
        if upload_path:
            with contextlib.suppress(OSError):
                os.remove(upload_path)


async def handle_module_upload(request: web.Request):
    manager = _manager()
    reader = await request.multipart()
    field = cast(BodyPartReader, await reader.next())
    if not field or field.name != 'file':
        return web.json_response({'success': False, 'message': '缺少文件'}, status=400)
    filename = os.path.basename((field.filename or '').replace('\\', '/'))
    if not filename.lower().endswith('.zip'):
        return web.json_response({'success': False, 'message': '仅支持 zip 格式'}, status=400)

    upload_path = extraction_root = ''
    try:
        upload_path, _ = await _save_part(field, '.zip', MAX_ARCHIVE_UPLOAD)
        if not zipfile.is_zipfile(upload_path):
            return web.json_response({'success': False, 'message': '无效的 zip 文件'}, status=400)
        module_name = os.path.splitext(filename)[0].strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', module_name):
            return web.json_response({'success': False, 'message': '无效模块名'}, status=400)
        modules_root = os.path.realpath(manager.modules_dir())
        os.makedirs(modules_root, exist_ok=True)
        extraction_root = tempfile.mkdtemp(prefix='.module-upload-', dir=modules_root)
        with zipfile.ZipFile(upload_path) as archive:
            validate_archive(archive, max_size=512 * 1024 * 1024)
            names = [name.replace('\\', '/') for name in archive.namelist() if name.strip('/')]
            if not any(name.endswith('.py') for name in names):
                return web.json_response({'success': False, 'message': 'zip 必须包含 .py 文件'}, status=400)
            safe_extractall(archive, extraction_root, max_size=512 * 1024 * 1024)
        top_dirs = {name.strip('/').split('/')[0] for name in names if '/' in name.strip('/')}
        top_files = {name for name in names if '/' not in name.strip('/')}
        staged = os.path.join(extraction_root, next(iter(top_dirs))) if len(top_dirs) == 1 and not top_files else extraction_root
        if not os.path.isfile(os.path.join(staged, 'main.py')):
            return web.json_response({'success': False, 'message': '解压后未找到 main.py'}, status=400)
        target = os.path.join(modules_root, module_name)
        if not is_within(modules_root, target):
            return web.json_response({'success': False, 'message': '无效模块路径'}, status=400)
        _replace_tree(staged, target)
        return web.json_response(
            {
                'success': True,
                'message': f'模块 {module_name} 上传成功，重启后生效',
                'module_name': module_name,
            }
        )
    except ValueError as error:
        return web.json_response({'success': False, 'message': str(error)}, status=413)
    except Exception as error:
        return web.json_response({'success': False, 'message': str(error)}, status=500)
    finally:
        if upload_path:
            with contextlib.suppress(OSError):
                os.remove(upload_path)
        if extraction_root:
            shutil.rmtree(extraction_root, ignore_errors=True)
