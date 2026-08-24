"""OneBot 正向、反向和 HTTP 连接管理器。"""

import asyncio
import contextlib
import json
import logging
import uuid
from enum import StrEnum

import aiohttp
from aiohttp import web

from core.base.config import cfg

logger = logging.getLogger('ElainaQQ.onebot.connection')


class ConnType(StrEnum):
    """OneBot 连接类型"""

    WS_REVERSE = 'ws_reverse'
    WS_FORWARD = 'ws_forward'
    HTTP_SERVER = 'http_server'
    HTTP_CLIENT = 'http_client'


CONN_TYPES = tuple(ConnType)


def default_connections():
    """默认不生成任何连接示例 (主服务端口始终提供 /OneBotv11 反向 WS 入口)"""
    return []


def normalize(conn: dict) -> dict:
    """补全连接配置的缺省字段"""
    c = dict(conn or {})
    c.setdefault('type', ConnType.WS_REVERSE)
    c.setdefault('name', c['type'])
    c['enable'] = bool(c.get('enable', False))
    c.setdefault('host', cfg.get('settings', 'server.host', '0.0.0.0'))
    c.setdefault('port', cfg.get('settings', 'server.port', 5201))
    c.setdefault('path', '/OneBotv11')
    c.setdefault('url', '')
    c.setdefault('token', '')
    c.setdefault('secret', '')
    c.setdefault('reconnect_interval', 5000)
    return c


