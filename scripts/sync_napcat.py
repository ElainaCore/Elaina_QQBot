"""从 NapCat 源码同步内置 QQ 的版本 / 偏移数据表。

内置 QQ 链路的应用 ID (appid)、QUA、以及原始包 Hook 偏移均跟随 NapCat：

| 本仓库文件 | NapCat 来源 |
| --- | --- |
| ``core/runtime/embedded/bridge/qq_appid.json`` | ``packages/napcat-core/external/appid.json`` |
| ``core/runtime/embedded/native/packet/packet_offsets.json`` | ``packages/napcat-core/external/napi2native.json`` |
| ``core/runtime/embedded/native/events/event_offsets.json`` | ``packages/napcat-core/external/packet.json`` |

用法::

    python scripts/sync_napcat.py /path/to/NapCatQQ
    python scripts/sync_napcat.py /path/to/NapCatQQ --check   # 只校验是否已同步

同步后请运行回归测试: ``python -m pytest tests/test_napcat_alignment.py``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BRIDGE = _ROOT / 'core' / 'runtime' / 'embedded' / 'bridge'
_NATIVE = _ROOT / 'core' / 'runtime' / 'embedded' / 'native'


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SystemExit(f'读取失败 {path}: {exc}') from exc
    if not isinstance(value, dict):
        raise SystemExit(f'期望 JSON 对象: {path}')
    return value


def _build_appid_table(source: dict) -> dict:
    """``{version}|{version-arch: {appid, qua}}`` -> 仅保留无 arch 的版本键。"""
    table: dict[str, dict[str, object]] = {}
    for version, info in source.items():
        if version.count('-') > 1:  # 带架构后缀的键由运行时按平台解析
            continue
        if not isinstance(info, dict) or info.get('appid') is None:
            continue
        table[version] = {'appid': info['appid'], 'qua': str(info.get('qua') or '')}

    def sort_key(item: str) -> tuple[str, int]:
        product, _, build = item.partition('-')
        return product, int(build) if build.isdigit() else 0

    return {key: table[key] for key in sorted(table, key=sort_key)}


def _build_offsets(source: dict) -> dict:
    """保留含 send/recv 的条目，地址统一大写。"""
    table = {}
    for key, value in source.items():
        if not isinstance(value, dict):
            continue
        send, recv = value.get('send'), value.get('recv')
        if not send or not recv:
            continue
        table[key] = {'send': str(send).upper(), 'recv': str(recv).upper()}
    return table


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _same(path: Path, payload: dict) -> bool:
    try:
        return json.loads(path.read_text(encoding='utf-8')) == payload
    except (OSError, ValueError):
        return False


def sync(napcat_root: Path, *, check: bool = False) -> int:
    external = napcat_root / 'packages' / 'napcat-core' / 'external'
    jobs = [
        (external / 'appid.json', _BRIDGE / 'qq_appid.json', _build_appid_table),
        (external / 'napi2native.json', _NATIVE / 'packet' / 'packet_offsets.json', _build_offsets),
        (external / 'packet.json', _NATIVE / 'events' / 'event_offsets.json', _build_offsets),
    ]

    drift = 0
    for source_path, target_path, builder in jobs:
        if not source_path.is_file():
            raise SystemExit(f'未找到 NapCat 数据文件: {source_path}')
        payload = builder(_load(source_path))
        if _same(target_path, payload):
            print(f'[已同步] {target_path.relative_to(_ROOT)} ({len(payload)} 条)')
            continue
        if check:
            drift += 1
            print(f'[需更新] {target_path.relative_to(_ROOT)} ({len(payload)} 条)')
            continue
        _write(target_path, payload)
        print(f'[已更新] {target_path.relative_to(_ROOT)} ({len(payload)} 条)')

    if check and drift:
        print(f'\n{drift} 个数据表与 NapCat 不一致，请运行同步。', file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='从 NapCat 源码同步内置 QQ 数据表')
    parser.add_argument('napcat_root', type=Path, help='NapCatQQ 仓库根目录')
    parser.add_argument('--check', action='store_true', help='只校验，不写入 (不一致时返回非零)')
    args = parser.parse_args()
    return sync(args.napcat_root.expanduser().resolve(), check=args.check)


if __name__ == '__main__':
    raise SystemExit(main())
