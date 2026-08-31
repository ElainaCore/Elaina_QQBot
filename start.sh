#!/usr/bin/env bash
set -Eeuo pipefail

BOOTSTRAP_VERSION='2'
PYTHON_VERSION='3.13'
DEFAULT_PYTHON_INSTALL_MIRROR='https://registry.npmmirror.com/-/binary/python-build-standalone'
PYTHON_INSTALL_MIRROR="${ELAINAQQ_PYTHON_MIRROR:-${ELAINABOT_PYTHON_MIRROR:-$DEFAULT_PYTHON_INSTALL_MIRROR}}"
PYTHON_INSTALL_MIRROR="${PYTHON_INSTALL_MIRROR%/}"
PIP_MIRROR='https://pypi.tuna.tsinghua.edu.cn/simple'
OFFICIAL_PIP_SOURCE='https://pypi.org/simple'
FRAMEWORK_DOWNLOAD_URL='https://github.com/ElainaCore/Elaina_QQBot/archive/main.zip'
FRAMEWORK_MIRRORS=(
    'https://github.chenc.dev'
    'https://ghproxy.cfd'
    'https://github.tbedu.top'
    'https://ghproxy.cc'
)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
TOOLS_DIR="$ROOT_DIR/.bootstrap/uv"
STAMP_FILE="$VENV_DIR/.elainabot-requirements.sha256"
SETUP_ONLY=0

for argument in "$@"; do
    case "$argument" in
        --setup-only) SETUP_ONLY=1 ;;
        -h|--help)
            echo '用法：./start.sh [--setup-only]'
            exit 0
            ;;
        *)
            echo "[ElainaBot] 错误：未知参数：$argument" >&2
            exit 2
            ;;
    esac
done

cd "$ROOT_DIR"

step() {
    printf '[ElainaBot] %s\n' "$*"
}

fail() {
    printf '[ElainaBot] 错误：%s\n' "$*" >&2
    exit 1
}

run_as_root() {
    if (( EUID == 0 )); then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        fail "安装系统软件包需要 root 权限或 sudo：$*"
    fi
}

install_download_prerequisites() {
    step '未找到 curl 或 wget，正在安装下载工具...'
    if command -v apt-get >/dev/null 2>&1; then
        run_as_root apt-get update
        run_as_root apt-get install -y curl ca-certificates
    elif command -v dnf >/dev/null 2>&1; then
        run_as_root dnf install -y curl ca-certificates
    elif command -v yum >/dev/null 2>&1; then
        run_as_root yum install -y curl ca-certificates
    elif command -v pacman >/dev/null 2>&1; then
        run_as_root pacman -Sy --needed --noconfirm curl ca-certificates
    elif command -v zypper >/dev/null 2>&1; then
        run_as_root zypper --non-interactive install curl ca-certificates
    elif command -v apk >/dev/null 2>&1; then
        run_as_root apk add curl ca-certificates
    else
        fail '未找到受支持的软件包管理器。请安装 curl 或 wget 后重新运行本脚本。'
    fi
}

python_is_compatible() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

python_is_preferred() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)' >/dev/null 2>&1
}

