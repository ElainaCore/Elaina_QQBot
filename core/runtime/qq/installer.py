"""跨平台 QQ 安装包管理器的兼容门面。"""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from pathlib import Path

from core.runtime.qq.distribution import QQ_VERSIONS, QQManager

log = logging.getLogger('ElainaQQ.qq_installer')


class QQInstaller:
    """保留旧版安装器 API，内部统一使用 QQManager。"""

    QQ_DOWNLOAD_URL = QQ_VERSIONS['windows_x64']['url']
    QQ_VERSION = QQ_VERSIONS['windows_x64']['version']

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.manager = QQManager(self.base_dir)
        self.download_dir = self.manager.download_dir
        self.install_dir = self.manager.install_dir

    def _default_key(self) -> str:
        key = self.manager.detect_platform()
        if not key:
            raise RuntimeError(f'不支持当前平台: {platform.system()} {platform.machine()}')
        return key

    async def download_qq(self, progress_callback=None, version_key: str | None = None) -> Path:
        path = await self.manager.download_qq(version_key or self._default_key(), progress_callback)
        if not path:
            raise RuntimeError('QQ 下载失败')
        return path

    async def install_qq(self, installer_path: Path | None = None, silent: bool = True, version_key: str | None = None) -> Path:
        key = version_key or self._default_key()
        if installer_path is not None:
            source = Path(installer_path).expanduser().resolve()
            target = self.manager._version_path(key)
            if source != target:
                await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(shutil.copy2, source, target)
        result = await self.manager.install_qq(key, auto_download=installer_path is None)
        if not result:
            raise RuntimeError('QQ 安装失败')
        return result

    def get_qq_path(self, version_key: str | None = None) -> Path | None:
        return self.manager.get_qq_executable(version_key)

    def is_qq_installed(self, version_key: str | None = None) -> bool:
        return self.get_qq_path(version_key) is not None

    def get_qq_version(self) -> str | None:
        path = self.get_qq_path()
        if not path:
            return None
        return self.manager.installed_versions.get(self._default_key(), {}).get('version') or 'unknown'


async def main():
    installer = QQInstaller(Path('data/qq'))
    print(installer.manager.get_install_status())
    if not installer.is_qq_installed():
        print(await installer.install_qq())


if __name__ == '__main__':
    asyncio.run(main())
