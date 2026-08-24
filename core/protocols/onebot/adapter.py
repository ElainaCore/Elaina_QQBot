"""OneBot v11 适配器与网络连接管理。"""

import asyncio
import hmac
import json
import logging
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp

from core.protocols.onebot.event import OneBotEvent, parse_event

logger = logging.getLogger('ElainaQQ.onebot.adapter')

_HTTP_RESPONSE_LIMIT = 32 * 1024 * 1024


class OneBotAdapter:
    """OneBot v11 协议适配器"""

    def __init__(self, action_result_handler=None):
        self.bots: dict[str, Any] = {}
        self.websockets: dict[str, Any] = {}
        self.api_responses: dict[str, asyncio.Future] = {}
        self._api_response_owners: dict[str, Any] = {}
        self.http_clients: dict[str, dict[str, str]] = {}  # 名称映射到地址和令牌
        self.local_actions: dict[str, Any] = {}
        self.identity_aliases: dict[str, str] = {}
        # 鉴权按端口和路径隔离，避免不同连接误用令牌或签名密钥。
        self.reverse_ws_tokens: dict[tuple, str] = {}
        self.reverse_http_secrets: dict[tuple, str] = {}
        self._http_session: aiohttp.ClientSession | None = None
        self.action_result_handler = action_result_handler

    def register_local_bot(self, self_id: str, action):
        """注册由框架直接 Hook 的本机 QQ 账号。"""
        self_id = str(self_id)
        self.local_actions[self_id] = action
        self.bots[self_id] = {'self_id': self_id, 'type': 'embedded'}

    def register_identity_alias(self, alias: str, self_id: str) -> None:
        """登记配置编号到真实 OneBot self_id 的稳定映射。"""
        alias, self_id = str(alias or '').strip(), str(self_id or '').strip()
        if alias and self_id and alias != self_id:
            self.identity_aliases[alias] = self_id

    def unregister_identity_alias(self, alias: str) -> None:
        self.identity_aliases.pop(str(alias or ''), None)

    def resolve_self_id(self, self_id: str | None) -> str | None:
        """将内置 QQ 的临时编号解析为标准 self_id。"""
        if self_id is None:
            return None
        current = str(self_id)
        seen = set()
        while current in self.identity_aliases and current not in seen:
            seen.add(current)
            current = self.identity_aliases[current]
        return current

    def allows_self_id(self, allowed: set[str] | frozenset[str] | None, self_id: str) -> bool:
        """使用同一身份规则判断插件账号绑定。"""
        if allowed is None:
            return True
        actual = self.resolve_self_id(self_id)
        return any(self.resolve_self_id(candidate) == actual for candidate in allowed)

    def unregister_local_bot(self, self_id: str):
        self_id = str(self_id)
        self.local_actions.pop(self_id, None)
        record = self.bots.get(self_id)
        if record and record.get('type') == 'embedded':
            self.bots.pop(self_id, None)

    async def call_local_action(
        self,
        action: str,
        params: dict | None = None,
        self_id: str | None = None,
    ):
        self_id = self.resolve_self_id(self_id)
        handler = self.local_actions.get(str(self_id)) if self_id else None
        if self_id and handler is None:
            return None
        if handler is None and len(self.local_actions) == 1:
            handler = next(iter(self.local_actions.values()))
        elif handler is None and len(self.local_actions) > 1:
            logger.warning('多条内置 QQ 连接未指定 self_id，拒绝随机选择本地动作')
        if handler is None:
            return None
        return await handler(action, params or {})

    def default_self_id(self) -> str | None:
        """按本机、WebSocket、已登记账号的顺序选择默认机器人。"""
        identities = {
            str(self.resolve_self_id(self_id) or self_id)
            for registry in (self.local_actions, self.websockets, self.bots)
            for self_id in registry
        }
        return next(iter(identities)) if len(identities) == 1 else None

    def expected_ws_token(self, port=None, path=None) -> str:
        """返回指定 (端口, 路径) 反向 WS 入口应校验的 token; 找不到则不校验"""
        m = self.reverse_ws_tokens
        if port is not None and (port, path) in m:
            return m[(port, path)]
        if port is not None:  # 同端口的别名路径 (如 /onebot/v11/ws) 复用该端口的 token
            for (p, _pa), t in m.items():
                if p == port:
                    return t
        return ''

    def expected_http_secret(self, port=None, path=None) -> str:
        m = self.reverse_http_secrets
        if port is not None and (port, path) in m:
            return m[(port, path)]
        if port is not None:
            for (p, _pa), s in m.items():
                if p == port:
                    return s
        return ''

    def _check_signature(self, body: bytes, signature: str | None, secret: str = '') -> bool:
        if not secret:
            return True
        if not signature:
            return False
        sig = hmac.new(secret.encode('utf-8'), body, 'sha1').hexdigest()
        return hmac.compare_digest(signature, 'sha1=' + sig)

    def _check_access_token(self, auth_header: str | None, token: str = '') -> bool:
        if not token:
            return True
        if not auth_header:
            return False
        parts = auth_header.split(' ', 1)
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return False
        return hmac.compare_digest(parts[1], token)

    def parse_event(self, data: dict, default_self_id: str = '') -> OneBotEvent | None:
        """解析事件，并把全部账号别名收敛为标准 self_id。"""
        if not isinstance(data, dict):
            return None
        payload = dict(data)
        supplied_self_id = payload.get('self_id') or default_self_id
        canonical_self_id = self.resolve_self_id(str(supplied_self_id)) if supplied_self_id else ''
        if canonical_self_id:
            payload['self_id'] = canonical_self_id
        return parse_event(payload, canonical_self_id or default_self_id)

    def decode_http_event(self, body: bytes, headers: dict, port=None, path=None) -> tuple[dict | None, int]:
        """校验并解码 HTTP 上报，事件解析统一交给 Application。"""
        self_id = headers.get('x-self-id') or headers.get('X-Self-ID')
        if not self_id:
            return None, 400

        signature = headers.get('x-signature') or headers.get('X-Signature')
        if not self._check_signature(body, signature, self.expected_http_secret(port, path)):
            return None, 401

        try:
            json_data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return None, 400
        if not isinstance(json_data, dict):
            return None, 400
        body_self_id = str(json_data.get('self_id') or '')
        if body_self_id and body_self_id != str(self_id):
            return None, 400
        json_data['self_id'] = str(self_id)
        if 'post_type' not in json_data and 'postType' not in json_data:
            return None, 400

        self_id = str(self_id)
        if self_id not in self.bots:
            self.bots[self_id] = {'self_id': self_id, 'type': 'http'}
            logger.info(f'Bot {self_id} HTTP 连接')

        return json_data, 204

    def validate_websocket_headers(self, headers: dict, port=None, path=None) -> tuple:
        """验证 WebSocket 连接头 (按 端口+路径 选取该连接配置的 token)"""
        self_id = headers.get('x-self-id') or headers.get('X-Self-ID')
        if not self_id:
            return False, None, '缺少 X-Self-ID'

        auth_header = headers.get('authorization') or headers.get('Authorization')
        if not self._check_access_token(auth_header, self.expected_ws_token(port, path)):
            return False, self_id, '鉴权失败'

        return True, self_id, None

    def register_bot(self, self_id: str, ws=None):
        # aiohttp 的连接对象可能被判定为假值，因此必须显式判断是否为 None。
        self_id = str(self_id)
        is_ws = ws is not None
        previous_ws = self.websockets.get(self_id)
        if previous_ws is not None and previous_ws is not ws:
            self.cancel_api_responses(previous_ws)
        self.bots[self_id] = {'self_id': self_id, 'type': 'websocket' if is_ws else 'http', 'ws': ws}
        if is_ws:
            self.websockets[self_id] = ws

    def unregister_bot(self, self_id: str, ws=None, *, cancel_responses: bool = True):
        self_id = str(self_id)
        if ws is not None and self.websockets.get(self_id) is not ws:
            return False
        active_ws = self.websockets.get(self_id)
        if cancel_responses and active_ws is not None:
            self.cancel_api_responses(active_ws)
        self.bots.pop(self_id, None)
        self.websockets.pop(self_id, None)
        return True

    def register_api_response(
        self,
        echo: str,
        future: asyncio.Future,
        owner=None,
    ) -> None:
        """登记等待中的 API 响应，并记录所属连接以便断线时回收。"""
        old_future = self.api_responses.get(echo)
        if old_future is not None and not old_future.done():
            old_future.cancel()
        self.api_responses[echo] = future
        if owner is not None:
            self._api_response_owners[echo] = owner
        else:
            self._api_response_owners.pop(echo, None)

    def resolve_api_response(self, echo, payload: dict) -> bool:
        """完成指定 API 响应；未知或已经结束的 echo 返回 False。"""
        key = str(echo)
        future = self.api_responses.pop(key, None)
        self._api_response_owners.pop(key, None)
        if future is None or future.done():
            return False
        future.set_result(payload)
        return True

    def discard_api_response(self, echo, *, cancel: bool = True) -> bool:
        """移除指定待响应对象，并按需取消仍在等待的 Future。"""
        key = str(echo)
        future = self.api_responses.pop(key, None)
        self._api_response_owners.pop(key, None)
        if future is None:
            return False
        if cancel and not future.done():
            future.cancel()
        return True

    def cancel_api_responses(self, owner=None) -> int:
        """取消全部或指定连接所属的待响应对象。"""
        if owner is None:
            echoes = tuple(self.api_responses)
        else:
            echoes = tuple(
                echo
                for echo, response_owner in self._api_response_owners.items()
                if response_owner is owner
            )
        for echo in echoes:
            self.discard_api_response(echo)
        return len(echoes)

    def get_bot_ws(self, self_id: str | None = None):
        """获取 bot WebSocket 连接"""
        self_id = self.resolve_self_id(self_id)
        if self_id:
            return self.websockets.get(self_id)
        # 仅单账号时允许省略 self_id，多账号绝不随机串线。
        if len(self.websockets) == 1:
            return next(iter(self.websockets.values()))
        return None

    def register_http_client(self, name: str, url: str, token: str = '', self_id: str = ''):
        """注册 HTTP 客户端目标 (框架 -> OneBot HTTP API)"""
        normalized = (url or '').strip().rstrip('/')
        parsed = urlsplit(normalized)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            logger.warning('忽略无效的 OneBot HTTP 地址: %s', url)
            return
        self.http_clients[name] = {
            'url': normalized,
            'token': token or '',
            'self_id': str(self_id or name or '').strip(),
        }

    def clear_http_clients(self):
        self.http_clients.clear()

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """获取复用的 HTTP 会话，限制连接数以避免高并发耗尽文件描述符。"""
        if self._http_session is None or self._http_session.closed:
            connector = aiohttp.TCPConnector(
                limit=64,
                limit_per_host=32,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=25)
            self._http_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'ElainaQQ/1.0'},
            )
        return self._http_session

    async def close(self) -> None:
        """关闭网络资源并取消仍在等待的 API 响应。"""
        self.cancel_api_responses()
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
        self._http_session = None

    @staticmethod
    async def _read_http_json(response: aiohttp.ClientResponse) -> dict:
        declared = int(response.headers.get('Content-Length', 0) or 0)
        if declared > _HTTP_RESPONSE_LIMIT:
            raise ValueError('OneBot HTTP 响应超过 32 MB 限制')
        body = bytearray()
        async for chunk in response.content.iter_chunked(256 * 1024):
            body.extend(chunk)
            if len(body) > _HTTP_RESPONSE_LIMIT:
                raise ValueError('OneBot HTTP 响应超过 32 MB 限制')
        if not body:
            return {}
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError('OneBot HTTP 响应根节点不是对象')
        return data

    def _select_http_client(self, self_id: str | None = None) -> dict | None:
        if not self.http_clients:
            return None
        requested = self.resolve_self_id(self_id) if self_id else ''
        clients = list(self.http_clients.values())
        if requested:
            matches = [client for client in clients if self.resolve_self_id(client.get('self_id')) == requested]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                logger.warning('OneBot HTTP 账号标识重复，拒绝随机选择: self_id=%s', requested)
                return None
            if len(clients) > 1:
                logger.warning('没有匹配 self_id 的 OneBot HTTP 连接: self_id=%s', requested)
                return None
        if len(clients) == 1:
            return clients[0]
        logger.warning('多条 OneBot HTTP 连接未指定 self_id，拒绝随机选择')
        return None

    async def http_call_action(self, action: str, params: dict | None = None, self_id: str | None = None) -> dict | None:
        """通过 HTTP 调用 OneBot 接口。"""
        if not self.http_clients:
            return None
        normalized_action = str(action or '').strip().strip('/')
        if not normalized_action:
            logger.warning('忽略空的 OneBot HTTP 动作')
            return None
        client = self._select_http_client(self_id)
        if client is None:
            return None
        url = f'{client["url"]}/{quote(normalized_action, safe="._-")}'
        headers = {}
        if client.get('token'):
            headers['Authorization'] = 'Bearer ' + client['token']
        try:
            session = await self._get_http_session()
            async with session.post(url, json=params or {}, headers=headers) as response:
                data = await self._read_http_json(response)
                if response.status >= 400:
                    message = data.get('message') or data.get('wording') or f'HTTP {response.status}'
                    logger.warning('OneBot HTTP 接口返回错误: %s - %s', normalized_action, message)
                    data.setdefault('status', 'failed')
                    data.setdefault('retcode', response.status)
                return data
        except (aiohttp.ClientError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            logger.warning('OneBot HTTP 接口调用失败: %s - %s', normalized_action, error)
            return None