find_preferred_python() {
    local candidate
    for candidate in python3.13 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && python_is_preferred "$(command -v "$candidate")"; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

ensure_downloader() {
    if command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1; then
        return
    fi
    install_download_prerequisites
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return
    fi
    if [[ -x "$TOOLS_DIR/uv" ]]; then
        printf '%s\n' "$TOOLS_DIR/uv"
        return
    fi

    ensure_downloader
    step '正在安装项目专用的 Python 环境引导工具...' >&2
    mkdir -p "$TOOLS_DIR"
    local installer
    installer="$(mktemp "${TMPDIR:-/tmp}/elainabot-uv-install.XXXXXX")"
    trap 'rm -f "$installer"' RETURN
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh -o "$installer"
    else
        wget -qO "$installer" https://astral.sh/uv/install.sh
    fi
    UV_INSTALL_DIR="$TOOLS_DIR" UV_NO_MODIFY_PATH=1 sh "$installer" >&2
    rm -f "$installer"
    trap - RETURN
    [[ -x "$TOOLS_DIR/uv" ]] || fail '无法安装项目专用的 Python 环境引导工具。'
    printf '%s\n' "$TOOLS_DIR/uv"
}

backup_invalid_venv() {
    [[ -e "$VENV_DIR" ]] || return
    local backup="$ROOT_DIR/.venv.backup-$(date +%Y%m%d-%H%M%S)"
    step "现有虚拟环境无效，正在将其移动到 ${backup##*/}。"
    mv -- "$VENV_DIR" "$backup"
}

ensure_virtual_environment() {
    step '[1/5] 正在检查 Python 3.11 或更高版本...'
    if [[ -x "$VENV_PYTHON" ]] && python_is_compatible "$VENV_PYTHON"; then
        step "[1/5] Python 已就绪：$("$VENV_PYTHON" -c 'import platform; print(platform.python_version())')"
        step '[2/5] 已有虚拟环境可用：.venv'
        return
    fi

    backup_invalid_venv
    local python_bin=''
if python_bin="$(find_preferred_python)"; then
step "[1/5] 已找到 Python 3.13：$("$python_bin" -c 'import platform; print(platform.python_version())')"
        step '[2/5] 正在创建项目虚拟环境：.venv...'
        if "$python_bin" -m venv "$VENV_DIR" && [[ -x "$VENV_PYTHON" ]]; then
            step '[2/5] 虚拟环境创建成功。'
            return
        fi
        if [[ -e "$VENV_DIR" ]]; then
            mv -- "$VENV_DIR" "$ROOT_DIR/.venv.failed-$(date +%Y%m%d-%H%M%S)"
        fi
        step '系统 Python 无法创建虚拟环境，将改用项目专用的 Python。'
    fi

    local uv_bin
    uv_bin="$(ensure_uv)"
    step "[1/5] 正在通过镜像下载项目专用的 Python $PYTHON_VERSION..."
    if ! (
        unset UV_NO_PROGRESS
        "$uv_bin" python install --no-bin --no-registry --mirror "$PYTHON_INSTALL_MIRROR" "$PYTHON_VERSION"
    ); then
        step 'Python 镜像下载失败，正在切换到官方源...'
        ( unset UV_NO_PROGRESS; "$uv_bin" python install --no-bin --no-registry "$PYTHON_VERSION" ) || fail "Python $PYTHON_VERSION 下载失败，镜像源和官方源均不可用。"
    fi
    step '[2/5] 正在创建项目虚拟环境：.venv...'
    "$uv_bin" venv --python "$PYTHON_VERSION" --managed-python --no-python-downloads "$VENV_DIR"
    [[ -x "$VENV_PYTHON" ]] || fail '虚拟环境创建结束，但未找到可用的 Python。'
    step '[2/5] 虚拟环境创建成功。'
}

framework_is_complete() {
    local path
    for path in \
        main.py \
        requirements.txt \
        pyproject.toml \
        config/settings.example.yaml \
        config/connections.example.yaml \
        core/runtime/application.py \
        core/foundation/config.py \
        core/runtime/embedded/manager.py \
        core/runtime/embedded/bridge/qq_runtime.mjs \
        web/setup.py \
        web/dist/index.html; do
        [[ -f "$ROOT_DIR/$path" ]] || return 1
    done
    return 0
}

framework_download_urls() {
    local custom_mirror="${ELAINAQQ_FRAMEWORK_MIRROR:-${ELAINABOT_FRAMEWORK_MIRROR:-}}" mirror
    if [[ -n "$custom_mirror" ]]; then
        printf '%s\n' "${custom_mirror%/}/$FRAMEWORK_DOWNLOAD_URL"
    fi
    for mirror in "${FRAMEWORK_MIRRORS[@]}"; do
        printf '%s\n' "${mirror%/}/$FRAMEWORK_DOWNLOAD_URL"
    done
    printf '%s\n' "$FRAMEWORK_DOWNLOAD_URL"
}

restore_framework_from_archive() {
    local archive="$1" staging="$2"
    "$VENV_PYTHON" - "$archive" "$staging" "$ROOT_DIR" <<'PY'
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

archive, staging, root = map(Path, sys.argv[1:])
staging = staging.resolve()
root = root.resolve()
with zipfile.ZipFile(archive) as zf:
    for info in zf.infolist():
        name = info.filename.replace('\\', '/')
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('压缩包包含不安全路径: ' + name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise RuntimeError('压缩包包含不安全符号链接: ' + name)
        target = (staging / relative).resolve()
        if target != staging and staging not in target.parents:
            raise RuntimeError('压缩包包含不安全路径: ' + name)
        if info.is_dir() or name.endswith('/'):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as source, target.open('wb') as destination:
            shutil.copyfileobj(source, destination)

entries = list(staging.iterdir())
source = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
required = (
    'main.py',
    'requirements.txt',
    'pyproject.toml',
    'config/settings.example.yaml',
    'config/connections.example.yaml',
    'core/runtime/application.py',
    'core/foundation/config.py',
    'core/runtime/embedded/manager.py',
    'core/runtime/embedded/bridge/qq_runtime.mjs',
    'web/setup.py',
    'web/dist/index.html',
)
missing = [relative for relative in required if not (source / relative).is_file()]
if missing:
    raise RuntimeError('压缩包缺少框架基本文件: ' + ', '.join(missing))

for item in source.rglob('*'):
    relative = item.relative_to(source)
    destination = root / relative
    resolved_destination = destination.resolve()
    if resolved_destination != root and root not in resolved_destination.parents:
        raise RuntimeError('目标路径超出项目目录: ' + str(relative))
    if item.is_dir():
        if destination.exists() and not destination.is_dir():
            continue
        destination.mkdir(parents=True, exist_ok=True)
    elif item.is_file() and not os.path.lexists(destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
PY
}

ensure_framework() {
    local path url archive staging
    local -a required download
    required=()
    for path in \
        main.py \
        requirements.txt \
        pyproject.toml \
        config/settings.example.yaml \
        config/connections.example.yaml \
        core/runtime/application.py \
        core/foundation/config.py \
        core/runtime/embedded/manager.py \
        core/runtime/embedded/bridge/qq_runtime.mjs \
        web/setup.py \
        web/dist/index.html; do
        [[ -f "$ROOT_DIR/$path" ]] || required+=("$path")
    done
    if (( ${#required[@]} == 0 )); then
        step '[3/6] 框架基本文件完整，无需下载。'
        return
    fi

    step "[3/6] 缺少框架基本文件: ${required[*]}，正在通过镜像下载并解压..."
    ensure_downloader
    staging="$(mktemp -d "${TMPDIR:-/tmp}/elainaqq-framework.XXXXXX")"
    archive="$staging/framework.zip"
    mkdir -p "$staging/extracted"
    while IFS= read -r url; do
        step "正在尝试框架镜像: $url"
        rm -f -- "$archive"
        if command -v curl >/dev/null 2>&1; then
            download=(curl --fail --location --silent --show-error --retry 2 --connect-timeout 10 --max-time 180 "$url" --output "$archive")
        else
            download=(wget --quiet --timeout=20 --tries=2 --output-document="$archive" "$url")
        fi
        if "${download[@]}" && "$VENV_PYTHON" -c 'import zipfile,sys; raise SystemExit(0 if zipfile.is_zipfile(sys.argv[1]) else 1)' "$archive"; then
            rm -rf -- "$staging/extracted"
            mkdir -p "$staging/extracted"
            if restore_framework_from_archive "$archive" "$staging/extracted" && framework_is_complete; then
                step '框架基本文件已从镜像恢复。'
                rm -rf -- "$staging"
                return
            fi
            step '镜像压缩包解压后仍缺少框架文件，尝试下一个来源。'
        else
            step '镜像下载失败或返回的文件不是有效 ZIP，尝试下一个来源。'
        fi
    done < <(framework_download_urls)
    rm -rf -- "$staging"
    fail '框架基本文件缺失，镜像源和官方源均无法下载或解压。'
}

collect_requirement_files() {
    REQ_FILES=()
    local file directory
    while IFS= read -r -d '' file; do
        REQ_FILES+=("$file")
    done < <(find "$ROOT_DIR" -maxdepth 1 -type f \( -name 'requirements.txt' -o -name '*_requirements.txt' \) -print0 | sort -z)

    for directory in "$ROOT_DIR/modules" "$ROOT_DIR/plugins"; do
        [[ -d "$directory" ]] || continue
        while IFS= read -r -d '' file; do
            REQ_FILES+=("$file")
        done < <(find "$directory" -type f \( -name 'requirements.txt' -o -name '*_requirements.txt' \) -print0 | sort -z)
    done
}

requirements_fingerprint() {
    "$VENV_PYTHON" - "$BOOTSTRAP_VERSION" "${REQ_FILES[@]}" <<'PY'
import hashlib
import pathlib
import sys

version, *paths = sys.argv[1:]
digest = hashlib.sha256()
digest.update(f'bootstrap={version}\n'.encode())
for raw_path in paths:
    path = pathlib.Path(raw_path)
    digest.update(str(path).encode())
    digest.update(b'\0')
    digest.update(hashlib.sha256(path.read_bytes()).digest())
print(digest.hexdigest())
PY
}

core_dependencies_work() {
    "$VENV_PYTHON" -c 'import aiohttp, psutil, yaml' >/dev/null 2>&1
}

pip_install() {
    step '正在优先使用清华 PyPI 镜像安装依赖...'
    if "$VENV_PYTHON" -m pip install --disable-pip-version-check --index-url "$PIP_MIRROR" "$@"; then
        return
    fi

    step '镜像源安装失败，正在切换到官方 PyPI...'
    "$VENV_PYTHON" -m pip install --disable-pip-version-check --index-url "$OFFICIAL_PIP_SOURCE" "$@"
}

ensure_dependencies() {
    step '[3/5] 正在扫描框架、模块和插件的依赖文件...'
    collect_requirement_files
    (( ${#REQ_FILES[@]} > 0 )) || fail '未找到任何依赖文件。'
    step "[3/5] 已找到 ${#REQ_FILES[@]} 个依赖文件。"

    local fingerprint saved_fingerprint=''
    fingerprint="$(requirements_fingerprint)"
    if [[ -f "$STAMP_FILE" ]]; then
        saved_fingerprint="$(<"$STAMP_FILE")"
    fi
    if [[ "$saved_fingerprint" == "$fingerprint" ]] && core_dependencies_work; then
        step '[4/5] 依赖已经安装且为最新状态，无需重复安装。'
        return
    fi

    step "[4/5] 正在根据 ${#REQ_FILES[@]} 个依赖文件安装依赖..."
    "$VENV_PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
    pip_install --upgrade pip setuptools wheel

    local pip_arguments=()
    local requirement
    for requirement in "${REQ_FILES[@]}"; do
        pip_arguments+=(-r "$requirement")
    done
    pip_install "${pip_arguments[@]}"
    core_dependencies_work || fail '依赖安装已经结束，但仍有一个或多个核心包无法导入。'
    printf '%s\n' "$fingerprint" > "$STAMP_FILE"
    step '[4/5] 依赖安装完成并通过验证。'
}

step '正在准备运行环境...'
ensure_virtual_environment
ensure_framework
ensure_dependencies

if (( SETUP_ONLY == 1 )); then
    step '[5/5] 已选择仅配置环境模式，跳过框架启动。'
    step '运行环境配置成功。'
    exit 0
fi

step '[5/5] 正在启动 ElainaBot 框架...'
step 'Web 管理面板：http://localhost:5201/web/'
exec "$VENV_PYTHON" "$ROOT_DIR/main.py"

