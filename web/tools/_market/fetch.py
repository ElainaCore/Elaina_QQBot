"""插件市场的索引读取、镜像重试与文件下载。"""

import json
import time

import aiohttp as _aiohttp

from web.tools._market.shared import (
    PLUGIN_REPO,
    _ranked_mirror_urls,
)

_plugin_cache = None  # 缓存的插件列表
_plugin_cache_ts = 0
_PLUGIN_CACHE_TTL = 10 * 60  # 10 分钟
_MAX_JSON_SIZE = 2 * 1024 * 1024
_MAX_DOWNLOAD_SIZE = 128 * 1024 * 1024
_REQUEST_HEADERS = {'User-Agent': 'ElainaQQ/1.0'}


async def _read_limited(response, limit):
    declared = int(response.headers.get('content-length', 0) or 0)
    if declared > limit:
        raise ValueError(f'下载内容超过 {limit // 1024 // 1024} MB 限制')
    chunks = []
    size = 0
    async for chunk in response.content.iter_chunked(256 * 1024):
        size += len(chunk)
        if size > limit:
            raise ValueError(f'下载内容超过 {limit // 1024 // 1024} MB 限制')
        chunks.append(chunk)
    return b''.join(chunks)


async def _try_fetch_json(session, urls, timeout):
    """依次尝试候选地址，返回首个有效的 JSON 数据。"""
    for url in urls:
        try:
            async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
                if resp.status == 200:
                    body = await _read_limited(resp, _MAX_JSON_SIZE)
                    if body.lstrip()[:1] in (b'[', b'{'):
                        data = json.loads(body)
                        if isinstance(data, (dict, list)):
                            return data
        except (
            _aiohttp.ClientError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            ValueError,
        ):
            continue
    return None


async def _try_download(session, urls, timeout):
    """依次下载候选地址，返回首个成功响应的内容。"""
    request_timeout = _aiohttp.ClientTimeout(total=timeout)
    for url in urls:
        try:
            async with session.get(
                url,
                timeout=request_timeout,
                allow_redirects=True,
            ) as response:
                if response.status == 200:
                    return await _read_limited(response, _MAX_DOWNLOAD_SIZE)
        except (_aiohttp.ClientError, TimeoutError, ValueError):
            continue
    return None


async def _fetch_plugin_json(force=False):
    """从 GitHub 获取 onebot_plugins.json, 按镜像排名依次尝试"""
    global _plugin_cache, _plugin_cache_ts
    now = time.time()
    if not force and _plugin_cache and (now - _plugin_cache_ts) < _PLUGIN_CACHE_TTL:
        return _plugin_cache

    raw_url = f'https://raw.githubusercontent.com/{PLUGIN_REPO}/main/onebot_plugins.json'
    timeout = _aiohttp.ClientTimeout(total=10)
    async with _aiohttp.ClientSession(headers=_REQUEST_HEADERS) as session:
        data = await _try_fetch_json(session, _ranked_mirror_urls(raw_url), timeout)
        if not data:
            from web.tools._updater.mirror import get_fast_mirrors

            await get_fast_mirrors(force=True)
            data = await _try_fetch_json(session, _ranked_mirror_urls(raw_url), timeout)
    if data:
        _plugin_cache, _plugin_cache_ts = data, now
    return data


async def _download_file(url, timeout=60, mirror=None):
    """按镜像排名下载, 全失败重新测速后再试; mirror 非空时优先使用指定镜像"""
    is_gh = 'github.com' in url or 'githubusercontent.com' in url
    if mirror and is_gh:
        from web.tools._updater.shared import _build_mirror_url

        urls = [_build_mirror_url(url, mirror)] + _ranked_mirror_urls(url)
    else:
        urls = _ranked_mirror_urls(url) if is_gh else [url]
    async with _aiohttp.ClientSession(headers=_REQUEST_HEADERS) as session:
        content = await _try_download(session, urls, timeout)
        if content is not None or not is_gh:
            return content

        # 首轮全部失败后刷新镜像测速，并复用当前连接池再次尝试。
        from web.tools._updater.mirror import get_fast_mirrors

        await get_fast_mirrors(force=True)
        return await _try_download(session, _ranked_mirror_urls(url), timeout)


def _extract_plugins(data):
    """从缓存数据提取插件列表，兼容列表和对象两种格式。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        plugins = data.get('plugins', [])
        return plugins if isinstance(plugins, list) else []
    return []
