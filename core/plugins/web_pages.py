"""Web 面板自定义页面/路由注册表 (供插件注册侧边栏页面与 /api/ext/ HTTP 接口)"""

from __future__ import annotations

import contextvars
import inspect
from contextlib import contextmanager

from core.services.files import read_text

_registry: dict = {}  # 页面标识映射到页面信息
_resource_stage: contextvars.ContextVar[dict[str, dict] | None] = contextvars.ContextVar(
    'plugin_web_resource_stage',
    default=None,
)


@contextmanager
def resource_registration_scope():
    """把加载期 Web 注册写入独立快照，提交前不影响在线路由。"""
    stage = {'pages': {}, 'routes': {}}
    token = _resource_stage.set(stage)
    try:
        yield stage
    finally:
        _resource_stage.reset(token)


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
    from core.plugins.context import current_plugin

    context = current_plugin()
    stage = _resource_stage.get()
    target = stage['pages'] if stage is not None else _registry
    target[key] = {
        'key': key,
        'label': label,
        'source': source,
        'source_name': source_name,
        'html': html,
        'html_file': html_file,
        'icon': icon,
        'owner': context.name,
    }


def unregister_page(key: str):
    """注销页面"""
    stage = _resource_stage.get()
    target = stage['pages'] if stage is not None else _registry
    target.pop(key, None)


def get_pages() -> list:
    """获取所有已注册页面 (不含 html 内容)"""
    hidden = {'html', 'html_file', 'owner'}
    return [{k: v for k, v in p.items() if k not in hidden} for p in _registry.values()]


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


def register_route(method: str, path: str, handler=None, *, auth: bool = True, timeout: float = 30):
    """注册插件 HTTP 路由 (路径需以 /api/ext/ 开头; 可作装饰器或直接传 handler)"""
    from core.plugins.context import current_plugin

    context = current_plugin()
    owner = context.name
    method = str(method).upper()
    if not path.startswith(_ROUTE_PREFIX):
        raise ValueError(f'插件路由路径必须以 {_ROUTE_PREFIX} 开头: {path}')

    def _add(fn):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f'插件 HTTP 路由必须使用 async def 定义: {fn.__module__}.{fn.__qualname__}')
        stage = _resource_stage.get()
        target = stage['routes'] if stage is not None else _routes
        target[(method, path)] = {
            'method': method,
            'path': path,
            'handler': fn,
            'auth': bool(auth),
            'owner': owner,
            'context': context,
            'timeout': float(timeout),
        }
        return fn

    return _add(handler) if handler is not None else _add


def unregister_route(method: str, path: str):
    """注销路由"""
    stage = _resource_stage.get()
    target = stage['routes'] if stage is not None else _routes
    target.pop((str(method).upper(), path), None)


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


def clear_resources_by_owner(owner: str) -> int:
    """移除指定插件注册的全部页面和路由。"""
    page_keys = [key for key, value in _registry.items() if value.get('owner') == owner]
    for key in page_keys:
        _registry.pop(key, None)
    return len(page_keys) + clear_routes_by_owner(owner)


def snapshot_resources_by_owner(owner: str) -> dict[str, dict]:
    """复制一个插件的 Web 注册项，供热重载提交或回滚。"""
    return {
        'pages': {key: dict(value) for key, value in _registry.items() if value.get('owner') == owner},
        'routes': {key: dict(value) for key, value in _routes.items() if value.get('owner') == owner},
    }


def restore_resources_by_owner(owner: str, snapshot: dict[str, dict]) -> None:
    """用快照替换一个插件当前的 Web 注册项。"""
    clear_resources_by_owner(owner)
    _registry.update(snapshot.get('pages', {}))
    _routes.update(snapshot.get('routes', {}))


def has_resources_by_owner(owner: str) -> bool:
    """判断指定插件是否注册过页面或 HTTP 路由。"""
    stage = _resource_stage.get()
    pages = stage['pages'] if stage is not None else _registry
    routes = stage['routes'] if stage is not None else _routes
    return any(value.get('owner') == owner for value in pages.values()) or any(
        value.get('owner') == owner for value in routes.values()
    )
