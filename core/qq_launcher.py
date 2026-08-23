"""通过内置运行时启动 QQ NT。"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import shutil
import sys
from pathlib import Path

log = logging.getLogger('ElainaQQ.qq_launcher')


class QQLauncher:
    """构建隔离的 QQ 进程命令，同时复用同一份 QQ 安装。"""

    def __init__(self, executable: Path, bridge_entry: Path):
        self.executable = Path(executable).resolve()
        self.bridge_entry = Path(bridge_entry).resolve()
        self.launch_env: dict[str, str] = {}

    def app_dir(self) -> Path:
        base = self.executable.parent
        candidates: list[Path] = []
        if sys.platform == 'darwin':
            candidates.append(base.parent / 'Resources' / 'app')

        versions_dir = base / 'versions'
        if versions_dir.is_dir():
            version_dirs = [item for item in versions_dir.iterdir() if item.is_dir()]
            version_dirs.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
            for version_dir in version_dirs:
                candidates.extend((version_dir / 'resources' / 'app', version_dir))

        candidates.extend(
            (
                base / 'resources' / 'app',
                base / 'resources' / 'app' / 'versions' / 'app',
            )
        )
        for candidate in candidates:
            if candidate.is_dir() and (candidate / 'package.json').is_file():
                return candidate
        raise FileNotFoundError(f'未找到 QQ Electron app 目录: {self.executable}')

    @staticmethod
    def _linux_arch() -> str:
        machine = platform.machine().lower()
        if machine in {'x86_64', 'amd64', 'x64'}:
            return 'amd64'
        if machine in {'aarch64', 'arm64', 'armv8', 'armv8l'} or machine.startswith('arm64'):
            return 'arm64'
        raise RuntimeError(f'内置 QQ 暂不支持 Linux 架构: {machine or "unknown"}')

    def install_loader(self) -> Path:
        app_dir = self.app_dir()
        package_path = app_dir / 'package.json'
        loader_name = 'elainaqq-loader.cjs'
        loader_path = app_dir / loader_name
        package_text = package_path.read_text(encoding='utf-8')
        package = json.loads(package_text)
        backup = package_path.with_name('package.json.elainaqq-original')
        original_main = package.get('main', '')
        if backup.is_file():
            with contextlib.suppress(OSError, ValueError):
                original_main = json.loads(backup.read_text(encoding='utf-8')).get(
                    'main',
                    original_main,
                )
        loader_text = (
            "const path = require('path');\n"
            "const { pathToFileURL } = require('url');\n"
            'const entry = process.env.ELAINAQQ_BRIDGE_ENTRY;\n'
            f'const originalMain = {json.dumps(str(original_main), ensure_ascii=False)};\n'
            "const skipOriginalMain = process.env.ELAINAQQ_EMBEDDED === '1';\n"
            'const originalDlopen = process.dlopen;\n'
            'let bridgeStarted = false;\n'
            'function startBridge(filename) {\n'
            '  if (bridgeStarted || !entry) return;\n'
            '  bridgeStarted = true;\n'
            '  if (filename) process.env.ELAINAQQ_WRAPPER_PATH = filename;\n'
            '  process.dlopen = originalDlopen;\n'
            '  import(pathToFileURL(entry).href).catch((error) => {\n'
            "    console.error('[ElainaQQ] 运行时加载失败:', error);\n"
            '    process.exitCode = 1;\n'
            '  });\n'
            '}\n'
            'process.dlopen = function(module, filename, flags) {\n'
            '  const result = flags === undefined\n'
            '    ? originalDlopen(module, filename)\n'
            '    : originalDlopen(module, filename, flags);\n'
            "  if (!bridgeStarted && typeof filename === 'string' && filename.includes('wrapper.node')) {\n"
            '    globalThis.__ELAINAQQ_WRAPPER__ = module.exports;\n'
            '    startBridge(filename);\n'
            '  }\n'
            '  return result;\n'
            '};\n'
            'try {\n'
            '  if (!skipOriginalMain && originalMain) require(path.resolve(__dirname, originalMain));\n'
            "  if (!bridgeStarted) startBridge('');\n"
            '} catch (error) {\n'
            "  console.error('[ElainaQQ] QQ 主入口加载失败:', error);\n"
            '  process.exitCode = 1;\n'
            '}\n'
        )
        if not loader_path.is_file() or loader_path.read_text(encoding='utf-8') != loader_text:
            loader_path.write_text(loader_text, encoding='utf-8')
        expected_main = f'./{loader_name}'
        if package.get('main') != expected_main:
            if not backup.exists():
                backup_package = dict(package)
                backup_package['main'] = original_main
                backup.write_text(
                    json.dumps(backup_package, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
            package['main'] = expected_main
            temporary = package_path.with_suffix('.elainaqq.tmp')
            temporary.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, package_path)
            log.info('已安装 QQ 内置加载器: %s', package_path)
        return loader_path

    def _linux_command(
        self,
        data_dir: Path,
        quick_login: str = '',
        display: str = '',
    ) -> list[str]:
        self.install_loader()
        if display:
            self.launch_env = {
                'DISPLAY': display,
                'ELAINAQQ_HEADLESS_RUNTIME': 'shared-xvfb',
            }
            command = [
                str(self.executable),
                '--no-sandbox',
            ]
        else:
            xvfb_run = shutil.which('xvfb-run')
            if not xvfb_run:
                raise RuntimeError('Linux 无头运行需要 Xvfb，请先安装 xorg-x11-server-Xvfb 或 xvfb')
            self.launch_env = {'ELAINAQQ_HEADLESS_RUNTIME': 'xvfb'}
            command = [
                xvfb_run,
                '-a',
                '-s',
                '-screen 0 1080x760x16 +extension GLX +render',
                str(self.executable),
                '--no-sandbox',
            ]
        if quick_login:
            command.extend(('-q', quick_login))
        return command

    def writable_runtime(self, runtime_root: Path, force_copy: bool = False) -> QQLauncher:
        app_dir = self.app_dir()
        package_path = app_dir / 'package.json'
        if not force_copy and os.access(app_dir, os.W_OK) and os.access(package_path, os.W_OK):
            return self

        runtime_root = Path(runtime_root).resolve()
        runtime_root.mkdir(parents=True, exist_ok=True)
        target_dir = runtime_root / self.executable.parent.name
        target_executable = target_dir / self.executable.name
        marker = target_dir / '.elainaqq-source.json'
        source_state = {
            'executable': str(self.executable),
            'mtime_ns': self.executable.stat().st_mtime_ns,
            'size': self.executable.stat().st_size,
            'package_mtime_ns': package_path.stat().st_mtime_ns,
            'package_size': package_path.stat().st_size,
        }
        current_state = None
        if marker.is_file():
            try:
                current_state = json.loads(marker.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                current_state = None
        if not target_executable.is_file() or current_state != source_state:
            shutil.copytree(self.executable.parent, target_dir, dirs_exist_ok=True, symlinks=True)
            marker.write_text(json.dumps(source_state, ensure_ascii=False, indent=2), encoding='utf-8')
        return QQLauncher(target_executable, self.bridge_entry)

    def command(
        self,
        data_dir: Path,
        headless: bool = False,
        single_process: bool = False,
        quick_login: str = '',
        linux_display: str = '',
    ) -> list[str]:
        del single_process
        self.launch_env = {}
        if sys.platform.startswith('linux'):
            return self._linux_command(data_dir, quick_login, linux_display)
        if sys.platform == 'win32':
            self.install_loader()
            args = [str(self.executable), '--user-data-dir', str(data_dir / 'chromium')]
            if headless:
                args.insert(1, '--headless')
            if quick_login:
                args.extend(('-q', quick_login))
            return args
        self.install_loader()
        args = [str(self.executable), '--user-data-dir', str(data_dir / 'chromium')]
        if quick_login:
            args.extend(('-q', quick_login))
        return args
