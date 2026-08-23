"""HTTP 服务器 — 基于 aiohttp"""

import asyncio
import contextlib
import json
import time

from aiohttp import web

from core.base.branding import public_text
from core.base.config import cfg
from core.base.logger import SYSTEM, get_logger

log = get_logger(SYSTEM, 'HTTP')

_MAX_REQUEST_SIZE = 132 * 1024 * 1024


def _local_port(request: web.Request):
    """获取该请求实际进入的本地监听端口 (用于按连接区分鉴权)"""
    try:
        sock = request.transport.get_extra_info('sockname') if request.transport else None
        if sock and len(sock) >= 2:
            return int(sock[1])
    except Exception:
        pass
    return request.url.port


class HttpServer:
    """aiohttp HTTP 服务器"""

    def __init__(self, app_instance, base_dir: str):
        self._app_instance = app_instance
        self._base_dir = base_dir
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._request_total = 0
        self._request_active = 0
        self._request_last_time = time.monotonic()
        self._request_last_total = 0

    @property
    def app(self) -> web.Application:
        if self._app is None:
            raise RuntimeError('HTTP 应用尚未初始化')
        return self._app

    def init_app(self):
        """初始化 aiohttp 应用"""
        self._app = web.Application(
            middlewares=[self._metrics_middleware, self._public_response_middleware],
            client_max_size=_MAX_REQUEST_SIZE,
        )

        # OneBot HTTP 事件回调
        self._app.router.add_post('/', self._handle_onebot_http)
        self._app.router.add_post('/onebot/v11/', self._handle_onebot_http)
        self._app.router.add_post('/onebot/v11/http', self._handle_onebot_http)
        self._app.router.add_post('/OneBotv11', self._handle_onebot_http)

        # OneBot 长连接
        self._app.router.add_get('/onebot/v11/', self._handle_onebot_ws)
        self._app.router.add_get('/onebot/v11/ws', self._handle_onebot_ws)
        self._app.router.add_get('/OneBotv11', self._handle_onebot_ws)

        # 健康检查
        self._app.router.add_get('/health', self._handle_health)

    @web.middleware
    async def _metrics_middleware(self, request: web.Request, handler):
        self._request_active += 1
        try:
            return await handler(request)
        finally:
            self._request_active = max(0, self._request_active - 1)
            self._request_total += 1

    @staticmethod
    @web.middleware
    async def _public_response_middleware(request: web.Request, handler):
        """清除公开文本响应中的底层依赖实现名称。"""
        try:
            response = await handler(request)
        except web.HTTPException as error:
            error.text = public_text(error.text)
            raise
        if not isinstance(response, web.Response) or response.body is None:
            return response
        if response.content_type not in {'application/json', 'text/plain', 'text/html'}:
            return response
        if response.headers.get('Content-Encoding'):
            return response
        charset = response.charset or 'utf-8'
        try:
            original = response.body.decode(charset)
        except (AttributeError, LookupError, UnicodeDecodeError):
            return response
        sanitized = public_text(original)
        if sanitized != original:
            response.body = sanitized.encode(charset)
        return response

    def request_metrics(self) -> dict:
        now = time.monotonic()
        elapsed = max(now - self._request_last_time, 0.1)
        rate = max(self._request_total - self._request_last_total, 0) / elapsed
        self._request_last_time = now
        self._request_last_total = self._request_total
        return {
            'total': self._request_total,
            'active': self._request_active,
            'rate': round(rate, 2),
        }

    def mount_web_panel(self):
        """挂载 Web 面板"""
        if self._app is None:
            raise RuntimeError('HTTP 应用尚未初始化')
        try:
            from web.setup import setup_web

            setup_web(self._app, self._app_instance, self._base_dir)
        except Exception as e:
            log.error(f'Web 面板挂载失败: {e}')

    async def start(self, bind_timeout: float = 15, retry_interval: float = 0.5):
        """启动 HTTP 服务器，端口短暂占用时在限定时间内重试。"""
        if self._app is None:
            raise RuntimeError('HTTP 应用尚未初始化')
        host = cfg.get('settings', 'server.host', '0.0.0.0')
        port = cfg.get('settings', 'server.port', 5201)

        self._runner = web.AppRunner(self._app, shutdown_timeout=3)
        await self._runner.setup()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0, bind_timeout)
        first_failure = True
        while True:
            try:
                site = web.TCPSite(self._runner, host, port, reuse_address=True)
                await site.start()
                self._site = site
                break
            except OSError as error:
                if loop.time() >= deadline:
                    await self._runner.cleanup()
                    self._runner = None
                    raise RuntimeError(f'HTTP 端口绑定失败: {host}:{port}') from error
                if first_failure:
                    log.warning('端口 %s:%s 暂不可用，等待旧进程释放', host, port)
                    first_failure = False
                await asyncio.sleep(max(0.05, retry_interval))

        log.info(f'HTTP 服务器启动: {host}:{port}')
        log.info(f'OneBot: ws://{host}:{port}/OneBotv11')
        log.info(f'Web: http://{host}:{port}/web/')

    async def stop(self, timeout: float = 5):
        """停止服务器: 先主动断开所有长连接 (OneBot 反向 WS / 面板 WS/SSE) 再清理, 避免卡住"""
        adapter = getattr(self._app_instance, 'adapter', None)
        if adapter:
            for ws in list(getattr(adapter, 'websockets', {}).values()):
                with contextlib.suppress(Exception):
                    await ws.close(code=1001, message=b'Server shutdown')
        with contextlib.suppress(Exception):
            from web.ws import get_broadcast

            get_broadcast().shutdown()
        if self._site:
            with contextlib.suppress(Exception):
                await self._site.stop()
        if self._runner:
            try:
                async with asyncio.timeout(timeout):
                    await self._runner.cleanup()
            except (TimeoutError, Exception):
                log.warning('HTTP 关闭超时, 强制结束')
        self._site = None
        self._runner = None

    async def _handle_onebot_http(self, request: web.Request):
        """处理 OneBot HTTP 回调"""
        adapter = self._app_instance.adapter
        if not adapter:
            return web.Response(status=503)

        body = await request.read()
        if not body:
            return web.Response(status=400)

        port, path = _local_port(request), request.path
        success, event = adapter.handle_http_callback(body, dict(request.headers), port=port, path=path)
        if event:
            self._app_instance.submit_event(event)

        return web.Response(status=204)

    async def _handle_onebot_ws(self, request: web.Request):
        """处理 OneBot WebSocket 连接"""
        from core.onebot.api import set_main_loop

        set_main_loop(asyncio.get_running_loop())

        adapter = self._app_instance.adapter
        if not adapter:
            return web.Response(status=503)

        headers = dict(request.headers)
        valid, self_id, error = adapter.validate_websocket_headers(headers, port=_local_port(request), path=request.path)
        if not valid:
            return web.Response(status=401, text=error or 'Unauthorized')

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        adapter.register_bot(self_id, ws)
        embedded_id = str(request.query.get('embedded_id') or '').strip()
        embedded = getattr(self._app_instance, 'embedded_qq', None)
        if embedded and embedded_id:
            embedded.on_onebot_connected(embedded_id, self_id)
        log.info(f'OneBot 连接: {request.remote} | Bot {self_id}')

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        event = adapter.parse_event(data)
                        if event:
                            self._app_instance.submit_event(event)
                        elif 'echo' in data and data['echo'] in adapter.api_responses:
                            future = adapter.api_responses.pop(data['echo'])
                            if not future.done():
                                future.set_result(data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            removed = adapter.unregister_bot(self_id, ws)
            if removed and embedded and embedded_id:
                embedded.on_onebot_disconnected(embedded_id, self_id)
            log.info(f'OneBot 断开: Bot {self_id}')

        return ws

    async def _handle_health(self, request: web.Request):
        return web.json_response({'status': 'ok'})
