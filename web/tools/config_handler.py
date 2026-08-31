"""配置文件管理 — settings.yaml 读写 (OneBot)"""

import copy
import os
from urllib.parse import urlparse

from aiohttp import web

from core.services.files import read_text, run_sync, write_text
from web.protocol import error, json_body, ok

_base_dir = ''
_app = None
_ALLOWED = ('settings',)


def set_context(app_instance, base_dir: str):
    global _app, _base_dir
    _app = app_instance
    _base_dir = base_dir


def _config_dir():
    return os.path.join(_base_dir, 'config')


def _read_settings_sync(path: str):
    import yaml

    with open(path, encoding='utf-8') as file:
        return yaml.safe_load(file.read()) or {}


def _public_settings(parsed: dict) -> dict:
    """Return a form-safe settings snapshot without hashes or API secrets."""
    result = copy.deepcopy(parsed) if isinstance(parsed, dict) else {}
    web_settings = result.get('web')
    if isinstance(web_settings, dict):
        web_settings.pop('admin_password', None)
    # AI 是插件能力，不属于框架内置配置。旧配置存在时也不暴露到可视化面板。
    result.pop('ai', None)
    # 可视化面板的布尔开关用 !!value 渲染；键缺失会显示为关，
    # 而运行时默认是开。这里显式回填默认值，避免 UI 与行为不一致。
    embedded = result.setdefault('embedded_qq', {})
    if not isinstance(embedded, dict):
        result['embedded_qq'] = embedded = {}
    embedded.setdefault('self_message_enabled', True)
    return result


def _set_path(target: dict, path: str, value):
    parts = [part for part in str(path).split('.') if part]
    if len(parts) != 2 or parts[0] not in {'server', 'web', 'owner', 'embedded_qq', 'logging', 'pip', 'ai'}:
        raise ValueError(f'不允许修改配置项: {path}')
    section, key = parts
    target.setdefault(section, {})
    if not isinstance(target[section], dict):
        target[section] = {}
    allowed = {
        'server': {'host', 'port'},
        'web': {'trust_forwarded_headers', 'framework_name', 'favicon_url'},
        'owner': {'ids'},
        'embedded_qq': {'enabled', 'bridge_port_start', 'command', 'qq_path', 'packet_backend', 'packet_verbose', 'packet_o3_hook', 'data_dir', 'headless', 'single_process', 'rss_target_mb', 'swap_reclaim', 'self_message_enabled'},
        'logging': {'dir', 'insert_interval', 'max_batch_size', 'max_queue_entries', 'retention_days', 'wal_mode'},
        'pip': {'auto_install', 'mirror'},
        # 仅保留旧插件配置的读写兼容性；框架本身不加载 AI 服务。
        'ai': {'enabled', 'base_url', 'model', 'temperature', 'max_iterations', 'request_timeout', 'system_prompt'},
    }
    if key not in allowed[section]:
        raise ValueError(f'不允许修改配置项: {path}')

    boolean_fields = {
        ('web', 'trust_forwarded_headers'),
        ('embedded_qq', 'enabled'),
        ('embedded_qq', 'packet_verbose'),
        ('embedded_qq', 'packet_o3_hook'),
        ('embedded_qq', 'headless'),
        ('embedded_qq', 'single_process'),
        ('embedded_qq', 'swap_reclaim'),
        ('embedded_qq', 'self_message_enabled'),
        ('logging', 'wal_mode'),
        ('pip', 'auto_install'),
        ('ai', 'enabled'),
    }
    integer_fields = {
        ('server', 'port'),
        ('embedded_qq', 'bridge_port_start'),
        ('embedded_qq', 'rss_target_mb'),
        ('logging', 'max_batch_size'),
        ('logging', 'max_queue_entries'),
        ('logging', 'retention_days'),
        ('ai', 'max_iterations'),
    }
    number_fields = {
        ('logging', 'insert_interval'),
        ('ai', 'temperature'),
        ('ai', 'request_timeout'),
    }
    string_fields = {
        ('server', 'host'),
        ('web', 'framework_name'),
        ('web', 'favicon_url'),
        ('embedded_qq', 'command'),
        ('embedded_qq', 'qq_path'),
        ('embedded_qq', 'packet_backend'),
        ('embedded_qq', 'data_dir'),
        ('logging', 'dir'),
        ('pip', 'mirror'),
        ('ai', 'base_url'),
        ('ai', 'model'),
        ('ai', 'system_prompt'),
    }
    if (section, key) in boolean_fields:
        if not isinstance(value, bool):
            raise ValueError(f'{path} 必须是布尔值')
    elif (section, key) in integer_fields:
        if isinstance(value, bool):
            raise ValueError(f'{path} 必须是整数')
        value = int(value)
    elif (section, key) in number_fields:
        if isinstance(value, bool):
            raise ValueError(f'{path} 必须是数字')
        value = float(value)
    elif (section, key) in string_fields:
        if not isinstance(value, str):
            raise ValueError(f'{path} 必须是字符串')

    if section == 'server' and key == 'port':
        if not 1 <= value <= 65535:
            raise ValueError('服务端口必须在 1-65535 之间')
    if section == 'embedded_qq' and key == 'bridge_port_start' and not 1 <= value <= 65535:
        raise ValueError('QQ 桥接端口必须在 1-65535 之间')
    positive_integer_fields = {
        ('logging', 'max_batch_size'),
        ('logging', 'max_queue_entries'),
        ('logging', 'retention_days'),
        ('ai', 'max_iterations'),
    }
    if (section, key) == ('embedded_qq', 'rss_target_mb') and value < 0:
        raise ValueError('embedded_qq.rss_target_mb 不能小于 0')
    if (section, key) in positive_integer_fields and value < 1:
        raise ValueError(f'{path} 必须大于 0')
    if (section, key) in number_fields and value < 0:
        raise ValueError(f'{path} 不能小于 0')
    if section == 'ai' and key == 'temperature' and value > 2:
        raise ValueError('ai.temperature 必须在 0-2 之间')
    if section == 'ai' and key == 'request_timeout' and value <= 0:
        raise ValueError('ai.request_timeout 必须大于 0')
    if section == 'owner' and key == 'ids':
        if not isinstance(value, list):
            raise ValueError('主人 QQ 列表必须是数组')
        value = [str(item).strip() for item in value if str(item).strip()]
    if section == 'web' and key == 'favicon_url':
        value = str(value).strip()
    target[section][key] = value


