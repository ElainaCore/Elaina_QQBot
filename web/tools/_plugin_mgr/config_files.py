"""插件与模块配置文件处理器。"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile

import yaml
from aiohttp import web

from core.base.zipsafe import is_within
from web.protocol import json_body

MAX_CONFIG_SIZE = 2 * 1024 * 1024


def _manager():
    from web.tools import plugin_mgr

    return plugin_mgr


def _yaml_scalar(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if not isinstance(value, str):
        return str(value)
    if not value:
        return "''"
    quoted = any(char in value for char in ':#[]{}|>&*!?,') or value[:1] == ' ' or value[-1:] == ' '
    return f"'{value}'" if quoted else value


def _rebuild_yaml(data, comments, prefix='', indent=0):
    if not isinstance(data, dict):
        return []
    output, padding = [], '  ' * indent
    for key, value in data.items():
        path = f'{prefix}.{key}' if prefix else key
        comment = comments.get(path, '')
        if isinstance(value, dict):
            if comment:
                output.append(f'{padding}# {comment}')
            output.append(f'{padding}{key}:')
            output.extend(_rebuild_yaml(value, comments, path, indent + 1))
        elif isinstance(value, list):
            if comment:
                output.append(f'{padding}# {comment}')
            if not value:
                output.append(f'{padding}{key}: []')
                continue
            output.append(f'{padding}{key}:')
            child_padding = '  ' * (indent + 1)
            for item in value:
                if isinstance(item, dict):
                    for index, (item_key, item_value) in enumerate(item.items()):
                        marker = '- ' if index == 0 else '  '
                        output.append(f'{child_padding}{marker}{item_key}: {_yaml_scalar(item_value)}')
                else:
                    output.append(f'{child_padding}- {_yaml_scalar(item)}')
        else:
            scalar = _yaml_scalar(value)
            output.append(f'{padding}{key}: {scalar}  # {comment}' if comment else f'{padding}{key}: {scalar}')
    return output


def _extract_yaml_comments(raw_text):
    comments, pending, stack = {}, None, []
    for line in raw_text.splitlines():
        stripped = line.rstrip()
        if not stripped:
            pending = None
            continue
        comment_match = re.match(r'^(\s*)#\s*(.*)', stripped)
        if comment_match:
            pending = comment_match.group(2).strip()
            continue
        key_match = re.match(r'^(\s*)([A-Za-z_][\w]*)\s*:', stripped)
        if not key_match:
            pending = None
            continue
        indentation, key = len(key_match.group(1)), key_match.group(2)
        while stack and stack[-1][0] >= indentation:
            stack.pop()
        inline_match = re.search(r'#\s*(.+)$', stripped)
        inline = inline_match.group(1).strip() if inline_match and ':' in stripped[: inline_match.start()] else ''
        comment = inline or pending or ''
        if comment:
            comments['.'.join([item[1] for item in stack] + [key])] = comment
        stack.append((indentation, key))
        pending = None
    return comments


async def handle_read_config(request: web.Request):
    manager = _manager()
    body = await json_body(request)
    if not body.get('path'):
        return web.json_response({'success': False, 'message': '缺少路径'}, status=400)
    path, error = manager.validate_config_path(body['path'])
    if error:
        return error
    if not os.path.isfile(path):
        return web.json_response({'success': False, 'message': '文件不存在'}, status=404)
    if os.path.getsize(path) > MAX_CONFIG_SIZE:
        return web.json_response({'success': False, 'message': '配置文件超过 2 MB 限制'}, status=413)
    fmt = manager.detect_config_format(os.path.splitext(path)[1].lower())
    with open(path, encoding='utf-8') as file:
        raw = file.read()
    parsed, comments = None, {}
    if fmt == 'yaml':
        with contextlib.suppress(Exception):
            parsed = yaml.safe_load(raw)
            comments = _extract_yaml_comments(raw)
    elif fmt == 'json':
        with contextlib.suppress(Exception):
            parsed = json.loads(raw)
    return web.json_response(
        {
            'success': True,
            'format': fmt,
            'raw': raw,
            'parsed': parsed,
            'comments': comments,
            'filename': os.path.basename(path),
        }
    )


async def handle_save_config(request: web.Request):
    manager = _manager()
    body = await json_body(request)
    content, fmt = body.get('content'), body.get('format', 'raw')
    if not body.get('path') or not isinstance(content, str):
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    if len(content.encode('utf-8')) > MAX_CONFIG_SIZE:
        return web.json_response({'success': False, 'message': '配置文件超过 2 MB 限制'}, status=413)
    path, error = manager.validate_config_path(body['path'])
    if error:
        return error
    if fmt == 'yaml':
        try:
            parsed = yaml.safe_load(content)
        except Exception as exc:
            return web.json_response({'success': False, 'message': f'YAML 格式错误: {exc}'}, status=400)
        if isinstance(parsed, dict) and os.path.isfile(path):
            with contextlib.suppress(Exception), open(path, encoding='utf-8') as file:
                comments = _extract_yaml_comments(file.read())
                if comments:
                    content = '\n'.join(_rebuild_yaml(parsed, comments)) + '\n'
    elif fmt == 'json':
        try:
            content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        except Exception as exc:
            return web.json_response({'success': False, 'message': f'JSON 格式错误: {exc}'}, status=400)
    else:
        return web.json_response({'success': False, 'message': '不支持的配置格式'}, status=400)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        shutil.copy2(path, path + '.backup')
    fd, temp_path = tempfile.mkstemp(prefix='.config-', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(content)
        os.replace(temp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(temp_path)
        raise

    reloaded = ''
    modules_root = os.path.realpath(manager.modules_dir())
    if is_within(modules_root, path):
        module_manager = manager.get_mm()
        if module_manager:
            module_name = os.path.relpath(path, modules_root).split(os.sep)[0]
            if module_manager.is_enabled(module_name):
                with contextlib.suppress(Exception):
                    await module_manager.reload(module_name)
                    reloaded = module_name
    message = f'配置已保存, 模块 {reloaded} 已重载' if reloaded else '配置已保存'
    return web.json_response({'success': True, 'message': message})
