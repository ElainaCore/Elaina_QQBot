"""Bump the framework's patch version with decimal carry."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / 'VERSION'
PYPROJECT = ROOT / 'pyproject.toml'
VERSION_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


def read_version() -> tuple[int, int, int]:
    value = VERSION_FILE.read_text(encoding='utf-8').strip()
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise SystemExit(f'invalid VERSION: {value!r}')
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def bump(version: tuple[int, int, int]) -> tuple[int, int, int]:
    major, minor, patch = version
    patch += 1
    if patch >= 10:
        patch = 0
        minor += 1
    if minor >= 10:
        minor = 0
        major += 1
    return major, minor, patch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--bump', action='store_true')
    args = parser.parse_args()
    version = bump(read_version()) if args.bump else read_version()
    value = f'{version[0]}.{version[1]}.{version[2]}'
    if args.bump:
        VERSION_FILE.write_text(value + '\n', encoding='utf-8')
        text = PYPROJECT.read_text(encoding='utf-8')
        text, count = re.subn(r'(?m)^(version\s*=\s*["\'])[^"\']+(["\'])$', rf'\g<1>{value}\g<2>', text, count=1)
        if count != 1:
            raise SystemExit('project version entry not found in pyproject.toml')
        PYPROJECT.write_text(text, encoding='utf-8')
    print(value)


if __name__ == '__main__':
    main()