async def _save_parsed_settings(parsed: dict):
    import yaml

    cdir = _config_dir()
    path = os.path.join(cdir, 'settings.yaml')
    original = await read_text(path) if os.path.exists(path) else ''
    if original:
        await write_text(path + '.bak', original)
    content = yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False, default_flow_style=False)
    await write_text(path, content)
    from core.foundation.config import cfg
    if not await run_sync(cfg.reload, 'settings'):
        return error('配置已保存，但重新读取失败；框架继续使用旧配置', status=500)
    applied = await _app.apply_config('settings') if _app else {'restart_required': []}
    restart_required = applied.get('restart_required', [])
    message = '配置已保存；部分字段需重启生效' if restart_required else '配置已保存并应用'
    return ok(message=message, restart_required=restart_required, values=_public_settings(parsed))


async def handle_get_config(request: web.Request):
    cdir = _config_dir()
    result = {'settings': ''}
    for name in _ALLOWED:
        path = os.path.join(cdir, f'{name}.yaml')
        if os.path.exists(path):
            result[name] = await read_text(path)
            if name == 'settings':
                try:
                    parsed = await run_sync(_read_settings_sync, path)
                    result['values'] = _public_settings(parsed)
                except Exception:
                    result['values'] = {}
    return ok(**result)


async def handle_save_visual_config(request: web.Request):
    import yaml

    body = await json_body(request)
    patch = body.get('patch')
    if not isinstance(patch, dict):
        return error('可视化配置必须是对象')
    path = os.path.join(_config_dir(), 'settings.yaml')
    if not os.path.exists(path):
        return error('settings.yaml 不存在', status=404)
    try:
        parsed = await run_sync(_read_settings_sync, path)
        if not isinstance(parsed, dict):
            return error('配置根节点必须是对象')
        for key, value in patch.items():
            _set_path(parsed, key, value)
        return await _save_parsed_settings(parsed)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        return error(str(exc), status=400)
    except Exception as exc:
        return error(str(exc), status=500)


async def handle_save_config(request: web.Request):
    body = await json_body(request)
    try:
        file_name = body.get('file', '')
        content = body.get('content', '')
        if file_name not in _ALLOWED:
            return error('无效的配置文件名')
        if not content:
            return error('内容不能为空')

        # 校验 YAML 合法
        import yaml

        try:
            parsed = await run_sync(yaml.safe_load, content)
        except yaml.YAMLError as e:
            return error(f'YAML 格式错误: {e}')
        if not isinstance(parsed, dict):
            return error('YAML 根节点必须是对象')

        if file_name == 'settings':
            return await _save_parsed_settings(parsed)
        cdir = _config_dir()
        path = os.path.join(cdir, f'{file_name}.yaml')
        if os.path.exists(path):
            original = await read_text(path)
            await write_text(path + '.bak', original)
        await write_text(path, content)
        from core.foundation.config import cfg
        if not await run_sync(cfg.reload, file_name):
            return error('配置已保存，但重新读取失败；框架继续使用旧配置', status=500)
        result = await _app.apply_config(file_name) if _app else {'restart_required': []}
        restart_required = result.get('restart_required', [])
        message = '配置已保存；部分字段需重启生效' if restart_required else '配置已保存并应用'
        return ok(message=message, restart_required=restart_required)
    except Exception as e:
        return error(str(e), status=500)
