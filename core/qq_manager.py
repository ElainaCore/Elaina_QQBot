"""内置 OneBot 运行时的跨平台 QQ 安装包管理。"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import aiohttp

from core.qq_catalog import QQ_VERSIONS

log = logging.getLogger('ElainaQQ.qq_manager')


class QQDownloadError(RuntimeError):
    """所有已配置 QQ 下载地址均不可用时抛出。"""

    def __init__(self, version_key: str, failures: list[str]):
        self.version_key = version_key
        self.failures = failures
        super().__init__('；'.join(failures) or 'QQ 下载地址不可用')


def _is_root() -> bool:
    return os.name != 'nt' and hasattr(os, 'geteuid') and os.geteuid() == 0


def _run_command(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    log.info('执行 QQ 安装命令: %s', ' '.join(command))
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout or '').strip()
        suffix = f': {detail}' if detail else ''
        raise RuntimeError(f'命令退出码 {result.returncode}: {" ".join(command)}{suffix}')
    return result


class QQManager:
    """下载、安装并定位可共享的 QQNT 安装。"""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.download_dir = self.base_dir / 'downloads'
        self.install_dir = self.base_dir / 'client'
        self.config_file = self.base_dir / 'versions.json'
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_layout()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.installed_versions = self._load_config()
        if self._rewrite_legacy_records():
            self._save_config()
        self._locks: dict[str, asyncio.Lock] = {}

    def _migrate_legacy_layout(self) -> None:
        """将管理器拥有的文件从 data/qq_client 迁移到 data/qq。"""
        if self.base_dir.name != 'qq':
            return
        legacy = self.base_dir.parent / 'qq_client'
        if not legacy.is_dir():
            return
        for source_name, target_name in (('downloads', 'downloads'), ('qq_clients', 'client')):
            source = legacy / source_name
            target = self.base_dir / target_name
            if not source.is_dir():
                continue
            target.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                destination = target / item.name
                if destination.exists():
                    continue
                try:
                    shutil.move(str(item), str(destination))
                except OSError as exc:
                    log.warning('迁移旧 QQ 数据失败: %s -> %s (%s)', item, destination, exc)
        legacy_config = legacy / 'qq_versions.json'
        if legacy_config.is_file() and not self.config_file.exists():
            try:
                shutil.copy2(legacy_config, self.config_file)
            except OSError as exc:
                log.warning('迁移旧 QQ 版本记录失败: %s', exc)

    def _rewrite_legacy_records(self) -> bool:
        if self.base_dir.name != 'qq':
            return False
        legacy = (self.base_dir.parent / 'qq_client').resolve()
        changed = False
        for record in self.installed_versions.values():
            if not isinstance(record, dict):
                continue
            for key, value in list(record.items()):
                if not isinstance(value, str) or not value:
                    continue
                try:
                    relative = Path(value).expanduser().resolve().relative_to(legacy)
                except (OSError, ValueError):
                    continue
                parts = list(relative.parts)
                if parts and parts[0] == 'qq_clients':
                    parts[0] = 'client'
                record[key] = str(self.base_dir.joinpath(*parts))
                changed = True
        return changed

    def _load_config(self) -> dict[str, Any]:
        if not self.config_file.is_file():
            return {}
        try:
            return json.loads(self.config_file.read_text(encoding='utf-8'))
        except Exception as exc:
            log.warning('读取 QQ 版本配置失败: %s', exc)
            return {}

    def _save_config(self) -> None:
        temp = self.config_file.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps(self.installed_versions, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, self.config_file)
        except Exception as exc:
            log.error('保存 QQ 版本配置失败: %s', exc)

    @staticmethod
    def _host_arch() -> str:
        machine = platform.machine().lower()
        if machine in {'aarch64', 'arm64', 'armv8', 'armv8l'} or machine.startswith('arm64'):
            return 'arm64'
        if machine in {'x86_64', 'amd64', 'x64'}:
            return 'x64'
        return machine or 'unknown'

    def platform_info(self) -> dict[str, Any]:
        system = platform.system().lower()
        if system == 'darwin':
            system = 'macos'
        distro_id = ''
        distro_like = ''
        if system == 'linux':
            try:
                release = {}
                for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        release[key.lower()] = value.strip().strip('"')
                distro_id = release.get('id', '').lower()
                distro_like = release.get('id_like', '').lower()
            except (OSError, UnicodeError):
                pass
        return {
            'system': system,
            'arch': self._host_arch(),
            'distro_id': distro_id,
            'distro_like': distro_like,
            'dpkg': bool(shutil.which('dpkg')),
            'rpm': bool(shutil.which('rpm')),
            'apt_get': bool(shutil.which('apt-get')),
            'dnf': bool(shutil.which('dnf')),
            'yum': bool(shutil.which('yum')),
            'zypper': bool(shutil.which('zypper')),
            'sudo': bool(shutil.which('sudo')),
            'display': bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')),
        }

    def detect_platform(self) -> str | None:
        info = self.platform_info()
        system, arch = info['system'], info['arch']
        if system == 'windows' and arch == 'x64':
            return 'windows_x64'
        if system == 'linux' and arch in {'x64', 'arm64'}:
            suffix = 'x64' if arch == 'x64' else 'arm64'
            rpm_distros = {'fedora', 'rhel', 'centos', 'rocky', 'almalinux', 'ol', 'opensuse', 'sles', 'suse', 'mageia', 'clear-linux-os'}
            deb_distros = {'debian', 'ubuntu', 'linuxmint', 'mint', 'deepin', 'uos', 'kali', 'raspbian', 'elementary'}
            distro_tokens = {info.get('distro_id', ''), *str(info.get('distro_like', '')).split()}
            rpm_capable = bool(info['rpm'] or info['dnf'] or info['yum'] or info['zypper'])
            deb_capable = bool(info['dpkg'] or info['apt_get'])
            if distro_tokens & rpm_distros and rpm_capable:
                package = 'rpm'
            elif distro_tokens & deb_distros and deb_capable or deb_capable and not rpm_capable:
                package = 'deb'
            elif rpm_capable and not deb_capable:
                package = 'rpm'
            else:
                package = 'deb' if info['dpkg'] else 'rpm'
            return f'linux_{suffix}_{package}'
        if system == 'macos':
            return 'macos'
        return None

    def get_recommended_version(self) -> dict[str, Any] | None:
        key = self.detect_platform()
        if not key or key not in QQ_VERSIONS:
            return None
        return {'key': key, **QQ_VERSIONS[key]}

    def is_compatible(self, version_key: str) -> bool:
        info = QQ_VERSIONS.get(version_key)
        if not info:
            return False
        host = self.platform_info()
        if info.get('platform') != host['system']:
            return False
        if info.get('arch') not in {host['arch'], 'universal'}:
            return False
        if host['system'] != 'linux':
            return True
        recommended = QQ_VERSIONS.get(self.detect_platform() or '', {})
        return info.get('host_package', info.get('package')) == recommended.get('package')

    def compatible_version_keys(self) -> list[str]:
        return [key for key in QQ_VERSIONS if self.is_compatible(key)]

    def _version_path(self, version_key: str) -> Path:
        return self.download_dir / QQ_VERSIONS[version_key]['filename']

    @staticmethod
    def _package_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _validate_package(self, version_key: str, path: Path) -> None:
        info = QQ_VERSIONS[version_key]
        expected_size = int(info.get('size') or 0)
        actual_size = path.stat().st_size
        if expected_size and actual_size != expected_size:
            raise RuntimeError(f'QQ 安装包大小校验失败: 期望 {expected_size} 字节，实际 {actual_size} 字节')
        expected_hash = str(info.get('sha256') or '').lower()
        if expected_hash:
            actual_hash = self._package_digest(path)
            if actual_hash != expected_hash:
                raise RuntimeError(f'QQ 安装包 SHA-256 校验失败: {actual_hash}')

    async def download_qq(self, version_key: str, progress_callback=None) -> Path | None:
        if version_key not in QQ_VERSIONS:
            raise ValueError(f'未知的 QQ 版本: {version_key}')
        version_info = QQ_VERSIONS[version_key]
        filepath = self._version_path(version_key)
        if filepath.is_file() and filepath.stat().st_size > 0:
            try:
                await asyncio.to_thread(self._validate_package, version_key, filepath)
                return filepath
            except RuntimeError:
                filepath.unlink(missing_ok=True)

        lock = self._locks.setdefault(version_key, asyncio.Lock())
        async with lock:
            if filepath.is_file() and filepath.stat().st_size > 0:
                try:
                    await asyncio.to_thread(self._validate_package, version_key, filepath)
                    return filepath
                except RuntimeError:
                    filepath.unlink(missing_ok=True)
            partial = filepath.with_suffix(filepath.suffix + '.part')
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=180)
            failures: list[str] = []
            urls = [version_info.get('url')]
            headers_base = {'User-Agent': 'ElainaQQ QQ manager/1.0', 'Accept': 'application/octet-stream'}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers_base) as session:
                for url in [item for item in urls if item]:
                    stalled = 0
                    last_error = ''
                    for _attempt in range(512):
                        downloaded = partial.stat().st_size if partial.is_file() else 0
                        expected_size = int(version_info.get('size') or 0)
                        if expected_size and downloaded == expected_size:
                            await asyncio.to_thread(self._validate_package, version_key, partial)
                            os.replace(partial, filepath)
                            return filepath
                        if expected_size and downloaded > expected_size:
                            partial.unlink(missing_ok=True)
                            downloaded = 0
                        headers = {'Range': f'bytes={downloaded}-'} if downloaded else {}
                        before = downloaded
                        try:
                            async with session.get(url, headers=headers, allow_redirects=True) as response:
                                if response.status not in (200, 206):
                                    last_error = f'HTTP {response.status}'
                                    if response.status in {401, 403, 404, 410}:
                                        partial.unlink(missing_ok=True)
                                        stalled = 8
                                        break
                                    raise QQDownloadError(version_key, [last_error])
                                if downloaded and response.status == 200:
                                    downloaded = 0
                                    before = 0
                                    partial.unlink(missing_ok=True)
                                total_header = response.headers.get('content-length')
                                total = expected_size or (int(total_header or 0) + downloaded if total_header else 0)
                                mode = 'ab' if downloaded and response.status == 206 else 'wb'
                                with partial.open(mode) as output:
                                    async for chunk in response.content.iter_chunked(1024 * 256):
                                        output.write(chunk)
                                        downloaded += len(chunk)
                                        if progress_callback:
                                            result = progress_callback(downloaded, total)
                                            if inspect.isawaitable(result):
                                                await result
                            await asyncio.to_thread(self._validate_package, version_key, partial)
                            os.replace(partial, filepath)
                            return filepath
                        except (TimeoutError, aiohttp.ClientError, OSError, ValueError, QQDownloadError) as exc:
                            last_error = str(exc)
                            current = partial.stat().st_size if partial.is_file() else 0
                            if current > before:
                                stalled = 0
                                log.info(
                                    'QQ 下载连接中断，已保留 %.1f MB，继续断点续传',
                                    current / (1024 * 1024),
                                )
                                await asyncio.sleep(0.2)
                                continue
                            stalled += 1
                            if stalled >= 8:
                                break
                            await asyncio.sleep(min(0.5 * stalled, 3.0))
                    failures.append(f'{url}: {last_error or "连续重试无进展"}')
                    log.warning('QQ 下载地址连续重试无进展: %s (%s)', url, last_error)
            raise QQDownloadError(version_key, failures)

    async def install_qq(
        self,
        version_key: str,
        auto_download: bool = True,
        progress_callback=None,
        stage_callback=None,
    ) -> Path | None:
        async def report(stage: str, percent: float, message: str) -> None:
            if not stage_callback:
                return
            result = stage_callback(stage, percent, message)
            if inspect.isawaitable(result):
                await result

        if version_key not in QQ_VERSIONS:
            raise ValueError(f'未知的 QQ 版本: {version_key}')
        await report('checking', 1, '正在检查 QQ 安装状态')
        info = QQ_VERSIONS[version_key]
        current = self.get_qq_executable(version_key)
        if current:
            self._record(
                version_key,
                {
                    'status': 'installed',
                    'executable': str(current),
                    'managed_install': bool((self.installed_versions.get(version_key) or {}).get('managed_install', False)),
                },
            )
            await report('completed', 100, 'QQ 已安装')
            return current
        package = self._version_path(version_key)
        if not package.is_file():
            if not auto_download:
                raise FileNotFoundError(f'QQ 安装包不存在: {package}')
            await report('downloading', 5, '正在下载 QQ 安装包')
            downloaded_package = await self.download_qq(version_key, progress_callback)
            if downloaded_package is None:
                return None
            package = downloaded_package

        await report('installing', 85, '正在安装 QQ')
        if info['platform'] == 'windows':
            result = await self._install_windows(package, self.install_dir / version_key, version_key)
        elif info['platform'] == 'linux':
            result = await self._install_linux(package, info, version_key)
        elif info['platform'] == 'macos':
            result = await self._install_macos(package, version_key)
        else:
            result = None
        await report('detecting', 95, '正在检测 QQ 可执行文件')
        await report('completed', 100, 'QQ 安装流程已完成')
        return result

    def _record(self, version_key: str, values: dict[str, Any]) -> None:
        record = dict(self.installed_versions.get(version_key) or {})
        record.update(values)
        record.setdefault('version', QQ_VERSIONS[version_key]['version'])
        self.installed_versions[version_key] = record
        self._save_config()

    async def _install_windows(self, installer_path: Path, install_path: Path, version_key: str) -> Path | None:
        command = [str(installer_path), '/S', f'/D={install_path}']
        try:
            await asyncio.to_thread(_run_command, command)
        except Exception as exc:
            self._record(
                version_key,
                {
                    'status': 'install_failed',
                    'installer': str(installer_path),
                    'error': str(exc),
                    'manual_command': ' '.join(command),
                },
            )
            raise RuntimeError(f'Windows QQ 静默安装失败: {exc}') from exc
        # QQ 安装程序可能在进程退出后才完成文件落盘，给标准安装目录和
        # 为腾讯公共安装目录留出一个短暂的探测窗口。
        executable = None
        for _ in range(10):
            executable = self.get_qq_executable(version_key)
            if executable:
                break
            await asyncio.sleep(0.5)
        if executable:
            self._record(
                version_key,
                {
                    'status': 'installed',
                    'installer': str(installer_path),
                    'install_path': str(install_path),
                    'executable': str(executable),
                    'managed_install': self._under_root(executable, install_path),
                },
            )
            return executable
        self._record(
            version_key,
            {
                'status': 'manual_install_required',
                'installer': str(installer_path),
                'install_path': str(install_path),
                'manual_command': ' '.join(command),
            },
        )
        return installer_path

    async def _install_linux(self, package_path: Path, version_info: dict[str, Any], version_key: str) -> Path | None:
        package_type = version_info.get('package')
        if not package_type:
            raise RuntimeError('Linux QQ 安装包类型未知')

        # 所有 Linux 环境均优先解包到 data/qq/client，不污染系统目录，也不需要 sudo。
        try:
            executable = await asyncio.to_thread(self._extract_linux_package, package_path, package_type, version_key)
            self._record(
                version_key,
                {
                    'status': 'installed',
                    'package': str(package_path),
                    'executable': str(executable),
                    'install_path': str(self.install_dir / version_key),
                    'managed_install': True,
                    'install_mode': 'private_extract',
                },
            )
            return executable
        except Exception as exc:
            log.info('QQ 私有目录解包失败，将尝试系统包管理器: %s', exc)

        prefix: list[str] = []
        if not _is_root():
            sudo = shutil.which('sudo')
            if not sudo:
                self._record(
                    version_key,
                    {
                        'status': 'install_requires_privilege',
                        'package': str(package_path),
                        'error': '普通用户无法完成私有解包，且系统未安装 sudo',
                        'manual_command': self._linux_manual_command(package_path, package_type),
                    },
                )
                return package_path
            try:
                # 只使用已有 sudo 凭据，绝不在 Web 服务中等待密码输入。
                await asyncio.to_thread(_run_command, [sudo, '-n', '-v'], 15)
            except Exception as exc:
                message = 'sudo 无免密权限，无法由后台服务完成系统级安装'
                self._record(
                    version_key,
                    {
                        'status': 'install_requires_privilege',
                        'package': str(package_path),
                        'error': f'{message}: {exc}',
                        'manual_command': self._linux_manual_command(package_path, package_type),
                    },
                )
                return package_path
            prefix = [sudo, '-n']

        if package_type == 'deb':
            if not shutil.which('dpkg'):
                raise RuntimeError('当前 Linux 没有 dpkg，不能安装 deb 包')
            commands = [prefix + ['dpkg', '-i', str(package_path)]]
            if shutil.which('apt-get'):
                commands.append(prefix + ['apt-get', 'install', '-f', '-y'])
        elif package_type == 'rpm':
            if shutil.which('dnf'):
                commands = [prefix + ['dnf', 'install', '-y', str(package_path)]]
            elif shutil.which('yum'):
                commands = [prefix + ['yum', 'install', '-y', str(package_path)]]
            elif shutil.which('rpm'):
                commands = [prefix + ['rpm', '-Uvh', str(package_path)]]
            else:
                raise RuntimeError('当前 Linux 没有 rpm/dnf/yum，不能安装 rpm 包')
        else:
            raise RuntimeError(f'不支持的 Linux 安装包类型: {package_type}')

        try:
            for command in commands:
                await asyncio.to_thread(_run_command, command)
        except Exception as exc:
            self._record(
                version_key,
                {
                    'status': 'install_failed',
                    'package': str(package_path),
                    'error': str(exc),
                    'manual_command': self._linux_manual_command(package_path, package_type),
                },
            )
            raise RuntimeError(f'Linux QQ 安装失败: {exc}') from exc

        detected_executable = self.get_qq_executable(version_key)
        self._record(
            version_key,
            {
                'status': 'installed' if detected_executable else 'installed_path_unknown',
                'package': str(package_path),
                'executable': str(detected_executable) if detected_executable else '',
                'managed_install': True,
                'install_mode': 'system_package',
            },
        )
        return detected_executable or package_path

    def _extract_linux_package(self, package_path: Path, package_type: str, version_key: str) -> Path:
        install_root = (self.install_dir / version_key).resolve()
        if not self._under_root(install_root, self.install_dir) or install_root == self.install_dir.resolve():
            raise RuntimeError('拒绝使用 QQ 管理器目录之外的安装路径')
        temp_root = Path(tempfile.mkdtemp(prefix=f'.{version_key}-', dir=str(self.install_dir)))
        try:
            if package_type == 'deb':
                self._extract_deb(package_path, temp_root)
            elif package_type == 'rpm':
                self._extract_rpm(package_path, temp_root)
            else:
                raise RuntimeError(f'不支持的 Linux 安装包类型: {package_type}')

            executable = self._find_managed_qq(temp_root)
            if not executable:
                raise RuntimeError('安装包解包成功，但未找到 QQ 可执行文件')
            if install_root.exists():
                shutil.rmtree(install_root)
            os.replace(temp_root, install_root)
            executable = self._find_managed_qq(install_root)
            if not executable:
                raise RuntimeError('QQ 可执行文件安装后不可访问')
            return executable
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise

    @staticmethod
    def _extract_deb(package_path: Path, target: Path) -> None:
        dpkg_deb = shutil.which('dpkg-deb')
        if dpkg_deb:
            _run_command([dpkg_deb, '-x', str(package_path), str(target)], timeout=300)
            return
        ar = shutil.which('ar')
        tar = shutil.which('tar')
        if not ar or not tar:
            raise RuntimeError('当前系统没有 dpkg-deb，且缺少 ar/tar，无法解包 DEB')
        with tempfile.TemporaryDirectory(prefix='.qq-deb-', dir=str(target.parent)) as temporary:
            work_dir = Path(temporary)
            listing = subprocess.run(
                [ar, 't', str(package_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if listing.returncode:
                raise RuntimeError(f'DEB 文件目录读取失败: {(listing.stderr or listing.stdout).strip()}')
            data_member = next(
                (line.strip() for line in listing.stdout.splitlines() if line.strip().startswith('data.tar.')),
                '',
            )
            if not data_member or Path(data_member).name != data_member:
                raise RuntimeError('DEB 安装包缺少有效的 data.tar 数据段')
            extracted = subprocess.run(
                [ar, 'x', str(package_path), data_member],
                cwd=str(work_dir),
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if extracted.returncode:
                raise RuntimeError(f'DEB 数据段提取失败: {(extracted.stderr or extracted.stdout).strip()}')
            archive = work_dir / data_member
            members = subprocess.run(
                [tar, '-tf', str(archive)],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if members.returncode:
                raise RuntimeError(f'DEB 数据目录读取失败: {(members.stderr or members.stdout).strip()}')
            for name in members.stdout.splitlines():
                normalized = name.replace('\\', '/').lstrip('./')
                if name.startswith('/') or '..' in Path(normalized).parts:
                    raise RuntimeError('DEB 安装包包含不安全的文件路径')
            unpacked = subprocess.run(
                [tar, '-xf', str(archive), '-C', str(target), '--no-same-owner'],
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if unpacked.returncode:
                raise RuntimeError(f'DEB 解包失败: {(unpacked.stderr or unpacked.stdout).strip()}')

    @staticmethod
    def _extract_rpm(package_path: Path, target: Path) -> None:
        bsdtar = shutil.which('bsdtar')
        if bsdtar:
            _run_command([bsdtar, '-xf', str(package_path), '-C', str(target)], timeout=300)
            return
        rpm2cpio = shutil.which('rpm2cpio')
        cpio = shutil.which('cpio')
        if not rpm2cpio or not cpio:
            raise RuntimeError('当前系统没有 bsdtar 或 rpm2cpio/cpio，无法在无 root 模式解包 RPM')
        producer = subprocess.Popen([rpm2cpio, str(package_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if producer.stdout is None:
            producer.kill()
            raise RuntimeError('RPM 解包失败：无法读取 rpm2cpio 输出')
        result = subprocess.run([cpio, '-idm'], cwd=str(target), stdin=producer.stdout, capture_output=True, text=True, timeout=300)
        producer.stdout.close()
        producer_stderr = producer.stderr.read().decode(errors='replace').strip() if producer.stderr else ''
        producer_code = producer.wait(timeout=30)
        if producer_code or result.returncode:
            detail = (result.stderr or producer_stderr or result.stdout or '').strip()
            raise RuntimeError(f'RPM 解包失败，退出码 {result.returncode or producer_code}: {detail}')

    def _find_managed_qq(self, root: Path) -> Path | None:
        candidates = [
            root / 'opt' / 'QQ' / 'qq',
            root / 'opt' / 'QQ' / 'QQ',
            root / 'opt' / 'qq' / 'qq',
            root / 'opt' / 'qq' / 'QQ',
            root / 'usr' / 'lib' / 'QQ' / 'qq',
            root / 'usr' / 'lib' / 'QQ' / 'QQ',
            root / 'usr' / 'bin' / 'qq',
            root / 'usr' / 'bin' / 'linuxqq',
        ]
        for path in candidates:
            try:
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if not self._under_root(resolved, root):
                    continue
                if not os.access(resolved, os.X_OK):
                    resolved.chmod(resolved.stat().st_mode | stat.S_IXUSR)
                return resolved
            except OSError:
                continue
        return None

    @staticmethod
    def _linux_manual_command(package_path: Path, package_type: str) -> str:
        if package_type == 'deb':
            return f'sudo dpkg -i "{package_path}" && sudo apt-get install -f -y'
        return f'sudo dnf install -y "{package_path}"'

    async def _install_macos(self, dmg_path: Path, version_key: str) -> Path | None:
        self._record(
            version_key,
            {
                'status': 'manual_install_required',
                'dmg': str(dmg_path),
                'managed_install': False,
            },
        )
        return dmg_path

    @staticmethod
    def _under_root(path: Path, root: Path) -> bool:
        """仅当路径位于管理器拥有的根目录内时返回真。"""
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            return False

    async def uninstall_qq(self, version_key: str | None = None) -> dict[str, Any]:
        """移除由本管理器创建的 QQ 安装。

        仅检测到的系统 QQ 不会被删除。Linux 安装包只有在原始安装记录能证明
        其归框架管理时，才会通过系统包管理器卸载。
        """
        key = version_key or self.detect_platform()
        if not key or key not in QQ_VERSIONS:
            raise ValueError('当前系统没有可卸载的 QQ 版本')

        record = dict(self.installed_versions.get(key) or {})
        previous_executable = self.get_qq_executable(key)
        removed: list[str] = []
        manual: list[str] = []
        managed_root = (self.install_dir / key).resolve()
        if managed_root.exists():
            if not self._under_root(managed_root, self.install_dir) or managed_root == self.install_dir.resolve():
                raise RuntimeError('拒绝删除不受 QQ 管理器控制的路径')
            shutil.rmtree(managed_root)
            removed.append(str(managed_root))

        if record.get('install_mode') == 'system_package' and QQ_VERSIONS[key].get('platform') == 'linux':
            package_name = 'linuxqq'
            info = self.platform_info()
            if _is_root():
                prefix: list[str] = []
            elif info.get('sudo'):
                prefix = ['sudo', '-n']
            else:
                prefix = []
            if not prefix and not _is_root():
                manual.append(self._linux_uninstall_command(package_name, QQ_VERSIONS[key].get('package', 'deb')))
            else:
                package_type = QQ_VERSIONS[key].get('package')
                if package_type == 'deb' and shutil.which('apt-get'):
                    command = prefix + ['apt-get', 'remove', '-y', package_name]
                elif package_type == 'rpm' and shutil.which('dnf'):
                    command = prefix + ['dnf', 'remove', '-y', package_name]
                elif package_type == 'rpm' and shutil.which('yum'):
                    command = prefix + ['yum', 'remove', '-y', package_name]
                elif package_type == 'rpm' and shutil.which('rpm'):
                    command = prefix + ['rpm', '-e', package_name]
                else:
                    command = []
                if command:
                    try:
                        await asyncio.to_thread(_run_command, command)
                        removed.append('system package: ' + package_name)
                    except Exception as exc:
                        manual.append(self._linux_uninstall_command(package_name, package_type or 'deb'))
                        record['uninstall_error'] = str(exc)
                else:
                    manual.append(self._linux_uninstall_command(package_name, package_type or 'deb'))

        executable = self.get_qq_executable(key)
        if executable and not removed and not manual:
            manual.append('当前 QQ 位于系统目录，未自动删除；请在系统应用管理器中卸载')

        if manual:
            record.update({'status': 'uninstall_requires_manual', 'manual_uninstall': manual})
            self.installed_versions[key] = record
        else:
            self.installed_versions.pop(key, None)
        self._save_config()
        return {
            'version_key': key,
            'removed': removed,
            'manual': manual,
            'previous_executable': str(previous_executable) if previous_executable else None,
            'executable': str(executable) if executable else None,
        }

    async def cleanup_qq(self, version_key: str | None = None) -> dict[str, Any]:
        """仅删除本管理器拥有的 QQ 安装缓存文件。"""
        keys = [version_key] if version_key else list(QQ_VERSIONS)
        removed: list[str] = []
        for key in keys:
            if key not in QQ_VERSIONS:
                continue
            package = self._version_path(key)
            partial = package.with_suffix(package.suffix + '.part')
            for path in (package, partial):
                if path.is_file() and self._under_root(path, self.download_dir):
                    path.unlink()
                    removed.append(str(path))
        return {'removed': removed, 'version_key': version_key}

    @staticmethod
    def _linux_uninstall_command(package_name: str, package_type: str) -> str:
        if package_type == 'rpm':
            return f'sudo dnf remove -y {package_name}'
        return f'sudo apt-get remove -y {package_name}'

    @staticmethod
    def _existing(paths: list[Path]) -> Path | None:
        for path in paths:
            if path.is_file():
                return path.resolve()
        return None

    def get_qq_executable(self, version_key: str | None = None) -> Path | None:
        version_key = version_key or self.detect_platform()
        if not version_key or version_key not in QQ_VERSIONS:
            return None
        recorded = self.installed_versions.get(version_key) or {}
        recorded_path = recorded.get('executable')
        if recorded_path:
            found = self._existing([Path(str(recorded_path))])
            if found:
                return found

        key = version_key
        managed_root = self.install_dir / key
        managed_candidates: list[Path] = []
        if 'windows' in key:
            managed_candidates.extend(
                [
                    managed_root / 'QQ.exe',
                    *sorted(managed_root.glob('versions/*/QQ.exe')),
                ]
            )
        elif 'linux' in key:
            managed_candidates.extend(
                [
                    managed_root / 'qq',
                    managed_root / 'QQ',
                    managed_root / 'opt' / 'QQ' / 'qq',
                    managed_root / 'opt' / 'QQ' / 'QQ',
                    managed_root / 'opt' / 'qq' / 'qq',
                    managed_root / 'usr' / 'lib' / 'QQ' / 'qq',
                ]
            )
        managed = self._existing(managed_candidates)
        if managed:
            return managed
        if QQ_VERSIONS[key].get('channel') == 'legacy':
            return None
        if 'windows' in key:
            configured = os.environ.get('QQ_PATH', '').strip()
            roots = []
            if configured:
                roots.append(Path(configured).expanduser())
            roots.extend(
                [
                    self.install_dir / key,
                    Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Tencent' / 'QQ',
                    Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Tencent' / 'QQNT',
                    Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Tencent' / 'QQ',
                    Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Programs' / 'Tencent' / 'QQ',
                    Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Programs' / 'Tencent' / 'QQNT',
                    Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Tencent' / 'QQ',
                    Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Tencent' / 'QQNT',
                ]
            )
            # QQNT 经常安装在其他磁盘，仅探测常见固定目录，避免递归扫描整块磁盘。
            for drive in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                roots.extend(
                    [
                        Path(f'{drive}:\\QQNT'),
                        Path(f'{drive}:\\Tencent\\QQNT'),
                    ]
                )
            candidates = []
            for root in roots:
                if root.suffix.lower() == '.exe':
                    candidates.append(root)
                else:
                    candidates.append(root / 'QQ.exe')
            for root in roots:
                if root.suffix.lower() != '.exe':
                    candidates.extend(sorted(root.glob('versions/*/QQ.exe')))
            return self._existing(candidates)
        if 'linux' in key:
            candidates = [Path(item) for item in [shutil.which('qq'), shutil.which('linuxqq')] if item]
            candidates.extend(
                [
                    Path('/opt/QQ/qq'),
                    Path('/opt/QQ/QQ'),
                    Path('/usr/bin/qq'),
                    Path('/usr/local/bin/qq'),
                    Path('/usr/lib/QQ/qq'),
                    Path.home() / '.local' / 'share' / 'QQ' / 'qq',
                    self.install_dir / key / 'qq',
                    self.install_dir / key / 'QQ',
                    self.install_dir / key / 'opt' / 'QQ' / 'qq',
                    self.install_dir / key / 'opt' / 'QQ' / 'QQ',
                    self.install_dir / key / 'opt' / 'qq' / 'qq',
                    self.install_dir / key / 'usr' / 'lib' / 'QQ' / 'qq',
                ]
            )
            return self._existing(candidates)
        if key == 'macos':
            return self._existing(
                [
                    Path('/Applications/QQ.app/Contents/MacOS/QQ'),
                    Path.home() / 'Applications' / 'QQ.app' / 'Contents' / 'MacOS' / 'QQ',
                ]
            )
        return None

    def list_available_versions(self) -> list[dict[str, Any]]:
        platform_key = self.detect_platform()
        result = []
        for key, info in QQ_VERSIONS.items():
            downloaded = self._version_path(key).is_file()
            executable = self.get_qq_executable(key)
            compatible = self.is_compatible(key)
            result.append(
                {
                    'key': key,
                    'version': info['version'],
                    'platform': info['platform'],
                    'arch': info.get('arch', 'unknown'),
                    'package': info.get('package'),
                    'label': info.get('label', info['version']),
                    'channel': info.get('channel', 'latest'),
                    'size': f'{info.get("size", 0) // (1024 * 1024)}MB' if info.get('size') else 'unknown',
                    'url': info['url'],
                    'downloaded': downloaded,
                    'installed': bool(executable),
                    'compatible': compatible,
                    'recommended': key == platform_key,
                }
            )
        result.sort(key=lambda item: (not item['compatible'], item['channel'] != 'latest', item['platform'], item['arch']))
        return result

    def get_install_status(self) -> dict[str, Any]:
        platform_key = self.detect_platform()
        executable = self.get_qq_executable(platform_key)
        return {
            'current_platform': platform_key,
            'platform_info': self.platform_info(),
            'recommended': self.get_recommended_version(),
            'installed': bool(executable),
            'installed_versions': self.installed_versions,
            'qq_executable': str(executable) if executable else None,
            'install_dir': str(self.install_dir),
            'download_dir': str(self.download_dir),
            'managed_install': bool(platform_key and (self.installed_versions.get(platform_key) or {}).get('managed_install', False)),
            'available_versions': self.list_available_versions(),
            'headless': {
                'supported': platform.system().lower() in {'windows', 'linux'},
                'mode': 'xvfb' if platform.system().lower() == 'linux' else 'electron',
                'uses_framework_port': True,
            },
        }


_qq_manager: QQManager | None = None


def get_qq_manager(base_dir: str | Path | None = None) -> QQManager:
    """返回进程级管理器，其根目录始终位于框架数据目录内。"""
    global _qq_manager
    resolved = Path(base_dir or 'data/qq').expanduser().resolve()
    if _qq_manager is None or _qq_manager.base_dir != resolved:
        _qq_manager = QQManager(resolved)
    return _qq_manager
