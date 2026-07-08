"""插件 / 模块 / 配置文件 管理 (OneBot 适配)"""

import ast
import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import cast

import yaml
from aiohttp import BodyPartReader, web

from core.base.zipsafe import safe_extractall

log = logging.getLogger('ElainaBot.web.plugin_mgr')

_app = None
_base_dir = ''
ENTRY_CANDIDATES = ('main.py', '__init__.py')
_CONFIG_EXTS = ('.yaml', '.yml', '.json')

_PLUGIN_TEMPLATE = '''"""新插件"""

from core.plugin.decorators import handler


@handler(r'^指令$', name='示例指令', desc='示例指令描述')
async def handle_command(event, match):
    await event.reply("Hello, World!")
'''


def set_context(app_instance, base_dir: str):
    global _app, _base_dir
    _app = app_instance
    _base_dir = base_dir


def get_pm():
    return getattr(_app, 'plugin_manager', None) if _app else None


def get_mm():
    return getattr(_app, 'module_manager', None) if _app else None


def plugins_dir():
    return os.path.join(_base_dir, 'plugins')


def modules_dir():
    return os.path.join(_base_dir, 'modules')


def find_entry(plugin_dir):
    for e in ENTRY_CANDIDATES:
        p = os.path.join(plugin_dir, e)
        if os.path.isfile(p):
            return p
    base = os.path.basename(plugin_dir)
    p = os.path.join(plugin_dir, f'{base}.py')
    return p if os.path.isfile(p) else None


def validate_path(rel_or_abs, root):
    root_abs = os.path.abspath(root)
    cand = rel_or_abs
    if not os.path.isabs(cand):
        cand = os.path.join(root, cand) if not cand.startswith(os.path.basename(root)) else os.path.join(_base_dir, cand)
    abs_path = os.path.abspath(cand)
    if not abs_path.startswith(root_abs):
        return False, ''
    return True, abs_path


def validate_config_path(rel_or_abs):
    for root in (plugins_dir(), modules_dir()):
        ok, abs_path = validate_path(rel_or_abs, root)
        if ok:
            return abs_path, None
    return '', web.json_response({'success': False, 'message': '无效路径'}, status=403)


def list_config_files(data_dir):
    files = []
    if not os.path.isdir(data_dir):
        return files
    for fname in sorted(os.listdir(data_dir)):
        fpath = os.path.join(data_dir, fname)
        if os.path.isfile(fpath) and os.path.splitext(fname)[1].lower() in _CONFIG_EXTS:
            files.append({'name': fname, 'path': fpath.replace('\\', '/'),
                          'size': os.path.getsize(fpath)})
    return files


def detect_config_format(ext):
    if ext in ('.yaml', '.yml'):
        return 'yaml'
    if ext == '.json':
        return 'json'
    return 'raw'


# ════════════════ 插件扫描 ════════════════

def _read_file_meta(py_path):
    try:
        with open(py_path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == '__plugin_meta__'):
                meta = ast.literal_eval(node.value)
                if isinstance(meta, dict):
                    allowed = {'name', 'version', 'author', 'description'}
                    return {k: str(v) for k, v in meta.items() if k in allowed and v}
    except Exception:
        pass
    return None


