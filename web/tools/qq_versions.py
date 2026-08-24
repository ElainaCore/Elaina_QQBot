"""QQ 版本管理 Web API"""

import asyncio
import time
from pathlib import Path

from aiohttp import web

from core.foundation.config import cfg
from core.runtime.qq.distribution import QQ_VERSIONS, QQDownloadError, get_qq_manager
from web.protocol import json_body

_app = None
_jobs: dict[str, dict] = {}


def _qq_error_response(exc: Exception):
    if isinstance(exc, QQDownloadError):
        return web.json_response(
            {
                'success': False,
                'error': 'QQ 安装包下载失败：所有备用地址均不可用，请稍后重试或手动下载官方安装包',
                'detail': str(exc),
            },
            status=502,
        )
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return web.json_response({'success': False, 'error': str(exc)}, status=400)
    if isinstance(exc, RuntimeError):
        return web.json_response({'success': False, 'error': str(exc)}, status=409)
    return web.json_response({'success': False, 'error': str(exc)}, status=500)


def set_context(app_instance):
    global _app
    _app = app_instance


def _manager():
    base_dir = getattr(_app, '_base_dir', None)
    # Web 安装和内置 QQ 启动必须共享同一个运行时目录，否则面板显示
    # 已安装而启动器仍会报“未找到 QQ 可执行文件”。
    return get_qq_manager(Path(base_dir) / 'data' / 'qq' if base_dir else None)


def _sync_embedded_path(manager, version_key=None):
    executable = manager.get_qq_executable(version_key)
    return executable


async def _stop_embedded_qq(version_key=None):
    manager = getattr(_app, 'embedded_qq', None) or getattr(_app, 'embedded_manager', None)
    if manager and version_key and hasattr(manager, 'stop_version'):
        await manager.stop_version(version_key)
    elif manager and hasattr(manager, 'stop_all'):
        await manager.stop_all()


async def handle_list_versions(request: web.Request):
    """列出所有可用的 QQ 版本"""
    manager = _manager()
    versions = manager.list_available_versions()
    return web.json_response({'success': True, 'versions': versions})


async def handle_get_status(request: web.Request):
    """获取 QQ 安装状态"""
    manager = _manager()
    _sync_embedded_path(manager)
    status = manager.get_install_status()
    return web.json_response(
        {
            'success': True,
            'status': status,
            'progress': _job_snapshot(_jobs.get(status.get('current_platform'))),
            'jobs': {key: snapshot for key, job in _jobs.items() if (snapshot := _job_snapshot(job)) is not None},
        }
    )


def _job_snapshot(job):
    if not job:
        return None
    return {key: value for key, value in job.items() if key != 'task'}


def _set_job(job, **values):
    job.update(values)
    job['updated_at'] = time.time()


async def _run_job(job: dict, manager, operation: str, version_key: str, auto_download: bool = True):
    try:
        if operation == 'download':

            def on_download(downloaded, total):
                percent = round(downloaded * 100 / total, 1) if total else 0
                _set_job(
                    job, stage='downloading', percent=percent, downloaded=downloaded, total=total, indeterminate=not bool(total), message='正在下载 QQ 安装包'
                )

            path = await manager.download_qq(version_key, on_download)
            _set_job(
                job,
                state='completed',
                stage='completed',
                percent=100,
                downloaded=path.stat().st_size if path else job.get('downloaded', 0),
                total=path.stat().st_size if path else job.get('total', 0),
                indeterminate=False,
                message='QQ 安装包下载完成',
                path=str(path) if path else None,
                success=bool(path),
            )
            return

        def on_download(downloaded, total):
            percent = 5 + (downloaded * 80 / total if total else 0)
            _set_job(
                job,
                stage='downloading',
                percent=round(percent, 1),
                downloaded=downloaded,
                total=total,
                indeterminate=not bool(total),
                message='正在下载 QQ 安装包',
            )

        async def on_stage(stage, percent, message):
            _set_job(job, stage=stage, percent=percent, indeterminate=False, message=message)

        install_path = await manager.install_qq(version_key, auto_download, on_download, on_stage)
        executable = _sync_embedded_path(manager, version_key)
        if install_path and executable:
            _set_job(
                job,
                state='completed',
                stage='completed',
                percent=100,
                indeterminate=False,
                message='QQ 安装完成，可以启动登录',
                install_path=str(install_path),
                executable=str(executable),
                success=True,
            )
        elif install_path:
            _set_job(
                job,
                state='manual',
                stage='manual_install_required',
                percent=100,
                indeterminate=False,
                message='安装包已准备，但系统需要手动完成安装',
                install_path=str(install_path),
                success=False,
            )
        else:
            _set_job(job, state='failed', stage='failed', percent=0, indeterminate=False, message='QQ 安装失败', success=False)
    except Exception as exc:
        message = 'QQ 安装包下载失败：所有备用地址均不可用' if isinstance(exc, QQDownloadError) else str(exc)
        _set_job(job, state='failed', stage='failed', percent=0, indeterminate=False, message=message, error=str(exc), success=False)
    finally:
        job['task'] = None


