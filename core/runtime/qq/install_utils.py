"""QQ 安装流程的系统工具。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def is_root() -> bool:
    """判断当前进程是否拥有 root 权限。"""
    return os.name != 'nt' and hasattr(os, 'geteuid') and os.geteuid() == 0


def run_command(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """执行安装命令并检查退出码。"""
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'QQ 安装操作失败（退出码 {result.returncode}）')
    return result


def write_download_chunk(path: Path, content: bytes, append: bool) -> None:
    """写入下载分片。"""
    with path.open('ab' if append else 'wb') as output:
        output.write(content)