def _scan_py_files(dir_path, prefix='', read_meta=False):
    files = []
    for fname in sorted(os.listdir(dir_path)):
        if fname.startswith('_') or not fname.endswith('.py'):
            continue
        fpath = os.path.join(dir_path, fname)
        if not os.path.isfile(fpath):
            continue
        stat = os.stat(fpath)
        info = {
            'name': f'{prefix}{fname}' if prefix else fname,
            'path': fpath.replace('\\', '/'),
            'enabled': True,
            'size': stat.st_size,
            'last_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
        if read_meta:
            meta = _read_file_meta(fpath)
            if meta:
                info['meta'] = meta
        files.append(info)
    return files


def _scan_plugin_dirs():
    pdir = plugins_dir()
    dirs = []
    if not os.path.isdir(pdir):
        return dirs
    pm = get_pm()
    plugin_info_map = pm.get_web_plugin_info() if pm else {}
    disabled_set = pm.get_disabled_plugins() if pm else set()

    for dir_name in sorted(os.listdir(pdir)):
        dir_path = os.path.join(pdir, dir_name)
        if not os.path.isdir(dir_path) or dir_name.startswith(('.', '__', '_')):
            continue
        is_system = dir_name == 'system'
        pinfo = plugin_info_map.get(dir_name, {})
        has_entry = any(e in os.listdir(dir_path) for e in ENTRY_CANDIDATES) or \
            os.path.isfile(os.path.join(dir_path, f'{dir_name}.py'))
        files = _scan_py_files(dir_path, read_meta=not has_entry)
        if not files:
            continue

        # 持久化禁用状态: 目录级 或 入口文件级 (入口文件禁用 = 整体禁用)
        entry_path = find_entry(dir_path)
        entry_key = f'{dir_name}/{os.path.basename(entry_path)[:-3]}' if entry_path else ''
        persist_disabled = dir_name in disabled_set or (entry_key and entry_key in disabled_set)

        # 标记文件级别的 enabled
        for f in files:
            stem = f['name'][:-3] if f['name'].endswith('.py') else f['name']
            if persist_disabled or f'{dir_name}/{stem}' in disabled_set:
                f['enabled'] = False

        if has_entry:
            app_dir = os.path.join(dir_path, 'app')
            if os.path.isdir(app_dir):
                sub_files = _scan_py_files(app_dir, prefix='app/')
                for f in sub_files:
                    stem = f['name'][:-3] if f['name'].endswith('.py') else f['name']
                    if persist_disabled or f'{dir_name}/{stem}' in disabled_set:
                        f['enabled'] = False
                files.extend(sub_files)

        loaded = dir_name in (pm.plugins if pm else {})
        dirs.append({
            'directory': dir_name,
            'is_system': is_system,
            'enabled': loaded and not persist_disabled,
            'is_large': has_entry,
            'files': files,
            'allowed_bots': [],
            'commands': pinfo.get('commands', []),
            'description': pinfo.get('description', ''),
            'meta': pinfo.get('meta', {}),
        })
    dirs.sort(key=lambda d: (not d['enabled'], d['directory']))
    return dirs


async def handle_scan_plugins(request: web.Request):
    return web.json_response({'success': True, 'plugins': _scan_plugin_dirs()})


async def handle_scan_plugin_dirs(request: web.Request):
    return web.json_response({'success': True, 'dirs': _scan_plugin_dirs()})


# ════════════════ 插件启停 / 重载 ════════════════

async def handle_toggle_plugin(request: web.Request):
    body = await request.json()
    name = body.get('name', '')
    file = body.get('file', '')
    action = body.get('action', '')
    if not name or action not in ('enable', 'disable'):
        return web.json_response({'success': False, 'message': '参数不完整'}, status=400)
    if not os.path.isdir(os.path.join(plugins_dir(), name)):
        return web.json_response({'success': False, 'message': f'插件目录不存在: {name}'}, status=404)
    pm = get_pm()
    if not pm:
        return web.json_response({'success': False, 'message': '插件管理器未初始化'}, status=503)

    key = f'{name}/{file}' if file else name
    try:
        (pm.enable_plugin if action == 'enable' else pm.disable_plugin)(key)
        # 入口文件/目录级: 需加载/卸载整个插件; 子文件: 重载目录即可
        is_entry = not file or f'{file}.py' in ('main.py', 'index.py', 'app.py') or file == name
        if is_entry:
            if action == 'enable' and name not in pm.plugins:
                await pm.reload(name)
            elif action == 'disable' and name in pm.plugins:
                await pm.unload(name)
        else:
            if name in pm.plugins:
                await pm.reload(name)
        label = '已启用' if action == 'enable' else '已禁用'
        return web.json_response({'success': True, 'message': f'{key} {label}', 'plugin_name': name})
    except Exception as e:
        log.error(f'插件 {action} [{key}] 失败: {e}')
        return web.json_response({'success': False, 'message': f'操作异常: {e}'}, status=500)


async def handle_reload_plugin(request: web.Request):
    body = await request.json()
    name = body.get('name', '')
    if not name:
        return web.json_response({'success': False, 'message': '缺少插件名'}, status=400)
    pm = get_pm()
    if not pm:
        return web.json_response({'success': False, 'message': '插件管理器未初始化'}, status=503)
    try:
        result = await pm.reload(name)
        if result:
            info = pm.plugins.get(name)
            count = len(info.handlers) if info else 0
            return web.json_response({'success': True, 'message': f'重载完成: {count} 个处理器', 'handler_count': count})
        return web.json_response({'success': False, 'message': '重载失败'})
    except Exception as e:
        return web.json_response({'success': False, 'message': f'重载异常: {e}'}, status=500)


# ════════════════ 插件读写 / 创建 / 上传 ════════════════

async def handle_read_plugin(request: web.Request):
    body = await request.json()
    plugin_path = os.path.normpath(body.get('path', ''))
    if not plugin_path:
        return web.json_response({'success': False, 'message': '缺少路径'}, status=400)
    valid, abs_path = validate_path(plugin_path, plugins_dir())
    if not valid or not os.path.isfile(abs_path):
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    with open(abs_path, encoding='utf-8') as f:
        content = f.read()
    return web.json_response({'success': True, 'content': content,
                              'path': plugin_path.replace('\\', '/'),
                              'filename': os.path.basename(plugin_path)})


async def handle_save_plugin(request: web.Request):
    body = await request.json()
    plugin_path = os.path.normpath(body.get('path', ''))
    content = body.get('content')
    if not plugin_path or content is None:
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    valid, abs_path = validate_path(plugin_path, plugins_dir())
    if not valid:
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    if os.path.exists(abs_path):
        shutil.copy2(abs_path, abs_path + '.backup')
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return web.json_response({'success': True, 'message': '插件已保存'})


async def handle_create_plugin(request: web.Request):
    body = await request.json()
    directory = body.get('directory', '')
    filename = body.get('filename', '')
    if not directory or not filename:
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    if not filename.endswith('.py'):
        filename += '.py'
    pdir = plugins_dir()
    target_dir = os.path.join(pdir, directory)
    if not os.path.abspath(target_dir).startswith(os.path.abspath(pdir)):
        return web.json_response({'success': False, 'message': '无效目录'}, status=403)
    plugin_path = os.path.join(target_dir, filename)
    if os.path.exists(plugin_path):
        return web.json_response({'success': False, 'message': '文件已存在'}, status=409)
    os.makedirs(target_dir, exist_ok=True)
    with open(plugin_path, 'w', encoding='utf-8') as f:
        f.write(_PLUGIN_TEMPLATE)
    return web.json_response({'success': True, 'message': '插件已创建', 'path': plugin_path.replace('\\', '/')})


async def handle_create_folder(request: web.Request):
    body = await request.json()
    folder_name = body.get('folder_name', '')
    parent_dir = body.get('parent_dir', '')
    if not folder_name:
        return web.json_response({'success': False, 'message': '缺少文件夹名'}, status=400)
    pdir = plugins_dir()
    target = os.path.join(pdir, parent_dir, folder_name) if parent_dir else os.path.join(pdir, folder_name)
    if not os.path.abspath(target).startswith(os.path.abspath(pdir)):
        return web.json_response({'success': False, 'message': '无效目录'}, status=403)
    if os.path.exists(target):
        return web.json_response({'success': False, 'message': '文件夹已存在'}, status=409)
    os.makedirs(target, exist_ok=True)
    return web.json_response({'success': True, 'message': '文件夹已创建'})


async def handle_get_folders(request: web.Request):
    pdir = plugins_dir()
    folders = []
    if os.path.isdir(pdir):
        for item in sorted(os.listdir(pdir)):
            if os.path.isdir(os.path.join(pdir, item)) and not item.startswith(('.', '__', '_')):
                folders.append({'name': item, 'path': item})
    return web.json_response({'success': True, 'folders': folders})


async def handle_upload_plugin(request: web.Request):
    reader = await request.multipart()
    file_data = filename = None
    directory = 'alone'
    async for field in reader:
        field = cast(BodyPartReader, field)
        if field.name == 'file':
            filename = field.filename
            file_data = await field.read()
        elif field.name == 'directory':
            directory = (await field.text()).strip() or 'alone'

    if not file_data or not filename:
        return web.json_response({'success': False, 'message': '没有文件'}, status=400)
    is_zip = filename.lower().endswith('.zip')
    is_py = filename.lower().endswith('.py')
    if not is_zip and not is_py:
        return web.json_response({'success': False, 'message': '仅支持 .py 或 .zip 文件'}, status=400)

    pdir = plugins_dir()
    if is_py:
        safe_name = re.sub(r'[^\w\u4e00-\u9fa5\-.]', '_', filename)
        target_dir = os.path.join(pdir, directory)
        if not os.path.abspath(target_dir).startswith(os.path.abspath(pdir)):
            return web.json_response({'success': False, 'message': '无效目录'}, status=403)
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, safe_name)
        if os.path.exists(dest):
            base, c = safe_name[:-3], 1
            while os.path.exists(dest):
                dest = os.path.join(target_dir, f'{base}_{c}.py')
                c += 1
        with open(dest, 'wb') as f:
            f.write(file_data)
        return web.json_response({'success': True, 'message': f'上传成功: {os.path.basename(dest)}',
                                  'path': dest.replace('\\', '/')})

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp.write(file_data)
        if not zipfile.is_zipfile(tmp.name):
            return web.json_response({'success': False, 'message': '无效的 zip 文件'}, status=400)
        with zipfile.ZipFile(tmp.name, 'r') as zf:
            names = zf.namelist()
            if not names:
                return web.json_response({'success': False, 'message': 'zip 文件为空'}, status=400)
            top_dirs, top_files = set(), set()
            for n in names:
                parts = n.replace('\\', '/').strip('/').split('/')
                if len(parts) > 1 and parts[0]:
                    top_dirs.add(parts[0])
                elif len(parts) == 1 and parts[0]:
                    top_files.add(parts[0])
            os.makedirs(pdir, exist_ok=True)
            if len(top_dirs) == 1 and not top_files:
                folder_name = list(top_dirs)[0]
                safe_folder = re.sub(r'[^\w\u4e00-\u9fa5\-]', '_', folder_name)
                target_dir = os.path.join(pdir, safe_folder)
                if os.path.exists(target_dir):
                    backup = target_dir + '.bak'
                    if os.path.exists(backup):
                        shutil.rmtree(backup)
                    shutil.move(target_dir, backup)
                extract_tmp = tempfile.mkdtemp()
                safe_extractall(zf, extract_tmp)
                shutil.move(os.path.join(extract_tmp, folder_name), target_dir)
                shutil.rmtree(extract_tmp, ignore_errors=True)
            else:
                safe_folder = re.sub(r'[^\w\u4e00-\u9fa5\-]', '_', os.path.splitext(filename)[0])
                target_dir = os.path.join(pdir, safe_folder)
                if os.path.exists(target_dir):
                    backup = target_dir + '.bak'
                    if os.path.exists(backup):
                        shutil.rmtree(backup)
                    shutil.move(target_dir, backup)
                os.makedirs(target_dir, exist_ok=True)
                safe_extractall(zf, target_dir)
            plugin_name = os.path.basename(target_dir)
        return web.json_response({'success': True, 'message': f'插件 {plugin_name} 上传成功', 'plugin_name': plugin_name})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)
    finally:
        if tmp is not None:
            with contextlib.suppress(Exception):
                os.unlink(tmp.name)