def _start_job(version_key: str, operation: str, auto_download: bool = True) -> dict:
    if version_key not in QQ_VERSIONS:
        raise ValueError(f'未知的 QQ 版本: {version_key}')
    current = _jobs.get(version_key)
    if current and current.get('state') == 'running':
        if current.get('operation') != operation:
            raise RuntimeError('该 QQ 版本已有其他安装任务正在执行')
        return current
    manager = _manager()
    job = {
        'version_key': version_key,
        'operation': operation,
        'state': 'running',
        'stage': 'preparing',
        'percent': 0,
        'downloaded': 0,
        'total': 0,
        'indeterminate': False,
        'message': '正在准备任务',
        'success': None,
        'error': '',
        'started_at': time.time(),
        'updated_at': time.time(),
    }
    _jobs[version_key] = job
    job['task'] = asyncio.create_task(_run_job(job, manager, operation, version_key, auto_download), name=f'qq-{operation}-{version_key}')
    return job


async def handle_get_progress(request: web.Request):
    version_key = request.query.get('version_key') or _manager().detect_platform()
    return web.json_response({'success': True, 'progress': _job_snapshot(_jobs.get(version_key))})


async def handle_download_qq(request: web.Request):
    """下载 QQ 客户端"""
    try:
        body = await json_body(request)
        version_key = body.get('version_key')

        if not version_key:
            return web.json_response({'success': False, 'error': '缺少 version_key 参数'}, status=400)

        manager = _manager()
        job = _start_job(version_key, 'download')
        return web.json_response(
            {
                'success': True,
                'accepted': True,
                'job': _job_snapshot(job),
                'status': manager.get_install_status(),
            },
            status=202,
        )

    except Exception as e:
        return _qq_error_response(e)


async def handle_install_qq(request: web.Request):
    """安装 QQ 客户端"""
    try:
        body = await json_body(request)
        version_key = body.get('version_key')
        auto_download = body.get('auto_download', True)

        if not version_key:
            return web.json_response({'success': False, 'error': '缺少 version_key 参数'}, status=400)

        manager = _manager()
        job = _start_job(version_key, 'install', auto_download)
        return web.json_response({'success': True, 'accepted': True, 'job': _job_snapshot(job), 'status': manager.get_install_status()}, status=202)

    except Exception as e:
        return _qq_error_response(e)


async def handle_uninstall_qq(request: web.Request):
    """卸载框架管理的 QQ，不删除外部检测到的系统 QQ。"""
    try:
        body = await json_body(request)
        version_key = body.get('version_key')
        await _stop_embedded_qq(version_key)
        manager = _manager()
        result = await manager.uninstall_qq(version_key)
        configured = str(cfg.get('settings', 'embedded_qq.qq_path', '') or '')
        previous_executable = result.get('previous_executable')
        if result.get('removed') and configured and previous_executable and Path(configured).resolve() == Path(previous_executable).resolve():
            cfg.set_value('settings', 'embedded_qq.qq_path', '')
        status = manager.get_install_status()
        if result.get('manual'):
            return web.json_response(
                {
                    'success': False,
                    'result': result,
                    'status': status,
                    'error': 'QQ 位于系统安装目录，未自动删除：' + '；'.join(result['manual']),
                },
                status=422,
            )
        return web.json_response({'success': True, 'result': result, 'status': status, 'message': 'QQ 已卸载'})
    except Exception as exc:
        return web.json_response({'success': False, 'error': str(exc)}, status=500)


async def handle_cleanup_qq(request: web.Request):
    """清理框架下载的 QQ 安装包和断点续传临时文件。"""
    try:
        body = await json_body(request)
    except Exception:
        body = {}
    try:
        manager = _manager()
        result = await manager.cleanup_qq(body.get('version_key'))
        return web.json_response(
            {
                'success': True,
                'result': result,
                'status': manager.get_install_status(),
                'message': f'已清理 {len(result.get("removed", []))} 个 QQ 安装缓存文件',
            }
        )
    except Exception as exc:
        return web.json_response({'success': False, 'error': str(exc)}, status=500)


async def handle_detect_qq(request: web.Request):
    """检测已安装的 QQ"""
    manager = _manager()
    qq_path = _sync_embedded_path(manager)

    if qq_path:
        return web.json_response({'success': True, 'found': True, 'path': str(qq_path)})
    else:
        return web.json_response({'success': True, 'found': False, 'path': None})
