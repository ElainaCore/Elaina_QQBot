"""QQ 安装包归档内容的安全校验与流式目录读取。"""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path


def validate_archive_member_name(name: str, package_type: str) -> None:
    """拒绝绝对路径、父目录跳转和 Windows 盘符路径。"""
    normalized = str(name or '').replace('\\', '/')
    if not normalized or '\x00' in normalized:
        raise RuntimeError(f'{package_type} 安装包包含无效的文件路径')
    first = normalized.split('/', 1)[0]
    if normalized.startswith('/') or (len(first) >= 2 and first[1] == ':'):
        raise RuntimeError(f'{package_type} 安装包包含不安全的绝对路径: {name!r}')
    if '..' in normalized.split('/'):
        raise RuntimeError(f'{package_type} 安装包包含父目录跳转: {name!r}')


def validate_archive_listing(listing: str, package_type: str) -> None:
    for name in listing.splitlines():
        if name.strip():
            validate_archive_member_name(name.strip(), package_type)


def validate_archive_link(member_name: str, link_name: str, package_type: str, *, hardlink: bool = False) -> None:
    """按 tar 语义解析相对链接，并拒绝解析到归档根目录之外。"""
    validate_archive_member_name(member_name, package_type)
    normalized = str(link_name or '').replace('\\', '/')
    first = normalized.split('/', 1)[0]
    if not normalized or '\x00' in normalized or normalized.startswith('/') or (len(first) >= 2 and first[1] == ':'):
        raise RuntimeError(f'{package_type} 安装包包含不安全的链接目标: {link_name!r}')

    member_parts = [part for part in member_name.replace('\\', '/').split('/') if part not in {'', '.'}]
    resolved = [] if hardlink else member_parts[:-1]
    for part in normalized.split('/'):
        if part in {'', '.'}:
            continue
        if part == '..':
            if not resolved:
                raise RuntimeError(f'{package_type} 安装包链接逃逸归档根目录: {link_name!r}')
            resolved.pop()
        else:
            resolved.append(part)


def validate_deb_archive(package_path: Path, dpkg_deb: str) -> None:
    """流式检查 DEB 的 data tar，不把未验证成员写入磁盘。"""
    producer = subprocess.Popen(
        [dpkg_deb, '--fsys-tarfile', str(package_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if producer.stdout is None:
        producer.kill()
        raise RuntimeError('DEB 文件目录读取失败：无法读取 dpkg-deb 输出')
    error: Exception | None = None
    try:
        with tarfile.open(fileobj=producer.stdout, mode='r|*') as archive:
            for member in archive:
                validate_archive_member_name(member.name, 'DEB')
                if member.issym():
                    validate_archive_link(member.name, member.linkname, 'DEB 链接')
                elif member.islnk():
                    validate_archive_link(member.name, member.linkname, 'DEB 硬链接', hardlink=True)
    except Exception as exc:
        error = exc
    finally:
        producer.stdout.close()
    producer_stderr = producer.stderr.read().decode(errors='replace').strip() if producer.stderr else ''
    producer_code = producer.wait(timeout=30)
    if error is not None:
        if isinstance(error, RuntimeError):
            raise error
        raise RuntimeError(f'DEB 文件目录读取失败: {error}') from error
    if producer_code:
        raise RuntimeError(f'DEB 文件目录读取失败: {producer_stderr or producer_code}')


def run_cpio_listing(package_path: Path, rpm2cpio: str, cpio: str) -> str:
    producer = subprocess.Popen([rpm2cpio, str(package_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if producer.stdout is None:
        producer.kill()
        raise RuntimeError('RPM 文件目录读取失败：无法读取 rpm2cpio 输出')
    result = subprocess.run([cpio, '-it'], stdin=producer.stdout, capture_output=True, text=True, timeout=300)
    producer.stdout.close()
    producer_stderr = producer.stderr.read().decode(errors='replace').strip() if producer.stderr else ''
    producer_code = producer.wait(timeout=30)
    if producer_code or result.returncode:
        detail = (result.stderr or producer_stderr or result.stdout or '').strip()
        raise RuntimeError(f'RPM 文件目录读取失败，退出码 {result.returncode or producer_code}: {detail}')
    return result.stdout

