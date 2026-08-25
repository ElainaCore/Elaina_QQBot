"""WebSocket 管理 — 实时推送日志/系统状态"""

import asyncio
import contextlib
import json
import logging
from collections import deque
from datetime import datetime

from aiohttp import WSMsgType, web

import web.auth as auth

log = logging.getLogger('ElainaQQ.web.ws')

_MAX_PENDING_BROADCASTS = 1024


# ==================== 长连接广播器 ====================


class WSBroadcast:
    """WebSocket/SSE 广播管理 (封装模块级全局状态)"""

    def __init__(self):
        self._clients: set = set()
        self._sse_queues: set = set()
        self._pending = deque(maxlen=_MAX_PENDING_BROADCASTS)
        self._drain_task: asyncio.Task | None = None

    @property
    def clients(self):
        return self._clients

    @property
    def sse_queues(self):
        return self._sse_queues

    def has_clients(self) -> bool:
        return bool(self._clients or self._sse_queues)

    async def broadcast(self, msg_type: str, data: dict):
        """向所有连接的面板客户端广播消息 (WS + SSE)"""
        if not self.has_clients():
            return
        payload = json.dumps({'type': msg_type, 'data': data}, ensure_ascii=False, default=str)

        # 并发发送并限制单客户端等待时间，避免慢连接阻塞全部面板。
        async def send_one(ws):
            try:
                async with asyncio.timeout(2):
                    await ws.send_str(payload)
                return None
            except Exception:
                return ws

        if self._clients:
            results = await asyncio.gather(*(send_one(ws) for ws in tuple(self._clients)))
            self._clients.difference_update(ws for ws in results if ws is not None)
        # 服务器推送事件
        for q in list(self._sse_queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # 状态流优先保留新数据，淘汰最旧的一条积压消息。
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(payload)

    def schedule_broadcast(self, msg_type: str, data: dict):
        """使用有界单消费者队列调度广播，避免突发日志无限创建任务。"""
        if not self.has_clients():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._pending.append((msg_type, data))
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = loop.create_task(self._drain_broadcasts())

    async def _drain_broadcasts(self):
        """按入队顺序发送广播；队列满时由 deque 自动淘汰最旧状态。"""
        try:
            while self._pending:
                msg_type, data = self._pending.popleft()
                await self.broadcast(msg_type, data)
        finally:
            self._drain_task = None

    def push_log(self, log_type: str, entry: dict):
        """实时推送日志到面板 (不缓存, 仅广播)"""
        if 'timestamp' not in entry:
            entry['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.schedule_broadcast('new_log', {'log_type': log_type, **entry})

    def push_system_info(self, data: dict):
        """推送系统信息更新"""
        self.schedule_broadcast('system_info', data)

    def clear(self):
        """清理所有连接 (用于测试隔离)"""
        self._clients.clear()
        self._sse_queues.clear()
        self._pending.clear()
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self._drain_task = None

    def shutdown(self):
        """服务器关闭时主动断开所有面板连接，避免阻塞 aiohttp runner.shutdown()

        WebSocket：发送关闭帧（代码 1001，服务离开）。
        SSE：清空队列集合，处理器会在下一次队列操作时自然退出。
        """
        for ws in list(self._clients):
            with contextlib.suppress(Exception, RuntimeError):
                asyncio.get_running_loop().create_task(ws.close(code=1001, message='服务关闭'.encode()))
        self._clients.clear()
        self._sse_queues.clear()
        self._pending.clear()
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self._drain_task = None


# 模块级单例
_broadcast = WSBroadcast()


def get_broadcast() -> WSBroadcast:
    """获取广播管理器单例"""
    return _broadcast


def reset_broadcast():
    """重置广播管理器 (用于测试)"""
    global _broadcast
    _broadcast.clear()
    _broadcast = WSBroadcast()
    return _broadcast


# ==================== 模块级兼容函数 ====================


async def broadcast(msg_type: str, data: dict):
    """向所有连接的面板客户端广播消息 (WS + SSE)"""
    await _broadcast.broadcast(msg_type, data)


def push_log(log_type: str, entry: dict):
    """实时推送日志到面板"""
    _broadcast.push_log(log_type, entry)


def push_system_info(data: dict):
    """推送系统信息更新"""
    _broadcast.push_system_info(data)


# ==================== WebSocket 处理器 ====================


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    """面板 WebSocket 端点。"""
    if not auth.validate_token(request) or not auth.is_same_origin(request):
        return web.Response(status=401, text='未授权')  # type: ignore[return-value]  # 升级连接前的鉴权失败

    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    _broadcast.clients.add(ws)
    log.debug(f'面板 WebSocket 已连接（{len(_broadcast.clients)} 个客户端）')

    try:
        # 通知前端已连接, 初始数据由前端通过 API 获取
        await ws.send_json({'type': 'init', 'data': {}})

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await _handle_client_msg(ws, data)
                except json.JSONDecodeError:
                    pass
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    finally:
        _broadcast.clients.discard(ws)
        log.debug(f'面板 WebSocket 已断开（{len(_broadcast.clients)} 个客户端）')

    return ws


async def _handle_client_msg(ws: web.WebSocketResponse, data: dict):
    """处理客户端发来的消息"""
    pass


# ==================== SSE 降级通道 ====================


async def handle_sse(request: web.Request) -> web.StreamResponse:
    """SSE 降级端点。

    当 WebSocket 因 Nginx 未配置 upgrade 等原因不可用时,
    前端自动降级到 SSE, 走普通 HTTP 无需特殊代理配置。
    """
    if not auth.validate_token(request) or not auth.is_same_origin(request):
        return web.Response(status=401, text='未授权')

    resp = web.StreamResponse()
    resp.headers['Content-Type'] = 'text/event-stream'
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'  # 禁止 Nginx 缓冲
    await resp.prepare(request)

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
    _broadcast.sse_queues.add(queue)
    log.debug(f'SSE 客户端已连接 (WS:{len(_broadcast.clients)} SSE:{len(_broadcast.sse_queues)})')

    try:
        # 发送初始连接确认
        await resp.write(b'data: {"type":"init","data":{}}\n\n')
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25)
                await resp.write(f'data: {payload}\n\n'.encode())
            except TimeoutError:
                await resp.write(b': keepalive\n\n')
    except (asyncio.CancelledError, ConnectionResetError, Exception):
        pass
    finally:
        _broadcast.sse_queues.discard(queue)
        log.debug(f'SSE 客户端已断开 (WS:{len(_broadcast.clients)} SSE:{len(_broadcast.sse_queues)})')

    return resp
