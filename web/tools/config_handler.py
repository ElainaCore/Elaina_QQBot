"""配置文件管理 — settings.yaml 读写 (OneBot)"""

import os

from aiohttp import web

from web.protocol import error, json_body, ok

_base_dir = ''
_ALLOWED = ('settings',)


def set_context(base_dir: str):
    global _base_dir
    _base_dir = base_dir


def _config_dir():
    return os.path.join(_base_dir, 'config')


async def handle_get_config(request: web.Request):
    cdir = _config_dir()
    result = {'settings': ''}
    for name in _ALLOWED:
        path = os.path.join(cdir, f'{name}.yaml')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                result[name] = f.read()
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
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return error(f'YAML 格式错误: {e}')

        cdir = _config_dir()
        path = os.path.join(cdir, f'{file_name}.yaml')

        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                original = f.read()
            with open(path + '.bak', 'w', encoding='utf-8') as fb:
                fb.write(original)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 触发热重载
        from core.base.config import cfg

        cfg.reload(file_name)

        return ok(message='配置已保存')
    except Exception as e:
        return error(str(e), status=500)
