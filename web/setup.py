"""Web 面板集成入口"""

import gzip
import logging
import os
import re
import sys

from aiohttp import web

import web.api as _panel_api
import web.auth as _auth
import web.ws as _ws
from core.foundation.archives import is_within
from core.foundation.branding import public_text
from web.protocol import api_protocol_middleware, prepare_response_headers

log = logging.getLogger('ElainaQQ.web')


def _disable_sendfile_on_windows() -> None:
    """在 Windows 上使用 aiohttp 的分块回退，避免 Proactor sendfile 缓冲区复用损坏静态文件。"""
    if sys.platform != 'win32':
        return
    os.environ.setdefault('AIOHTTP_NOSENDFILE', '1')
    try:
        import aiohttp.web_fileresponse as file_response

        file_response.NOSENDFILE = True
    except Exception:
        pass


class _WebPanelLogHandler(logging.Handler):
    """将 Python logging 记录推送到 web 面板 + 持久化到 SQLite"""

    def __init__(self, app_instance):
        super().__init__()
        self._app = app_instance

    def emit(self, record):
        try:
            from datetime import datetime

            # 标记 web_skip 的记录(如消息内容)不进入框架日志面板, 它们另存于消息记录
            if getattr(record, 'web_skip', False):
                return

            msg = public_text(record.getMessage())
            entry = {
                'timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                'content': msg,
                'source': record.name,
                'level': record.levelname,
            }
            _ws.push_log('framework', entry)
            svc = getattr(self._app, '_log_service', None)
            if svc:
                svc.add_nowait('framework', entry)
        except Exception:
            pass


def setup_web(app: web.Application, bot_manager, base_dir: str):
    """将 Web 面板挂载到 aiohttp 应用 (bot_manager 即 Application 实例)"""
    _disable_sendfile_on_windows()
    _auth.init(base_dir)
    _panel_api.set_context(bot_manager, base_dir)
    app.middlewares.append(api_protocol_middleware)
    app.on_response_prepare.append(prepare_response_headers)

    # 注入日志/错误实时推送
    try:
        from core.foundation.logging import on_error

        bot_manager._web_log_cb = _ws.push_log

        def _push_error(error_data):
            _ws.push_log(
                'error',
                {
                    'timestamp': error_data.get('timestamp', ''),
                    'module_type': error_data.get('module_type', ''),
                    'module_name': error_data.get('module_name', ''),
                    'content': public_text(error_data.get('content', '')),
                    'traceback': public_text(error_data.get('traceback', '')),
                },
            )
            svc = getattr(bot_manager, '_log_service', None)
            if svc:
                svc.add(
                    'error',
                    {
                        'timestamp': error_data.get('timestamp', ''),
                        'source': f'{error_data.get("module_type", "")}.{error_data.get("module_name", "")}',
                        'level': 'ERROR',
                        'content': public_text(error_data.get('content', '')),
                        'extra': public_text(error_data.get('traceback', '')),
                    },
                )

        on_error(_push_error)

        _handler = _WebPanelLogHandler(bot_manager)
        _handler.setLevel(logging.INFO)
        logging.getLogger('ElainaQQ').addHandler(_handler)
    except Exception as e:
        log.warning(f'日志推送注入失败: {e}')

    # 面板接口路由
    app.router.add_routes(_panel_api.get_routes())

    # 媒体目录包含聊天内容，只允许已登录的面板读取。
    media_dir = os.path.join(base_dir, 'data', 'media')
    os.makedirs(media_dir, exist_ok=True)
    app.router.add_get('/api/media/{path:.*}', _auth.require_auth(_make_media_handler(media_dir)))

    # 前端构建目录
    _web_dir = os.path.dirname(__file__)
    configured_dist = os.environ.get('ELAINAQQ_WEB_DIST', '').strip()
    if configured_dist:
        configured_dist = os.path.expanduser(configured_dist)
        dist_dir = os.path.abspath(configured_dist if os.path.isabs(configured_dist) else os.path.join(base_dir, configured_dist))
    else:
        dist_dir = os.path.join(_web_dir, 'dist')

    app.router.add_get('/web', _redirect_to_web)

    if os.path.isdir(dist_dir):
        app.router.add_get('/web/{path:.*}', _make_spa_handler(dist_dir))
        source = '外部前端构建目录' if configured_dist else '内置构建产物'
        log.info(f'Web 面板已挂载 ({source}: {dist_dir})')
    else:
        app.router.add_get('/web/{path:.*}', _dev_placeholder)
        log.warning(f'Web 面板未找到编译产物 (期望: {dist_dir})')


_MIME = {
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.html': 'text/html',
    '.json': 'application/json',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
}
# 可压缩的文本资源类型
_COMPRESSIBLE = {'.js', '.css', '.html', '.json', '.svg'}
# 压缩结果内存缓存：文件路径 ->（修改时间，压缩字节）
_gz_cache: dict = {}


