"""Web 面板自定义页面/路由注册表 (供插件注册侧边栏页面与 /api/ext/ HTTP 接口)"""

from __future__ import annotations

import inspect

from core.services.files import read_text

_registry: dict = {}  # 页面标识映射到页面信息


def register_page(
    key: str,
    label: str,
    *,
    source: str = 'plugin',
    source_name: str = '',
    html: str = '',
    html_file: str = '',
    icon: str = '',
):
    """注册侧边栏自定义页面 (html 优先于 html_file)"""
    _registry[key] = {
        'key': key,
        'label': label,
        'source': source,
        'source_name': source_name,
        'html': html,
        'html_file': html_file,
        'icon': icon,
    }


def unregister_page(key: str):
    """注销页面"""
    _registry.pop(key, None)


def get_pages() -> list:
    """获取所有已注册页面 (不含 html 内容)"""
    return [{k: v for k, v in p.items() if k not in ('html', 'html_file')} for p in _registry.values()]


async def get_page_html(key: str) -> str | None:
    """获取指定页面的 HTML 内容"""
    info = _registry.get(key)
    if not info:
        return None
    if info.get('html'):
        return str(info['html'])
    path = info.get('html_file')
    if not path:
        return '<p>空页面</p>'
    try:
        return await read_text(path)
    except Exception:
        return '<p style="color:red">页面文件加载失败</p>'


# 自定义 HTTP 路由 (挂 /api/ext/ 前缀, 查表执行, 热重载即时生效; auth=False 开放免验证)
_routes: dict = {}  # 请求方法和路径映射到路由信息
_ROUTE_PREFIX = '/api/ext/'


def register_route(method: str, path: str, handler=None, *, auth: bool = True):
    """注册插件 HTTP 路由 (路径需以 /api/ext/ 开头; 可作装饰器或直接传 handler)"""
    from core.plugins.context import current_plugin

    context = current_plugin()
    owner = context.name
    method = str(method).upper()
    if not path.startswith(_ROUTE_PREFIX):
        raise ValueError(f'插件路由路径必须以 {_ROUTE_PREFIX} 开头: {path}')

    def _add(fn):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f'plugin HTTP route must use async def: {fn.__module__}.{fn.__qualname__}')
        _routes[(method, path)] = {
            'method': method,
            'path': path,
            'handler': fn,
            'auth': bool(auth),
            'owner': owner,
            'context': context,
        }
        return fn

    return _add(handler) if handler is not None else _add


def unregister_route(method: str, path: str):
    """注销路由"""
    _routes.pop((str(method).upper(), path), None)


def match_route(method: str, path: str):
    """精确匹配已注册路由; HEAD 回退到 GET。未命中返回 None。"""
    m = str(method).upper()
    entry = _routes.get((m, path))
    if entry is None and m == 'HEAD':
        entry = _routes.get(('GET', path))
    return entry


def get_routes() -> list:
    """获取所有已注册路由 (不含 handler)"""
    hidden = {'handler', 'context'}
    return [{k: v for k, v in r.items() if k not in hidden} for r in _routes.values()]


def clear_routes_by_owner(owner: str) -> int:
    """注销某插件注册的全部路由 (插件卸载时由框架自动调用); 返回清理数量。"""
    keys = [k for k, v in _routes.items() if v.get('owner') == owner]
    for k in keys:
        _routes.pop(k, None)
    return len(keys)
