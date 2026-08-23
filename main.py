#!/usr/bin/env python
"""ElainaQQ 应用程序入口。"""

import asyncio
import contextlib
import os
import subprocess
import sys

if sys.version_info < (3, 11):  # noqa: UP036  运行时版本守卫, 面向使用旧版 Python 的用户
    raise SystemExit(f'ElainaQQ 需要 Python 3.11+，当前为 {sys.version_info.major}.{sys.version_info.minor}，请升级后再运行。')

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
sys.dont_write_bytecode = True


def _relaunch() -> None:
    """在当前进程完成清理后重新拉起框架。"""
    if os.name == 'nt':
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.Popen(
            [sys.executable, *sys.argv],
            cwd=_ROOT,
            creationflags=flags,
            close_fds=True,
        )
        os._exit(0)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def main():
    from core.application import Application

    async def run_application():
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()

        def handle_loop_exception(current_loop, context):
            message = str(context.get('message') or '')
            error = context.get('exception')
            if os.name == 'nt' and isinstance(error, ConnectionResetError) and '_ProactorBasePipeTransport._call_connection_lost' in message:
                return
            if previous_handler:
                previous_handler(current_loop, context)
            else:
                current_loop.default_exception_handler(context)

        loop.set_exception_handler(handle_loop_exception)
        return await Application().start()

    with contextlib.suppress(KeyboardInterrupt):
        restart = asyncio.run(run_application())
    if restart:
        _relaunch()


if __name__ == '__main__':
    main()