# ════════════════ 插件机器人绑定 (OneBot 单机器人, 降级) ════════════════

async def handle_get_plugin_bots(request: web.Request):
    return web.json_response({'success': True, 'plugin_bots': {}})


async def handle_set_plugin_bots(request: web.Request):
    return web.json_response({'success': True, 'message': 'OneBot 为单机器人模式，无需配置机器人绑定'})


async def handle_plugin_config_files(request: web.Request):
    body = await request.json()
    plugin_name = body.get('name', '')
    if not plugin_name:
        return web.json_response({'success': False, 'message': '缺少插件名'}, status=400)
    plugin_dir = os.path.join(plugins_dir(), plugin_name)
    files = list_config_files(os.path.join(plugin_dir, 'data'))
    return web.json_response({'success': True, 'config_files': files})


# ════════════════ 模块管理 ════════════════

def _read_module_meta(entry_path):
    try:
        with open(entry_path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == '__module_meta__'):
                return ast.literal_eval(node.value)
    except Exception:
        pass
    return {}


def _scan_modules():
    mdir = modules_dir()
    result = []
    if not os.path.isdir(mdir):
        return result
    mm = get_mm()
    runtime = {m['name']: m for m in mm.list_modules()} if mm else {}
    persist_map = {}
    enabled_file = os.path.join(mdir, 'modules_enabled.json')
    if os.path.isfile(enabled_file):
        with contextlib.suppress(Exception), open(enabled_file, encoding='utf-8') as f:
            persist_map = json.load(f) or {}

    for name in sorted(os.listdir(mdir)):
        mod_dir = os.path.join(mdir, name)
        if not os.path.isdir(mod_dir) or name.startswith('_'):
            continue
        entry = os.path.join(mod_dir, 'main.py')
        if not os.path.isfile(entry):
            continue
        meta = _read_module_meta(entry)
        rt = runtime.get(name, {})
        result.append({
            'name': name,
            'display_name': meta.get('name') or rt.get('display_name') or name,
            'description': meta.get('description') or rt.get('description', ''),
            'version': meta.get('version') or rt.get('version', '1.0.0'),
            'author': meta.get('author') or rt.get('author', ''),
            'enabled': rt.get('enabled', False),
            'persist_enabled': rt.get('persist_enabled', persist_map.get(name, False)),
            'error': rt.get('error'),
            'last_modified': datetime.fromtimestamp(os.path.getmtime(entry)).strftime('%Y-%m-%d %H:%M:%S'),
            'config_files': list_config_files(os.path.join(mod_dir, 'data')),
        })
    return result


