"""QQ 子进程输出的噪声过滤、等级分类与崩溃段识别。"""

import logging

_NOISE_MARKERS = (
    'DroppedFrame(',
    'Failed to connect to the bus:',
    'org.freedesktop.DBus.NameHasOwner',
    'org.freedesktop.systemd1.Manager.StartTransientUnit',
    'No suitable EGL configs found',
    'Failed to get config for surface',
    'CreateOffscreenGLSurface failed',
    'Could not create surface for info collection',
    'CollectGraphicsInfo failed',
    'Exiting GPU process due to errors during initialization',
    '[QQ hotUpdate]',
    'not mini app.',
    '[preload] succeeded.',
    '状态变更: logging_in {"qrcodeUrl":',
    '[LOGIN] onQRCodeGetPicture, qrcodeUrl:',
    '[LOGIN] 轮询已开始',
    '[LOGIN] onQRCodeSessionFailed: 1 3',
    'AddContentDecryptionModules called',
    'Widevine CDM path from switch:',
    'Widevine CDM path not set',
    'Widevine CDM not available',
    'argv[',
    'Boot Command:',
    'Creating pipe:',
    'resourcesPath:',
    'loadSymbolFromShell: dlsym failed PerfTrace',
    '[I] <MMKV',
    '[I] <MemoryFile',
    'linux-bugly: init bugly',
    'InitBuglyManager',
    'SetLogger',
    'fatalSetup',
    'GetDllPath:',
    'pub_key_path:',
    'BuglyManager/',
    '[BuglyService.cpp][registBugly]',
    '[BuglyService.cpp][registSignalHandler]',
    'registBugly/',
    '[BuglyService.cpp][setParam]',
    'setParam/',
    'StartWithOptions ',
    'PostDelayedTask ',
    '请扫描下面的二维码',
    '二维码解码URL:',
    '如果控制台二维码无法扫码',
    '二维码已保存到',
)
_WARNING_MARKERS = ('error', 'failed', 'exception', 'fatal', '启动失败', '登录失败', '加载失败', '初始化失败', '崩溃')
_CRASH_START_MARKERS = (
    '[BuglyManager.cpp][UploadBugly]',
    '[NativeCrashHandler.cpp]',
    '[BuglyService.cpp][buglySignalHandler]',
    'FATAL:electron/shell/browser/electron_browser_main_parts.cc',
)


def is_qq_noise(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) >= 12 and not stripped.translate(str.maketrans('', '', '▄▀█ ')):
        return True
    return any(pattern in line for pattern in _NOISE_MARKERS)


def qq_output_level(line: str) -> int:
    """正常登录链路仅在调试模式显示，错误输出提升为警告。"""
    lowered = line.casefold()
    return logging.WARNING if any(marker in lowered for marker in _WARNING_MARKERS) else logging.DEBUG


def crash_dump_start(line: str) -> bool:
    return any(pattern in line for pattern in _CRASH_START_MARKERS)


def crash_dump_end(line: str) -> bool:
    return (
        '[NativeCrashHandler.cpp][onUploadEnd]' in line
        or '[UploadTask.cpp][onUploadEnd]' in line
        or 'upload success' in line.lower()
    )

