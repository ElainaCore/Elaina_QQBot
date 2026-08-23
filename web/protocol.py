"""Web API 请求与响应协议。"""

from __future__ import annotations

import json
import logging
import re
import secrets
from typing import Any

from aiohttp import ContentTypeError, web

log = logging.getLogger('ElainaQQ.web.protocol')

_MAX_JSON_BODY_SIZE = 4 * 1024 * 1024
_JSON_BODY_KEY = web.RequestKey('elaina.json_body', dict)
_REQUEST_ID_KEY = web.RequestKey('elaina.request_id', str)
_REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
_SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'Referrer-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}


class RequestFormatError(ValueError):
    """表示客户端提交了无法解析或类型错误的请求正文。"""


async def json_body(request: web.Request) -> dict[str, Any]:
    """读取并缓存 JSON 对象，统一拒绝空正文、非法 JSON 和非对象根节点。"""
    cached = request.get(_JSON_BODY_KEY)
    if cached is not None:
        return cached
    if request.content_length is not None and request.content_length > _MAX_JSON_BODY_SIZE:
        raise RequestFormatError('JSON 请求正文不能超过 4 MB')
    try:
        raw = await request.read()
        if len(raw) > _MAX_JSON_BODY_SIZE:
            raise RequestFormatError('JSON 请求正文不能超过 4 MB')
        data = json.loads(raw)
    except RequestFormatError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, web.HTTPBadRequest) as error:
        raise RequestFormatError('请求正文必须是有效的 JSON 对象') from error
    if not isinstance(data, dict):
        raise RequestFormatError('JSON 根节点必须是对象')
    request[_JSON_BODY_KEY] = data
    return data


def ok(data: Any = None, *, message: str = '', **fields: Any) -> web.Response:
    """生成成功响应，并兼容已有的顶层字段格式。"""
    payload: dict[str, Any] = {'success': True}
    if data is not None:
        payload['data'] = data
    if message:
        payload['message'] = message
    payload.update(fields)
    return web.json_response(payload)


def error(message: str, *, status: int = 400, **fields: Any) -> web.Response:
    """生成格式一致的失败响应。"""
    payload: dict[str, Any] = {
        'success': False,
        'error': str(message),
        'message': str(message),
    }
    payload.update(fields)
    return web.json_response(payload, status=status)


def _request_id(request: web.Request) -> str:
    supplied = request.headers.get('X-Request-ID', '').strip()
    if _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return secrets.token_hex(8)


def _apply_response_headers(request: web.Request, response: web.StreamResponse, *, prepared: bool = False) -> None:
    if response.prepared and not prepared:
        return
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    response.headers.pop('Server', None)
    response.headers.setdefault('X-Request-ID', request[_REQUEST_ID_KEY])
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers.setdefault('Pragma', 'no-cache')


def _normalize_api_json_response(request: web.Request, response: web.StreamResponse) -> None:
    """补齐旧接口的成功标记和错误字段，同时保留原有业务字段。"""
    if (
        not request.path.startswith('/api/')
        or not isinstance(response, web.Response)
        or response.content_type != 'application/json'
        or not response.body
        or response.prepared
    ):
        return
    try:
        payload = json.loads(response.body.decode(response.charset or 'utf-8'))
    except (AttributeError, LookupError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return

    if response.status >= 400:
        payload['success'] = False
    elif 'success' not in payload:
        payload['success'] = not bool(payload.get('error'))

    if payload['success'] is False:
        message = str(payload.get('error') or payload.get('message') or response.reason or '请求失败')
        payload['error'] = message
        payload['message'] = message

    response.body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')


async def prepare_response_headers(request: web.Request, response: web.StreamResponse) -> None:
    """在流式响应发送响应头前应用同一套安全与缓存规则。"""
    request.setdefault(_REQUEST_ID_KEY, _request_id(request))
    _apply_response_headers(request, response, prepared=True)


@web.middleware
async def api_protocol_middleware(request: web.Request, handler):
    """统一 API 异常、请求编号、缓存策略和基础安全响应头。"""
    request[_REQUEST_ID_KEY] = _request_id(request)
    try:
        if (
            request.path.startswith('/api/')
            and request.method not in {'GET', 'HEAD', 'OPTIONS'}
            and request.can_read_body
            and request.content_type.lower().endswith('json')
        ):
            await json_body(request)
        response = await handler(request)
    except RequestFormatError as exc:
        response = error(str(exc), status=400)
    except (json.JSONDecodeError, UnicodeDecodeError, ContentTypeError):
        response = error('请求正文必须是有效的 JSON 对象', status=400)
    except web.HTTPException as exc:
        if not request.path.startswith('/api/'):
            raise
        response = error(exc.reason or '请求失败', status=exc.status)
    except Exception:
        if not request.path.startswith('/api/'):
            raise
        log.exception(
            'API 请求处理失败: %s %s [请求编号 %s]',
            request.method,
            request.path,
            request[_REQUEST_ID_KEY],
        )
        response = error('服务器内部错误', status=500)
    _normalize_api_json_response(request, response)
    _apply_response_headers(request, response)
    return response