async def handle_scan_modules(request: web.Request):
    return web.json_response({'success': True, 'modules': _scan_modules()})


async def handle_module_toggle(request: web.Request):
    body = await request.json()
    name = body.get('name', '')
    action = body.get('action', '')
    if not name or action not in ('enable', 'disable'):
        return web.json_response({'success': False, 'message': '参数错误'}, status=400)
    mm = get_mm()
    if not mm:
        return web.json_response({'success': False, 'message': '模块管理器未初始化'}, status=503)
    try:
        if action == 'enable':
            ok = await mm.enable(name)
        else:
            ok = await mm.disable(name)
            if not ok:
                mm.set_module_enabled_persist(name, False)
                return web.json_response({'success': True, 'message': f'模块 {name} 已关闭'})
        if ok:
            verb = '开启' if action == 'enable' else '关闭'
            return web.json_response({'success': True, 'message': f'模块 {name} 已{verb}'})
        return web.json_response({'success': False, 'message': '操作失败'})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def handle_module_upload(request: web.Request):
    reader = await request.multipart()
    field = cast(BodyPartReader, await reader.next())
    if not field or field.name != 'file':
        return web.json_response({'success': False, 'message': '缺少文件'}, status=400)
    filename = field.filename or ''
    if not filename.lower().endswith('.zip'):
        return web.json_response({'success': False, 'message': '仅支持 zip 格式'}, status=400)

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                tmp.write(chunk)
        if not zipfile.is_zipfile(tmp.name):
            return web.json_response({'success': False, 'message': '无效的 zip 文件'}, status=400)
        with zipfile.ZipFile(tmp.name, 'r') as zf:
            names = zf.namelist()
            if not any(n.endswith('.py') for n in names):
                return web.json_response({'success': False, 'message': 'zip 必须包含 .py 文件'}, status=400)
            mod_name = os.path.splitext(filename)[0]
            top_dirs = {n.replace('\\', '/').split('/')[0] for n in names if '/' in n.replace('\\', '/')}
            mdir = modules_dir()
            os.makedirs(mdir, exist_ok=True)
            target_dir = os.path.join(mdir, mod_name)
            if os.path.exists(target_dir):
                backup = target_dir + '.bak'
                if os.path.exists(backup):
                    shutil.rmtree(backup)
                shutil.move(target_dir, backup)
            if len(top_dirs) == 1:
                extract_tmp = tempfile.mkdtemp()
                safe_extractall(zf, extract_tmp)
                shutil.move(os.path.join(extract_tmp, list(top_dirs)[0]), target_dir)
                shutil.rmtree(extract_tmp, ignore_errors=True)
            else:
                os.makedirs(target_dir, exist_ok=True)
                safe_extractall(zf, target_dir)
        if not os.path.isfile(os.path.join(target_dir, 'main.py')):
            shutil.rmtree(target_dir, ignore_errors=True)
            return web.json_response({'success': False, 'message': '解压后未找到 main.py'}, status=400)
        return web.json_response({'success': True, 'message': f'模块 {mod_name} 上传成功，重启后生效', 'module_name': mod_name})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)
    finally:
        if tmp is not None:
            with contextlib.suppress(Exception):
                os.unlink(tmp.name)