class ConnectionManager:
    """维护 OneBot 连接 (正向 WS 客户端 + HTTP 客户端 + 反向服务器鉴权 + 自定义端口监听)"""

    def __init__(self, app):
        self._app = app
        self._adapter = app.adapter
        self._loop = None
        self._tasks = {}  # 连接名称映射到正向连接任务
        self._status = {}  # 连接名称映射到运行状态
        self._forward_ids = set()  # 正向连接占用的账号标识，包含临时标识
        self._configs = []
        self._stopping = False
        self._reloading = False
        self._sites = {}  # 监听地址映射到运行器和站点
        self._client_session: aiohttp.ClientSession | None = None
        self._lifecycle_lock = asyncio.Lock()

    # ── 配置 ──
    def load_configs(self):
        conns = cfg.get('connections', 'connections', None)
        if not conns or not isinstance(conns, list):
            conns = default_connections()
        self._configs = [normalize(c) for c in conns if isinstance(c, dict)]
        return self._configs

    @property
    def configs(self):
        return self._configs

    def _main_addr(self):
        return (cfg.get('settings', 'server.host', '0.0.0.0'), int(cfg.get('settings', 'server.port', 5201)))

    # ── 启动 / 停止 ──
    async def start(self):
        async with self._lifecycle_lock:
            self._loop = asyncio.get_running_loop()
            self._stopping = False
            self.load_configs()
            self._apply_server_auth()
            self._register_http_clients()
            await self._start_listeners()
            await self._start_forward_clients()

    async def stop(self):
        async with self._lifecycle_lock:
            self._stopping = True
            await self._close_reverse_ws()
            await self._cancel_forward_clients()
            await self._stop_listeners()
            if self._client_session is not None and not self._client_session.closed:
                await self._client_session.close()
            self._client_session = None

    async def _close_reverse_ws(self):
        """主动关闭已接入的反向 WS, 避免监听端口清理时等待空闲超时"""
        for sid in [k for k in list(self._adapter.websockets) if not str(k).startswith('forward:') and k not in self._forward_ids]:
            ws = self._adapter.websockets.get(sid)
            if ws is not None:
                with contextlib.suppress(Exception):
                    await ws.close(code=1001, message=b'Server shutdown')
                # 热重载必须立即清除账号状态，不能依赖连接处理协程稍后执行 finally。
                self._adapter.unregister_bot(sid, ws)

    async def reload(self):
        """配置变更后重新应用 (重启正向客户端 / 自定义监听 + 刷新鉴权/HTTP 客户端)"""
        async with self._lifecycle_lock:
            self._reloading = True
            try:
                await self._cancel_forward_clients()
                await self._close_reverse_ws()
                self._clear_http_bot_state()
                await self._stop_listeners()
                self.load_configs()
                self._apply_server_auth()
                self._register_http_clients()
                self._stopping = False
                await self._start_listeners()
                await self._start_forward_clients()
            finally:
                self._reloading = False

    def _clear_http_bot_state(self) -> None:
        """清除无长连接可触发断开回调的 HTTP 上报账号状态。"""
        for self_id, record in list(self._adapter.bots.items()):
            if record.get('type') == 'http':
                self._adapter.unregister_bot(self_id)

    @staticmethod
    def _normalize_path(path: str) -> str:
        normalized = '/' + str(path or '/').strip('/')
        return normalized if normalized != '//' else '/'

    def server_connection_enabled(self, connection_type: ConnType, port: int | None, path: str) -> bool:
        """判断外部 OneBot 服务端入口是否已在网络接入中启用。"""
        if self._stopping or self._reloading or port is None:
            return False
        requested_path = self._normalize_path(path)
        _main_host, main_port = self._main_addr()
        for connection in self._configs:
            if not connection.get('enable') or connection.get('type') != connection_type:
                continue
            configured_port = int(connection.get('port') or main_port)
            configured_path = self._normalize_path(connection.get('path') or '/')
            if configured_port == int(port) and configured_path == requested_path:
                return True
        return False

    # ── 反向服务器鉴权 (按连接区分: 每条反向 WS/HTTP 上报各自的 token/secret) ──
    def _apply_server_auth(self):
        main_host, main_port = self._main_addr()
        ws_tokens, http_secrets = {}, {}
        for c in self._configs:
            if not c.get('enable'):
                continue
            port = int(c.get('port') or main_port)
            path = str(c.get('path') or '/') or '/'
            if c['type'] == ConnType.WS_REVERSE:
                ws_tokens[(port, path)] = c.get('token', '') or ''
            elif c['type'] == ConnType.HTTP_SERVER:
                http_secrets[(port, path)] = c.get('secret', '') or ''
        self._adapter.reverse_ws_tokens = ws_tokens
        self._adapter.reverse_http_secrets = http_secrets

    # ── HTTP 客户端 ──
    def _register_http_clients(self):
        self._adapter.clear_http_clients()
        for c in self._configs:
            if c.get('enable') and c['type'] == ConnType.HTTP_CLIENT and c.get('url'):
                self._adapter.register_http_client(c['name'], c['url'], c.get('token', ''))

    # ── 自定义端口监听 (反向 WS / HTTP 上报) ──
    async def _start_listeners(self):
        """为监听地址与主服务不同的反向 WS / HTTP 上报连接启动独立监听端口"""
        http_server = getattr(self._app, '_http_server', None)
        if not http_server:
            return
        main_host, main_port = self._main_addr()
        # 按监听地址分组，同一端口可以挂载多条路径。
        groups = {}
        for c in self._configs:
            if not c.get('enable') or c['type'] not in (ConnType.WS_REVERSE, ConnType.HTTP_SERVER):
                continue
            host = str(c.get('host') or main_host)
            port = int(c.get('port') or main_port)
            if (host, port) == (main_host, main_port):
                # 主服务端口已内置 OneBot 路由，无需重复监听。
                self._set_status(c['name'], connected=False, error='', self_id=None)
                continue
            groups.setdefault((host, port), []).append(c)

        for (host, port), conns in groups.items():
            try:
                app = web.Application()
                seen = set()
                for c in conns:
                    path = str(c.get('path') or '/') or '/'
                    if c['type'] == ConnType.WS_REVERSE:
                        key = ('GET', path)
                        if key not in seen:
                            app.router.add_get(path, http_server._handle_onebot_ws)
                            seen.add(key)
                    else:  # HTTP 上报服务
                        key = ('POST', path)
                        if key not in seen:
                            app.router.add_post(path, http_server._handle_onebot_http)
                            seen.add(key)
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host, port)
                await site.start()
                self._sites[(host, port)] = (runner, site)
                for c in conns:
                    self._set_status(c['name'], connected=False, error='', self_id=None)
                logger.info(f'OneBot 自定义监听启动: {host}:{port} ({", ".join(c["name"] for c in conns)})')
            except Exception as e:
                logger.warning(f'自定义监听启动失败 [{host}:{port}]: {e}')
                for c in conns:
                    self._set_status(c['name'], connected=False, error=f'监听失败: {e}', self_id=None)

    async def _stop_listeners(self):
        for runner, site in list(self._sites.values()):
            with contextlib.suppress(Exception):
                await site.stop()
            with contextlib.suppress(Exception):
                await runner.cleanup()
        self._sites.clear()

    # ── 正向 WS 客户端 ──
    async def _start_forward_clients(self):
        for c in self._configs:
            if c.get('enable') and c['type'] == ConnType.WS_FORWARD and c.get('url'):
                name = c['name']
                self._tasks[name] = asyncio.create_task(self._forward_loop(c))

    async def _cancel_forward_clients(self):
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks.clear()

    async def _forward_loop(self, conn: dict):
        name = conn['name']
        url = conn['url']
        token = conn.get('token', '')
        interval = max(1.0, float(conn.get('reconnect_interval') or 5000) / 1000.0)
        headers = {}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        temp_id = f'forward:{name}'

        while not self._stopping:
            conn['_self_id'] = None
            probe_task = None
            active_ws = None
            try:
                self._set_status(name, connected=False, error='连接中…')
                session = await self._get_client_session()
                async with session.ws_connect(url, headers=headers, heartbeat=30) as ws:
                    active_ws = ws
                    self._adapter.register_bot(temp_id, ws)
                    conn['_self_id'] = temp_id
                    self._forward_ids.add(temp_id)
                    self._set_status(name, connected=True, error='', self_id=temp_id)
                    logger.info(f'正向 WS 已连接: {name} -> {url}')
                    # 主动探测真实账号，即使事件从其他通道上报也能正确归属。
                    probe_task = asyncio.create_task(self._probe_self_id(conn, ws))
                    await self._consume(ws, conn)
            except asyncio.CancelledError:
                self._set_status(name, connected=False, error='已停止')
                raise
            except Exception as e:
                logger.warning(f'正向 WS 连接异常 [{name}]: {e}')
                self._set_status(name, connected=False, error=str(e))
            finally:
                if probe_task:
                    probe_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await probe_task
                self._cleanup_forward(conn, active_ws)
            if self._stopping:
                break
            await asyncio.sleep(interval)

    async def _get_client_session(self) -> aiohttp.ClientSession:
        """复用正向 WebSocket 客户端会话，降低断线重连时的建连开销。"""
        if self._client_session is None or self._client_session.closed:
            self._client_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
                connector=aiohttp.TCPConnector(limit=32, limit_per_host=16, ttl_dns_cache=300),
                headers={'User-Agent': 'ElainaQQ/1.0'},
            )
        return self._client_session

    async def _probe_self_id(self, conn, ws):
        """连接后查询登录信息，并将临时标识替换为真实账号。"""
        adapter = self._adapter
        echo = f'probe:{conn["name"]}:{uuid.uuid4().hex[:8]}'
        fut = self._loop.create_future()
        adapter.register_api_response(echo, fut, ws)
        try:
            send = getattr(ws, 'send_str', None) or ws.send_text
            await send(json.dumps({'action': 'get_login_info', 'params': {}, 'echo': echo}))
            async with asyncio.timeout(10):
                resp = await fut
            uid = str(((resp or {}).get('data') or {}).get('user_id') or '')
            if uid and conn.get('_self_id') != uid:
                self._rekey_forward(conn, uid, ws)
                self._set_status(conn['name'], connected=True, error='', self_id=uid)
        except (TimeoutError, aiohttp.ClientError, TypeError, ValueError):
            pass
        finally:
            adapter.discard_api_response(echo)

    async def _consume(self, ws, conn):
        adapter = self._adapter
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(data, dict):
                    continue
                echo = data.get('echo')
                if echo and adapter.resolve_api_response(echo, data):
                    continue
                sid = str(data.get('self_id') or '')
                if not sid and str(conn.get('_self_id') or '').startswith('forward:'):
                    sid = ''
                elif not sid:
                    sid = str(conn.get('_self_id') or '')
                if sid and conn.get('_self_id') != sid:
                    self._rekey_forward(conn, sid, ws)
                    self._set_status(conn['name'], connected=True, error='', self_id=sid)
                if not await self._app.ingest_event(data, sid):
                    logger.warning('拒绝无效或无法入队的 OneBot 正向 WebSocket 事件: %s', conn['name'])
                    continue
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                break

    def _rekey_forward(self, conn, real_id, ws):
        old = conn.get('_self_id')
        if old and old != real_id:
            self._adapter.unregister_bot(old, ws, cancel_responses=False)
            self._forward_ids.discard(old)
        self._adapter.register_bot(real_id, ws)
        self._forward_ids.add(real_id)
        conn['_self_id'] = real_id

    def _cleanup_forward(self, conn, ws=None):
        sid = conn.get('_self_id')
        if sid:
            self._adapter.unregister_bot(sid, ws)
            self._forward_ids.discard(sid)
        conn['_self_id'] = None

    # ── 状态 ──
    def _set_status(self, name, connected, error='', self_id=None):
        self._status[name] = {'connected': bool(connected), 'error': error or '', 'self_id': self_id}

    def status(self):
        """返回各连接的运行状态"""
        result = []
        for c in self._configs:
            name = c['name']
            ctype = c['type']
            entry = {'name': name, 'type': ctype, 'enable': c.get('enable', False), 'connected': False, 'self_id': None, 'error': ''}
            if ctype == ConnType.WS_FORWARD:
                st = self._status.get(name, {})
                entry['connected'] = c.get('enable', False) and st.get('connected', False)
                entry['self_id'] = st.get('self_id')
                entry['error'] = st.get('error', '')
            elif ctype == ConnType.WS_REVERSE:
                # 排除正向连接占用的账号标识，只统计真正接入的反向连接。
                reverse_ids = [k for k in self._adapter.websockets if not str(k).startswith('forward:') and k not in self._forward_ids]
                entry['connected'] = c.get('enable', False) and bool(reverse_ids)
                entry['self_id'] = reverse_ids[0] if reverse_ids else None
                entry['error'] = self._status.get(name, {}).get('error', '')
            elif ctype == ConnType.HTTP_CLIENT:
                entry['connected'] = c.get('enable', False) and (c['name'] in self._adapter.http_clients)
            elif ctype == ConnType.HTTP_SERVER:
                entry['connected'] = c.get('enable', False)
                entry['error'] = self._status.get(name, {}).get('error', '')
            result.append(entry)
        return result
