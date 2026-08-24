"""插件 / 模块 / 配置文件 管理 (OneBot 适配)"""

import ast
import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime

from aiohttp import web

from core.foundation.archives import is_within
from core.services.files import ensure_dir, read_text, run_sync, write_text
from web.protocol import json_body
from web.tools import _common
from web.tools._plugin_mgr.archives import handle_module_upload as handle_module_upload
from web.tools._plugin_mgr.archives import handle_upload_plugin as handle_upload_plugin
from web.tools._plugin_mgr.config_files import handle_read_config as handle_read_config
from web.tools._plugin_mgr.config_files import handle_save_config as handle_save_config

log = logging.getLogger('ElainaQQ.web.plugin_mgr')

_app = None
_base_dir = ''
ENTRY_CANDIDATES = ('main.py',)
_CONFIG_EXTS = ('.yaml', '.yml', '.json')

_PLUGIN_TEMPLATE = '''"""新插件"""

from core.plugins import handler


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
    if not is_within(root_abs, abs_path):
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
            files.append(
                {
                    'name': fname,
                    'path': fpath.replace('\\', '/'),
                    'size': os.path.getsize(fpath),
                    'format': detect_config_format(os.path.splitext(fname)[1].lower()),
                }
            )
    return files


def detect_config_format(ext):
    if ext in ('.yaml', '.yml'):
        return 'yaml'
    if ext == '.json':
        return 'json'
    return 'raw'


def _save_source(path: str, content: str) -> None:
    if os.path.exists(path):
        shutil.copy2(path, path + '.backup')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.plugin-', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(content)
        os.replace(temporary, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(temporary)
        raise


def _visible_folders(root: str) -> list[dict[str, str]]:
    if not os.path.isdir(root):
        return []
    return [
        {'name': item, 'path': item}
        for item in sorted(os.listdir(root))
        if os.path.isdir(os.path.join(root, item)) and not item.startswith(('.', '__', '_'))
    ]


# ════════════════ 插件扫描 ════════════════


def _read_file_meta(py_path):
    try:
        with open(py_path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == '__plugin_meta__':
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
    bots_map = pm.get_plugin_bots() if pm and hasattr(pm, 'get_plugin_bots') else {}

    for dir_name in sorted(os.listdir(pdir)):
        dir_path = os.path.join(pdir, dir_name)
        if not os.path.isdir(dir_path) or dir_name.startswith(('.', '__', '_')):
            continue
        is_system = dir_name == 'system'
        pinfo = plugin_info_map.get(dir_name, {})
        has_entry = os.path.isfile(os.path.join(dir_path, 'main.py'))
        if not has_entry:
            continue
        files = _scan_py_files(dir_path, read_meta=False)
        if not files:
            continue

        # 持久化禁用状态: 目录级 或 入口文件级 (入口文件禁用 = 整体禁用)
        persist_disabled = dir_name in disabled_set

        # 标记文件级别的 enabled
        for f in files:
            stem = f['name'][:-3] if f['name'].endswith('.py') else f['name']
            if persist_disabled or f'{dir_name}/{stem}' in disabled_set:
                f['enabled'] = False
            f['allowed_bots'] = bots_map.get(f'{dir_name}/{stem}', [])

        loaded = dir_name in (pm.plugins if pm else {})
        dirs.append(
            {
                'directory': dir_name,
                'is_system': is_system,
                'enabled': loaded and not persist_disabled,
                'files': files,
                'allowed_bots': bots_map.get(dir_name, []),
                'commands': pinfo.get('commands', []),
                'description': pinfo.get('description', ''),
                'meta': pinfo.get('meta', {}),
            }
        )
    dirs.sort(key=lambda d: (not d['enabled'], d['directory']))
    return dirs


async def handle_scan_plugins(request: web.Request):
    plugins = await asyncio.to_thread(_scan_plugin_dirs)
    return web.json_response({'success': True, 'plugins': plugins})


async def handle_scan_plugin_dirs(request: web.Request):
    directories = await asyncio.to_thread(_scan_plugin_dirs)
    return web.json_response({'success': True, 'dirs': directories})


# ════════════════ 插件启停 / 重载 ════════════════


async def handle_toggle_plugin(request: web.Request):
    body = await json_body(request)
    name = body.get('name', '')
    file = body.get('file', '')
    action = body.get('action', '')
    if not name or action not in ('enable', 'disable'):
        return web.json_response({'success': False, 'message': '参数不完整'}, status=400)
    valid, plugin_dir = validate_path(name, plugins_dir())
    if not valid or not os.path.isdir(plugin_dir):
        return web.json_response({'success': False, 'message': f'插件目录不存在: {name}'}, status=404)
    pm = get_pm()
    if not pm:
        return web.json_response({'success': False, 'message': '插件管理器未初始化'}, status=503)

    key = f'{name}/{file}' if file else name
    try:
        await (pm.enable_plugin if action == 'enable' else pm.disable_plugin)(key)
        # 入口文件/目录级: 需加载/卸载整个插件; 子文件: 重载目录即可
        is_entry = not file or file == 'main' or file == name
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
    body = await json_body(request)
    name = body.get('name', '')
    if not name:
        return web.json_response({'success': False, 'message': '缺少插件名'}, status=400)
    valid, plugin_dir = validate_path(name, plugins_dir())
    if not valid or not os.path.isdir(plugin_dir):
        return web.json_response({'success': False, 'message': '无效插件名'}, status=403)
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
    body = await json_body(request)
    plugin_path = os.path.normpath(body.get('path', ''))
    if not plugin_path:
        return web.json_response({'success': False, 'message': '缺少路径'}, status=400)
    valid, abs_path = validate_path(plugin_path, plugins_dir())
    if not valid or not os.path.isfile(abs_path):
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    content = await read_text(abs_path)
    return web.json_response({'success': True, 'content': content, 'path': plugin_path.replace('\\', '/'), 'filename': os.path.basename(plugin_path)})


async def handle_save_plugin(request: web.Request):
    body = await json_body(request)
    plugin_path = os.path.normpath(body.get('path', ''))
    content = body.get('content')
    if not plugin_path or not isinstance(content, str):
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    if not plugin_path.lower().endswith('.py') or len(content.encode('utf-8')) > 2 * 1024 * 1024:
        return web.json_response({'success': False, 'message': '仅允许保存不超过 2 MB 的 Python 源码'}, status=400)
    valid, abs_path = validate_path(plugin_path, plugins_dir())
    if not valid:
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    await run_sync(_save_source, abs_path, content)
    return web.json_response({'success': True, 'message': '插件已保存'})


async def handle_create_plugin(request: web.Request):
    body = await json_body(request)
    directory = body.get('directory', '')
    filename = body.get('filename', '')
    if not directory or not filename:
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    if not filename.endswith('.py'):
        filename += '.py'
    pdir = plugins_dir()
    target_dir = os.path.join(pdir, directory)
    if not is_within(pdir, target_dir):
        return web.json_response({'success': False, 'message': '无效目录'}, status=403)
    plugin_path = os.path.join(target_dir, filename)
    if not is_within(pdir, plugin_path):
        return web.json_response({'success': False, 'message': '无效文件名'}, status=403)
    if os.path.exists(plugin_path):
        return web.json_response({'success': False, 'message': '文件已存在'}, status=409)
    await write_text(plugin_path, _PLUGIN_TEMPLATE)
    return web.json_response({'success': True, 'message': '插件已创建', 'path': plugin_path.replace('\\', '/')})


async def handle_create_folder(request: web.Request):
    body = await json_body(request)
    folder_name = body.get('folder_name', '')
    parent_dir = body.get('parent_dir', '')
    if not folder_name:
        return web.json_response({'success': False, 'message': '缺少文件夹名'}, status=400)
    pdir = plugins_dir()
    target = os.path.join(pdir, parent_dir, folder_name) if parent_dir else os.path.join(pdir, folder_name)
    if not is_within(pdir, target):
        return web.json_response({'success': False, 'message': '无效目录'}, status=403)
    if os.path.exists(target):
        return web.json_response({'success': False, 'message': '文件夹已存在'}, status=409)
    await ensure_dir(target)
    return web.json_response({'success': True, 'message': '文件夹已创建'})


async def handle_get_folders(request: web.Request):
    pdir = plugins_dir()
    folders = await run_sync(_visible_folders, pdir)
    return web.json_response({'success': True, 'folders': folders})


# ════════════════ 插件机器人绑定 ════════════════


async def handle_get_plugin_bots(request: web.Request):
    pm = get_pm()
    if not pm:
        return web.json_response({'success': False, 'message': '插件管理器未初始化'}, status=503)
    return web.json_response(
        {
            'success': True,
            'plugin_bots': pm.get_plugin_bots(),
            'bots': _common.connected_ids(),
            'mode': 'all',
        }
    )


async def handle_set_plugin_bots(request: web.Request):
    pm = get_pm()
    if not pm:
        return web.json_response({'success': False, 'message': '插件管理器未初始化'}, status=503)
    body = await json_body(request)
    data = body.get('plugin_bots')
    if not isinstance(data, dict):
        return web.json_response({'success': False, 'message': 'plugin_bots 必须为对象'}, status=400)
    await pm.set_plugin_bots(data)
    return web.json_response({'success': True, 'message': '插件机器人绑定已保存'})


async def handle_plugin_config_files(request: web.Request):
    body = await json_body(request)
    plugin_name = body.get('name', '')
    if not plugin_name:
        return web.json_response({'success': False, 'message': '缺少插件名'}, status=400)
    valid, plugin_dir = validate_path(plugin_name, plugins_dir())
    if not valid or not os.path.isdir(plugin_dir):
        return web.json_response({'success': False, 'message': '无效插件名'}, status=403)
    files = await run_sync(list_config_files, os.path.join(plugin_dir, 'data'))
    return web.json_response({'success': True, 'config_files': files})


# ════════════════ 模块管理 ════════════════


def _read_module_meta(entry_path):
    try:
        with open(entry_path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == '__module_meta__':
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
        result.append(
            {
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
            }
        )
    return result


async def handle_scan_modules(request: web.Request):
    modules = await asyncio.to_thread(_scan_modules)
    return web.json_response({'success': True, 'modules': modules})


async def handle_module_toggle(request: web.Request):
    body = await json_body(request)
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
                await mm.set_module_enabled_persist(name, False)
                return web.json_response({'success': True, 'message': f'模块 {name} 已关闭'})
        if ok:
            verb = '开启' if action == 'enable' else '关闭'
            return web.json_response({'success': True, 'message': f'模块 {name} 已{verb}'})
        return web.json_response({'success': False, 'message': '操作失败'})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)
