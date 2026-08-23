"""带路径与容量限制的 ZIP 解压工具。"""

from __future__ import annotations

import os
import shutil
import stat
import zipfile

MAX_ARCHIVE_FILES = 20_000
MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024
MAX_MEMBER_SIZE = 512 * 1024 * 1024


def is_within(base_dir: str, target: str) -> bool:
    base = os.path.realpath(base_dir)
    real = os.path.realpath(target)
    return real == base or real.startswith(base + os.sep)


def safe_extractall(
    zf: zipfile.ZipFile,
    dest_dir: str,
    *,
    max_files: int = MAX_ARCHIVE_FILES,
    max_size: int = MAX_ARCHIVE_SIZE,
    max_member_size: int = MAX_MEMBER_SIZE,
) -> None:
    """校验路径、链接、文件数量与大小后解压 ZIP。"""
    validate_archive(zf, max_files=max_files, max_size=max_size, max_member_size=max_member_size)
    root = os.path.realpath(dest_dir)
    os.makedirs(root, exist_ok=True)
    for member in zf.infolist():
        name = member.filename.replace('\\', '/')
        target = os.path.join(root, name)
        if not is_within(root, target):
            raise ValueError(f'非法压缩包成员路径: {member.filename!r}')
        if member.is_dir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        with zf.open(member) as src, open(target, 'wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)


def validate_archive(
    zf: zipfile.ZipFile,
    *,
    max_files: int = MAX_ARCHIVE_FILES,
    max_size: int = MAX_ARCHIVE_SIZE,
    max_member_size: int = MAX_MEMBER_SIZE,
) -> None:
    """仅校验压缩包元数据，不执行解压。"""
    members = zf.infolist()
    if len(members) > max_files:
        raise ValueError(f'压缩包文件过多: {len(members)} > {max_files}')

    total_size = 0
    for member in members:
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError(f'压缩包不允许符号链接: {member.filename!r}')
        if member.file_size > max_member_size:
            raise ValueError(f'压缩包成员过大: {member.filename!r}')
        total_size += member.file_size
        if total_size > max_size:
            raise ValueError(f'压缩包解压后超过限制: {max_size} 字节')
