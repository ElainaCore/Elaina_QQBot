"""QLinux OneBot 消息段编码。"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
import urllib.request
from urllib.parse import urlsplit

from core.protocols.onebot.message import normalize_message


async def to_segments(message) -> list[dict]:
    """转换 OneBot 消息段为 runner segments。"""
    output: list[dict] = []
    for segment in normalize_message(message):
        kind = segment.get('type')
        data = segment.get('data', {}) or {}
        if kind == 'text':
            output.append({'type': 'text', 'data': data.get('text', '')})
        elif kind == 'at':
            qq = str(data.get('qq', ''))
            output.append({'type': 'at_all'} if qq == 'all' else {'type': 'at', 'qq': int(qq or 0)})
        elif kind == 'image':
            value = data.get('file', '')
            if value.startswith('base64://'):
                value = value[9:]
            elif value.startswith('http'):
                value = await asyncio.to_thread(fetch_base64, value)
            output.append({'type': 'image', 'data_base64': value})
        elif kind == 'json':
            output.append({'type': 'json', 'data': data.get('data', '')})
        elif kind in {'record', 'video', 'file', 'markdown', 'xml'}:
            output.append({'type': kind, 'data': dict(data)})
        elif kind == 'reply':
            output.append({'type': 'reply', 'id': str(data.get('id') or data.get('seq') or '')})
        else:
            output.append({'type': str(kind or 'unknown'), 'data': dict(data)})
    return output


def fetch_base64(url: str) -> str:
    """安全下载图片并编码为 base64。"""
    max_size = 16 * 1024 * 1024
    parsed = urlsplit(str(url or ''))
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('图片 URL 必须使用 HTTP 或 HTTPS')
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == 'https' else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise ValueError('图片地址无法解析') from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError('图片地址不允许访问内网或本机地址')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError('图片地址不允许重定向')

    request = urllib.request.Request(url, headers={'User-Agent': 'ElainaQQ/QLinux'})
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(request, timeout=15) as response:  # nosec B310
        if int(response.headers.get('Content-Length') or 0) > max_size:
            raise ValueError('图片超过 16 MB 限制')
        chunks: list[bytes] = []
        size = 0
        while chunk := response.read(256 * 1024):
            size += len(chunk)
            if size > max_size:
                raise ValueError('图片超过 16 MB 限制')
            chunks.append(chunk)
        return base64.b64encode(b''.join(chunks)).decode()