# ════════════════ 配置文件读写 (YAML 注释保留) ════════════════

def _ys(v):
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if not isinstance(v, str):
        return str(v)
    if not v:
        return "''"
    return f"'{v}'" if any(c in v for c in ':#[]{}|>&*!?,') or v[0] == ' ' or v[-1] == ' ' else v


def _rebuild_yaml(data, cmt, pre='', ind=0):
    if not isinstance(data, dict):
        return []
    out, pad = [], '  ' * ind
    for k, v in data.items():
        p = f'{pre}.{k}' if pre else k
        c = cmt.get(p, '')
        if isinstance(v, dict):
            if c:
                out.append(f'{pad}# {c}')
            out.append(f'{pad}{k}:')
            out.extend(_rebuild_yaml(v, cmt, p, ind + 1))
        elif isinstance(v, list):
            if c:
                out.append(f'{pad}# {c}')
            if not v:
                out.append(f'{pad}{k}: []')
            else:
                out.append(f'{pad}{k}:')
                cp = '  ' * (ind + 1)
                for it in v:
                    if isinstance(it, dict):
                        for i, (ik, iv) in enumerate(it.items()):
                            out.append(f'{cp}{"- " if not i else "  "}{ik}: {_ys(iv)}')
                    else:
                        out.append(f'{cp}- {_ys(it)}')
        else:
            s = _ys(v)
            out.append(f'{pad}{k}: {s}  # {c}' if c else f'{pad}{k}: {s}')
    return out