def _make_media_handler(media_dir: str):
    """创建带目录边界检查的媒体文件处理器。"""
    media_root = os.path.realpath(media_dir)

    async def handler(request: web.Request):
        relative = request.match_info.get('path', '').replace('/', os.sep)
        file_path = os.path.realpath(os.path.join(media_root, relative))
        if not relative or not is_within(media_root, file_path) or not os.path.isfile(file_path):
            raise web.HTTPNotFound(reason='媒体文件不存在')
        headers = {'Cache-Control': 'private, no-store'}
        content_type = _MIME.get(os.path.splitext(file_path)[1].lower())
        if content_type:
            headers['Content-Type'] = content_type
        return web.FileResponse(file_path, headers=headers)

    return handler


def _gzipped(file_path: str) -> bytes:
    """返回文件的 gzip 压缩字节, 按文件 mtime 缓存, 避免重复压缩"""
    mtime = os.path.getmtime(file_path)
    cached = _gz_cache.get(file_path)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(file_path, 'rb') as f:
        raw = f.read()
    data = gzip.compress(raw, 6)
    _gz_cache[file_path] = (mtime, data)
    return data


def _cache_headers(path: str) -> dict:
    """稳定文件名配合修改时间参数，禁止浏览器混用不同构建。"""
    return {'Cache-Control': 'no-store, no-cache, must-revalidate'}


def _make_spa_handler(dist_dir: str):
    dist_root = os.path.realpath(dist_dir)

    def _versioned_index(file_path: str) -> bytes:
        """为固定资源名追加文件修改时间，避免浏览器使用旧构建。"""
        with open(file_path, encoding='utf-8') as file:
            text = file.read()
        asset_pattern = re.compile(r'((?:/web/)?assets/[^"\'\s?]+)')

        def replace(match):
            url = match.group(1)
            relative = url.split('/assets/', 1)[-1]
            asset_path = os.path.realpath(os.path.join(dist_root, 'assets', relative))
            if not (asset_path == dist_root or asset_path.startswith(dist_root + os.sep)) or not os.path.isfile(asset_path):
                return url
            return f'{url}?v={os.stat(asset_path).st_mtime_ns}'

        return asset_pattern.sub(replace, text).encode('utf-8')

    def _versioned_script(file_path: str) -> bytes:
        """给懒加载脚本的相对 import 也追加对应文件的修改时间。"""
        with open(file_path, encoding='utf-8') as file:
            text = file.read()
        base_dir = os.path.dirname(file_path)
        pattern = re.compile(r'(["\'\x60])((?:\./|assets/)[^"\'\x60?]+?\.(?:js|css))(?:\?[^"\'\x60]*)?\1')

        def replace(match):
            quote, relative = match.groups()
            target = os.path.realpath(os.path.join(dist_root, relative) if relative.startswith('assets/') else os.path.join(base_dir, relative[2:]))
            if not os.path.isfile(target) or not target.startswith(dist_root + os.sep):
                return match.group(0)
            return f'{quote}{relative}?v={os.stat(target).st_mtime_ns}{quote}'

        text = pattern.sub(replace, text)
        # 前端构建代码在创建样式链接前会检查 URL 后缀，因此先剥离查询参数。
        for quote in ('"', "'", '`'):
            old = f'.endsWith({quote}.css{quote})'
            new = f'.split({quote}?{quote})[0].endsWith({quote}.css{quote})'
            text = text.replace(old, new)
        return text.encode('utf-8')

    def _serve(file_path: str, path: str, request: web.Request):
        ext = os.path.splitext(file_path)[1].lower()
        headers = _cache_headers(path)
        ct = _MIME.get(ext)
        if ct:
            headers['Content-Type'] = ct

        accepts_gzip = 'gzip' in request.headers.get('Accept-Encoding', '')
        body_override = _versioned_index(file_path) if path == 'index.html' else (_versioned_script(file_path) if ext == '.js' else None)
        if ext in _COMPRESSIBLE and accepts_gzip:
            try:
                body = gzip.compress(body_override, 6) if body_override is not None else _gzipped(file_path)
                headers['Content-Encoding'] = 'gzip'
                headers['Vary'] = 'Accept-Encoding'
                return web.Response(body=body, headers=headers)
            except Exception:
                pass
        if body_override is not None:
            return web.Response(body=body_override, headers=headers)
        return web.FileResponse(file_path, headers=headers)

    async def handler(request: web.Request):
        path = request.match_info.get('path', '')
        if not path or path == '/':
            path = 'index.html'

        file_path = os.path.realpath(os.path.join(dist_root, path.replace('/', os.sep)))
        if (file_path == dist_root or file_path.startswith(dist_root + os.sep)) and os.path.isfile(file_path):
            return _serve(file_path, path, request)

        index = os.path.join(dist_root, 'index.html')
        if os.path.isfile(index):
            return _serve(index, 'index.html', request)

        return web.Response(text='Not Found', status=404)

    return handler


async def _redirect_to_web(request: web.Request):
    raise web.HTTPFound('/web/')


async def _dev_placeholder(request: web.Request):
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ElainaQQ</title></head>
<body style="background:#fff;color:#333;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center">
<h1 style="color:#5865f2">ElainaQQ 管理面板</h1>
<p style="color:#666">未找到 <code>web/dist/</code> 目录。</p>
</div></body></html>"""
    return web.Response(text=html, content_type='text/html')
