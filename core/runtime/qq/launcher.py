"""通过内置运行时启动 QQ NT。"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import posixpath
import shutil
import stat
import sys
from pathlib import Path

log = logging.getLogger('ElainaQQ.qq_launcher')

_WINDOWS_APPID_TABLE = (
    Path(__file__).parents[1] / 'embedded' / 'bridge' / 'qq_windows_appid.json'
)


class QQLauncher:
    """构建隔离的 QQ 进程命令，同时复用同一份 QQ 安装。"""

    def __init__(self, executable: Path, bridge_entry: Path):
        self.executable = Path(executable).resolve()
        self.bridge_entry = Path(bridge_entry).resolve()
        self.launch_env: dict[str, str] = {}

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError) as exc:
            raise RuntimeError(f'读取 QQ 版本信息失败: {path}: {exc}') from exc
        if not isinstance(value, dict):
            raise RuntimeError(f'QQ 版本信息不是 JSON 对象: {path}')
        return value

    @classmethod
    def windows_supported_versions(cls) -> frozenset[str]:
        table = cls._read_json(_WINDOWS_APPID_TABLE)
        return frozenset(str(version) for version in table)

    def windows_version(self) -> str:
        """按 QQ 目录规则读取 Windows QQNT 的真实版本。"""
        base = self.executable.parent
        config_candidates = (
            base / 'versions' / 'config.json',
            base / 'resources' / 'app' / 'versions' / 'config.json',
        )
        for config_path in config_candidates:
            if not config_path.is_file():
                continue
            config = self._read_json(config_path)
            version = str(config.get('curVersion') or '').strip()
            if not version:
                raise RuntimeError(f'QQ 版本配置缺少 curVersion: {config_path}')
            return version

        package_candidates = [base / 'resources' / 'app' / 'package.json']
        versions_dir = base / 'versions'
        if versions_dir.is_dir():
            version_dirs = [item for item in versions_dir.iterdir() if item.is_dir()]
            version_dirs.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
            package_candidates.extend(item / 'resources' / 'app' / 'package.json' for item in version_dirs)
        legacy_versions_dir = base / 'resources' / 'app' / 'versions'
        if legacy_versions_dir.is_dir():
            legacy_dirs = [item for item in legacy_versions_dir.iterdir() if item.is_dir()]
            legacy_dirs.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
            package_candidates.extend(item / 'package.json' for item in legacy_dirs)

        for package_path in package_candidates:
            if not package_path.is_file():
                continue
            package = self._read_json(package_path)
            version = str(package.get('version') or '').strip()
            if version:
                return version
        raise RuntimeError(f'无法从 QQ 安装目录读取 Windows QQ 版本: {self.executable}')

    def validate_windows_version(self) -> str:
        version = self.windows_version()
        if version not in self.windows_supported_versions():
            raise RuntimeError(f'当前 Windows QQ 版本 {version} 暂不兼容，无法启动 HookQQ')
        return version

    def app_dir(self) -> Path:
        base = self.executable.parent
        candidates: list[Path] = []
        if sys.platform == 'darwin':
            candidates.append(base.parent / 'Resources' / 'app')
        if sys.platform == 'win32':
            version = self.validate_windows_version()
            candidates.extend(
                (
                    base / 'versions' / version / 'resources' / 'app',
                    base / 'resources' / 'app' / 'versions' / version,
                )
            )

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
            "const skipOriginalMain = process.env.ELAINAQQ_SKIP_QQ_UI === '1';\n"
            'const originalDlopen = process.dlopen;\n'
            'let bridgeStarted = false;\n'
            'function startBridge(filename) {\n'
            '  if (bridgeStarted || !entry) return;\n'
            "  // 只有 QQ 主进程（无 --type= 参数）才启动 bridge\n"
            "  if (process.argv.some((arg) => {\n"
            "    const a = String(arg);\n"
            "    return a.startsWith('--type=') || a.startsWith('--pcqq-platform-channel-handle') || a.startsWith('--loadapp');\n"
            "  })) return;\n"
            '  bridgeStarted = true;\n'
            '  if (filename) process.env.ELAINAQQ_WRAPPER_PATH = filename;\n'
            '  process.dlopen = originalDlopen;\n'
            '  import(pathToFileURL(entry).href).catch((error) => {\n'
            "    console.error('[ElainaQQ] 运行时加载失败:', error);\n"
            '    // bridge 失败不能拖垮 QQ UI（Windows Hook 模式共用进程）\n'
            '  });\n'
            '}\n'
            'const electronMod = require("electron");\n'
            'const { app, session, ipcMain } = electronMod;\n'
            'const grabPreloadPath = process.env.ELAINAQQ_GRAB_PRELOAD || "";\n'
            'const grabNickName = process.env.ELAINAQQ_GRAB_NICKNAME || "";\n'
            'if (grabPreloadPath && !process.argv.some((a) => String(a).startsWith("--type="))) {\n'
            '  let grabConfigured = false;\n'
            '  const applyPreload = (s) => {\n'
            '    try {\n'
            '      const list = (s.getPreloads && s.getPreloads()) || [];\n'
            '      if (!list.includes(grabPreloadPath)) s.setPreloads(list.concat([grabPreloadPath]));\n'
            '    } catch (e2) {}\n'
            '  };\n'
            '  const configureGrab = () => {\n'
            '    if (grabConfigured) return;\n'
            '    grabConfigured = true;\n'
            '    try {\n'
            '      if (session.defaultSession) applyPreload(session.defaultSession);\n'
            '      app.on("session-created", (s) => applyPreload(s));\n'
            '      app.on("web-contents-created", (_ev, wc) => { try { if (wc.session) applyPreload(wc.session); } catch (e3) {} });\n'
            '      console.log("[ElainaQQ] grab preload installed:", grabPreloadPath);\n'
            '    } catch (error) { console.error("[ElainaQQ] setPreload failed:", error); }\n'
            '  };\n'
            '  if (app.isReady()) configureGrab(); else app.whenReady().then(configureGrab);\n'
            '  ipcMain.handle("elainaqq:whoami", (event) => ({ wcId: event.sender.id, nickName: grabNickName }));\n'
            '  ipcMain.on("elainaqq:grab-log", (_event, text) => console.log("[ElainaQQ][grab]", text));\n'
            '  const fs = require("fs");\n'
            '  const grabLogPath = process.env.ELAINAQQ_GRAB_LOG || "";\n'
            '  ipcMain.on("elainaqq:grab-file", (_event, text) => { try { if (grabLogPath) fs.appendFileSync(grabLogPath, String(text) + "\\n"); } catch (error) {} });\n'
            '  const watchPath = grabLogPath.replace(/grab_result\\.jsonl$/, "grab_task.json");\n'
            '  let lastTaskMtime = 0;\n'
            '  const broadcastTask = (raw) => { try { const task = JSON.parse(raw); const ec = require("electron").webContents.getAllWebContents(); ec.forEach((wc) => { try { wc.send("elainaqq:grab-go", task); } catch (e4) {} }); } catch (e5) {} };\n'
            '  let watching = false;\n'
            '  const startWatch = () => { if (watching || !grabLogPath) return; watching = true; try { fs.watchFile(watchPath, { interval: 400 }, (curr, prev) => { try { if (curr.mtimeMs !== lastTaskMtime) { lastTaskMtime = curr.mtimeMs; broadcastTask(fs.readFileSync(watchPath, "utf-8")); } } catch (e6) {} }); console.log("[ElainaQQ] grab task watcher on:", watchPath); } catch (e7) {} };\n'
            '  startWatch();\n'
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
            '  // 失败不设 exitCode，避免 QQ 整体退出\n'
            '}\n'
        )
        if not loader_path.is_file() or loader_path.read_text(encoding='utf-8') != loader_text:
            loader_path.write_text(loader_text, encoding='utf-8')
        grab_preload_src = Path(__file__).parents[1] / 'qq' / 'grab_preload.cjs'
        if grab_preload_src.is_file():
            grab_preload_dst = app_dir / 'elainaqq-grab-preload.cjs'
            if not grab_preload_dst.is_file() or grab_preload_dst.read_text(encoding='utf-8') != grab_preload_src.read_text(encoding='utf-8'):
                shutil.copyfile(grab_preload_src, grab_preload_dst)
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

    def _framework_root(self) -> Path:
        """框架仓库根目录（core/runtime/qq/launcher.py 向上三级）。"""
        return Path(__file__).resolve().parents[3]

    _SIGN_PATCH_OFFSET = 0x514317  # QQNT.dll 内 IsSignVerifySkipped 调用后的 test al,al 文件偏移
    _SIGN_PATCH_CONTEXT = b'\x84\xc0\x0f\x85'  # test al,al; jne rel32（打补丁前的特征）
    _SIGN_PATCH_NEW = b'\x0c\x01'  # or al,1（al=1 且 ZF=0 → jne 恒跳转，无条件跳过验签）

    def _windows_qqnt_dll(self) -> Path | None:
        """定位当前 QQ 布局下的 QQNT.dll（主流：versions/<ver>/QQNT.dll）。"""
        candidates: list[Path] = []
        try:
            app_dir = self.app_dir()
        except (RuntimeError, FileNotFoundError):
            # 版本不在兼容表时 app_dir 会拋错；直接扫 versions 目录兼容新版本。
            candidates.extend((self.executable.parent / 'versions').glob('*/QQNT.dll'))
        else:
            candidates.extend((
                app_dir.parent / 'QQNT.dll',
                app_dir.parent.parent / 'QQNT.dll',
                self.executable.parent / 'QQNT.dll',
            ))
        candidates.extend((self.executable.parent / 'versions').glob('*/QQNT.dll'))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def apply_windows_sign_patch(self) -> None:
        """跳过 QQNT.dll 的 resources 清单验签（仅限 hook-runtime 副本调用）。"""
        if sys.platform != 'win32':
            return
        dll_path = self._windows_qqnt_dll()
        if dll_path is None:
            return
        offset = self._SIGN_PATCH_OFFSET
        context = self._SIGN_PATCH_CONTEXT
        new = self._SIGN_PATCH_NEW
        try:
            raw = bytearray(dll_path.read_bytes())
        except OSError as exc:
            log.warning('QQNT.dll 验签补丁读取失败: %s (%s)', dll_path, exc)
            return
        current = bytes(raw[offset:offset + len(context)])
        if current == new + context[2:]:
            return  # 已补丁
        if current != context:
            log.warning(
                'QQNT.dll 验签补丁特征不匹配（QQ 可能已更新），跳过: %s offset=0x%X got=%s',
                dll_path, offset, current.hex(),
            )
            return
        backup = dll_path.with_name(dll_path.name + '.elainaqq-bak')
        if not backup.is_file():
            try:
                shutil.copyfile(dll_path, backup)
            except OSError as exc:
                log.warning('QQNT.dll 备份失败，跳过验签补丁: %s', exc)
                return
        raw[offset:offset + len(new)] = new
        temporary = dll_path.with_name(dll_path.name + '.elainaqq.tmp')
        try:
            temporary.write_bytes(bytes(raw))
            os.replace(temporary, dll_path)
        except OSError as exc:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            log.warning('QQNT.dll 验签补丁写入失败: %s (%s)', dll_path, exc)
            return
        log.info('QQNT.dll 验签补丁已应用: %s', dll_path)

    def hook_runtime(self) -> QQLauncher:
        """Windows Hook 启动模式：复制 QQ 到框架隔离运行时并打验签补丁。"""
        package_path = self.app_dir() / 'package.json'
        runtime_root = self._framework_root() / 'data' / 'qq' / 'runtime' / 'hook-runtime'
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
            runtime_root.mkdir(parents=True, exist_ok=True)
            log.info('Hook 启动模式：复制 QQ 到隔离运行时 %s（首次或 QQ 更新后约需 1-3 分钟）', target_dir)
            shutil.copytree(self.executable.parent, target_dir, dirs_exist_ok=True, symlinks=True)
            marker.write_text(json.dumps(source_state, ensure_ascii=False, indent=2), encoding='utf-8')
        launcher = QQLauncher(target_executable, self.bridge_entry)
        launcher.apply_windows_sign_patch()
        return launcher

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
                'ELAINAQQ_HEADLESS_RUNTIME': 'display',
            }
            command = [
                str(self.executable),
                '--no-sandbox',
            ]
        elif os.environ.get('WAYLAND_DISPLAY'):
            wayland_display = os.environ['WAYLAND_DISPLAY']
            if not os.path.isabs(wayland_display):
                runtime_dir = os.environ.get('XDG_RUNTIME_DIR', '')
                if runtime_dir:
                    wayland_display = posixpath.join(runtime_dir, wayland_display)
            self.launch_env = {
                'ELAINAQQ_HEADLESS_RUNTIME': 'wayland',
                'WAYLAND_DISPLAY': wayland_display,
            }
            command = [str(self.executable), '--no-sandbox', '--ozone-platform=wayland']
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
        launcher = QQLauncher(target_executable, self.bridge_entry)
        app_dir = launcher.app_dir()
        target_root = target_dir.resolve()
        for path in (app_dir, app_dir / 'package.json'):
            resolved = path.resolve()
            try:
                resolved.relative_to(target_root)
            except ValueError as exc:
                raise RuntimeError(f'QQ 运行时链接超出隔离副本: {path}') from exc
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        return launcher

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
            version = self.validate_windows_version()
            self.launch_env = {'QQ_VERSION': version}
            self.install_loader()
            grab_preload = self.app_dir() / 'elainaqq-grab-preload.cjs'
            if grab_preload.is_file() and os.environ.get('ELAINAQQ_GRAB_DISABLE') != '1':
                self.launch_env['ELAINAQQ_GRAB_PRELOAD'] = str(grab_preload)
                self.launch_env['ELAINAQQ_GRAB_NICKNAME'] = os.environ.get('ELAINAQQ_GRAB_NICKNAME', '')
                # QQ 可安装在任意盘符/深度（如 D:\QQNT\QQ.exe）；grab 日志与抢包任务
                grab_log = self._framework_root() / 'data' / 'log' / 'grab_result.jsonl'
                grab_log.parent.mkdir(parents=True, exist_ok=True)
                self.launch_env['ELAINAQQ_GRAB_LOG'] = str(grab_log)
            args = [str(self.executable), '--user-data-dir', str(data_dir / 'chromium')]
        if os.environ.get('ELAINAQQ_CDP_PORT'):
            args.append(f'--remote-debugging-port={os.environ["ELAINAQQ_CDP_PORT"]}')
            args.append('--remote-allow-origins=*')
        if headless:
            args.insert(1, '--headless')
        if quick_login:
            args.extend(('-q', quick_login))
        return args
        self.install_loader()
        args = [str(self.executable), '--user-data-dir', str(data_dir / 'chromium')]
        if os.environ.get('ELAINAQQ_CDP_PORT'):
            args.append(f'--remote-debugging-port={os.environ["ELAINAQQ_CDP_PORT"]}')
            args.append('--remote-allow-origins=*')
        if quick_login:
            args.extend(('-q', quick_login))
        return args