def _extract_yaml_comments(raw_text):
    comments = {}
    pending = None
    stack = []
    for line in raw_text.split('\n'):
        stripped = line.rstrip()
        if not stripped:
            pending = None
            continue
        m_comment = re.match(r'^(\s*)#\s*(.*)', stripped)
        if m_comment:
            pending = m_comment.group(2).strip()
            continue
        m_kv = re.match(r'^(\s*)([A-Za-z_][\w]*)\s*:', stripped)
        if not m_kv:
            pending = None
            continue
        indent = len(m_kv.group(1))
        key = m_kv.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        inline = ''
        m_inline = re.search(r'#\s*(.+)$', stripped)
        if m_inline:
            before = stripped[:m_inline.start()].rstrip()
            if ':' in before:
                inline = m_inline.group(1).strip()
        comment = inline or pending or ''
        if comment:
            comments['.'.join([p[1] for p in stack] + [key])] = comment
        stack.append((indent, key))
        pending = None
    return comments


async def handle_read_config(request: web.Request):
    body = await request.json()
    if not body.get('path', ''):
        return web.json_response({'success': False, 'message': '缺少路径'}, status=400)
    abs_path, err = validate_config_path(body['path'])
    if err:
        return err
    if not os.path.isfile(abs_path):
        return web.json_response({'success': False, 'message': '文件不存在'}, status=404)
    fmt = detect_config_format(os.path.splitext(abs_path)[1].lower())
    with open(abs_path, encoding='utf-8') as f:
        raw = f.read()
    parsed, comments = None, {}
    if fmt == 'yaml':
        with contextlib.suppress(Exception):
            parsed = yaml.safe_load(raw)
            comments = _extract_yaml_comments(raw)
    elif fmt == 'json':
        with contextlib.suppress(Exception):
            parsed = json.loads(raw)
    return web.json_response({'success': True, 'format': fmt, 'raw': raw, 'parsed': parsed,
                              'comments': comments, 'filename': os.path.basename(abs_path)})


async def handle_save_config(request: web.Request):
    body = await request.json()
    content = body.get('content')
    fmt = body.get('format', 'raw')
    if not body.get('path', '') or content is None:
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    abs_path, err = validate_config_path(body['path'])
    if err:
        return err
    if fmt == 'yaml':
        try:
            parsed = yaml.safe_load(content)
        except Exception as e:
            return web.json_response({'success': False, 'message': f'YAML 格式错误: {e}'}, status=400)
        if isinstance(parsed, dict) and os.path.isfile(abs_path):
            with contextlib.suppress(Exception):
                with open(abs_path, encoding='utf-8') as f:
                    old_comments = _extract_yaml_comments(f.read())
                if old_comments:
                    content = '\n'.join(_rebuild_yaml(parsed, old_comments)) + '\n'
    elif fmt == 'json':
        try:
            content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        except Exception as e:
            return web.json_response({'success': False, 'message': f'JSON 格式错误: {e}'}, status=400)
    if os.path.isfile(abs_path):
        shutil.copy2(abs_path, abs_path + '.backup')
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)

    reloaded = ''
    mdir = os.path.abspath(modules_dir())
    if abs_path.startswith(mdir):
        mm = get_mm()
        if mm:
            mod_name = os.path.relpath(abs_path, mdir).split(os.sep)[0]
            if mm.is_enabled(mod_name):
                with contextlib.suppress(Exception):
                    await mm.reload(mod_name)
                    reloaded = mod_name
    return web.json_response({'success': True, 'message': f'配置已保存, 模块 {reloaded} 已重载' if reloaded else '配置已保存'})
