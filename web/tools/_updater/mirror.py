"""框架更新 — 镜像测速, 环境检测"""

import asyncio
import os
import time

import aiohttp as _aiohttp

from web.tools._updater.shared import (
    GITHUB_FILE_MIRRORS,
    _build_mirror_url,
    _load_mirror_cache,
    _save_mirror_cache,
    clear_mirror_cache,  # noqa: F401  # 供处理器模块复用
)

_mirror_testing = None  # 防止并发触发重复测速


async def _test_one_mirror(session, mirror, timeout=3):
    """通过响应头请求测试镜像延迟，成功或重定向均视为可用。"""
    test_url = _build_mirror_url('https://github.com/ElainaCore/Elaina_QQBot/releases/latest', mirror)
    start = time.monotonic()
    try:
        async with session.head(
            test_url,
            timeout=_aiohttp.ClientTimeout(total=timeout),
            allow_redirects=False,
        ) as resp:
            latency = time.monotonic() - start
            # 部分镜像不支持响应头请求，但服务本身仍然可用。
            ok = (200 <= resp.status < 400) or resp.status == 405
            return {
                'mirror': mirror,
                'latency': round(latency, 3),
                'success': ok,
                'status': resp.status,
            }
    except (_aiohttp.ClientError, TimeoutError) as e:
        return {
            'mirror': mirror,
            'latency': round(time.monotonic() - start, 3),
            'success': False,
            'error': type(e).__name__,
        }


async def test_one_mirror(mirror, timeout=3):
    """使用独立会话测试单个镜像，供管理接口调用。"""
    connector = _aiohttp.TCPConnector(limit=2, ttl_dns_cache=300)
    async with _aiohttp.ClientSession(
        connector=connector,
        headers={'User-Agent': 'ElainaQQ-Mirror-Test'},
    ) as session:
        return await _test_one_mirror(session, mirror, timeout)


async def test_all_mirrors(timeout=3):
    """使用共享连接池并行测试镜像并按延迟排序。"""
    connector = _aiohttp.TCPConnector(limit=16, limit_per_host=4, ttl_dns_cache=300)
    async with _aiohttp.ClientSession(
        connector=connector,
        headers={'User-Agent': 'ElainaQQ-Mirror-Test'},
    ) as session:
        mirrors = [*GITHUB_FILE_MIRRORS, '']
        results = await asyncio.gather(*(_test_one_mirror(session, mirror, timeout) for mirror in mirrors))
    results = sorted(results, key=lambda r: (not r['success'], r['latency']))
    return results


async def get_fast_mirrors(force=False):
    """获取按延迟排序的可用镜像列表 (磁盘缓存 30 分钟)"""
    global _mirror_testing
    if not force:
        cached = _load_mirror_cache()
        if cached:
            return cached
    if _mirror_testing and not _mirror_testing.done():
        return await _mirror_testing
    _mirror_testing = asyncio.create_task(test_all_mirrors(), name='mirror-latency-test')
    try:
        results = await _mirror_testing
    finally:
        _mirror_testing = None
    ok = [r for r in results if r['success']]
    _save_mirror_cache(ok)
    return ok


# ==================== 环境检测 ====================


def detect_environment():
    """检测运行环境, 返回 {docker, writable, warning}"""
    info = {'docker': False, 'writable': True, 'warnings': []}
    # 检测 Docker 环境
    if os.path.exists('/.dockerenv'):
        info['docker'] = True
    else:
        try:
            with open('/proc/1/cgroup') as f:
                if 'docker' in f.read() or 'containerd' in f.read():
                    info['docker'] = True
        except Exception:
            pass
    # 可写性检测
    try:
        test_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            '.write_test',
        )
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
    except Exception:
        info['writable'] = False
        info['warnings'].append('项目目录不可写, 更新将失败')
    if info['docker']:
        info['warnings'].append('检测到 Docker 环境, 请确保项目目录已挂载 volume 以持久化更新')
    return info
