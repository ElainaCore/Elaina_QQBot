"""配置文件管理 — settings.yaml 读写 (OneBot)"""

import os

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


async def handle_get_config(request: web.Request):
    cdir = _config_dir()
    result = {'settings': ''}
    for name in _ALLOWED:
        path = os.path.join(cdir, f'{name}.yaml')
        if os.path.exists(path):
            result[name] = await read_text(path)
    return ok(**result)


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

        cdir = _config_dir()
        path = os.path.join(cdir, f'{file_name}.yaml')

        if os.path.exists(path):
            original = await read_text(path)
            await write_text(path + '.bak', original)

        await write_text(path, content)

        # 触发热重载
        from core.foundation.config import cfg

        if not await run_sync(cfg.reload, file_name):
            return error('配置已保存，但重新读取失败；框架继续使用旧配置', status=500)
        result = await _app.apply_config(file_name) if _app else {'restart_required': []}

        restart_required = result.get('restart_required', [])
        message = '配置已保存；部分字段需重启生效' if restart_required else '配置已保存并应用'
        return ok(message=message, restart_required=restart_required)
    except Exception as e:
        return error(str(e), status=500)
