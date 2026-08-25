"""YAML 配置管理器 — 支持热加载"""

import logging
import os
import threading
from typing import Any

import yaml

log = logging.getLogger('ElainaQQ.config')


class Config:
    """全局配置管理器"""

    def __init__(self):
        self._config_dir = ''
        self._data = {}  # 配置文件名映射到配置内容
        self._lock = threading.Lock()
        self._callbacks = {}  # 配置文件名映射到回调列表

    def init(self, config_dir: str):
        """初始化配置目录，加载所有 yaml 文件"""
        self._config_dir = config_dir
        os.makedirs(config_dir, exist_ok=True)
        self._ensure_defaults()
        self._load_all()

    def _ensure_defaults(self):
        """如果配置文件不存在，从 example 复制"""
        for name in ('settings', 'connections'):
            target = os.path.join(self._config_dir, f'{name}.yaml')
            if not os.path.isfile(target):
                example = os.path.join(self._config_dir, f'{name}.example.yaml')
                if os.path.isfile(example):
                    import shutil

                    shutil.copy2(example, target)
                else:
                    # 从项目根目录的 config/ 复制
                    root_example = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config', f'{name}.example.yaml')
                    if os.path.isfile(root_example):
                        import shutil

                        shutil.copy2(root_example, target)

    def _load_all(self):
        """加载配置目录下所有 yaml 文件"""
        if not os.path.isdir(self._config_dir):
            return []
        loaded = []
        for fname in os.listdir(self._config_dir):
            if fname.endswith('.yaml') and not fname.endswith('.example.yaml'):
                name = fname[:-5]
                if self._load_file(name):
                    loaded.append(name)
        return loaded

    def _load_file(self, name: str):
        """加载单个配置文件"""
        path = os.path.join(self._config_dir, f'{name}.yaml')
        if not os.path.isfile(path):
            return False
        try:
            with open(path, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise TypeError('YAML 根节点必须是对象')
            with self._lock:
                self._data[name] = data
            return True
        except Exception as e:
            log.error(f'加载配置失败 [{name}]: {e}')
            return False

    def reload(self, name: str | None = None):
        """重新加载配置"""
        if name:
            loaded = self._load_file(name)
            if loaded:
                self._fire_callbacks(name)
            return loaded
        loaded_names = self._load_all()
        for loaded_name in loaded_names:
            self._fire_callbacks(loaded_name)
        return bool(loaded_names)

    def get(self, file: str, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号路径 (如 'server.port')"""
        with self._lock:
            data = self._data.get(file, {})
        if not key:
            return data or default
        parts = key.split('.')
        for part in parts:
            if isinstance(data, dict):
                data = data.get(part)
            else:
                return default
            if data is None:
                return default
        return data

    def set_value(self, file: str, key: str, value: Any):
        """设置配置值并保存"""
        with self._lock:
            if file not in self._data:
                self._data[file] = {}
            data = self._data[file]

        parts = key.split('.')
        target = data
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

        self._save_file(file)
        self._fire_callbacks(file)

    def _save_file(self, name: str):
        """保存配置到文件"""
        path = os.path.join(self._config_dir, f'{name}.yaml')
        with self._lock:
            data = self._data.get(name, {})
        try:
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            log.error(f'保存配置失败 [{name}]: {e}')

    def on_change(self, file: str, callback):
        """注册配置变更回调"""
        if file not in self._callbacks:
            self._callbacks[file] = []
        self._callbacks[file].append(callback)

    def _fire_callbacks(self, file: str):
        """触发配置变更回调"""
        for cb in self._callbacks.get(file, []):
            try:
                cb()
            except Exception as e:
                log.warning(f'配置回调异常 [{file}]: {e}')

    def get_raw(self, file: str) -> dict:
        """获取文件完整配置"""
        with self._lock:
            return dict(self._data.get(file, {}))

    def set_raw(self, file: str, data: dict):
        """设置文件完整配置"""
        with self._lock:
            self._data[file] = data
        self._save_file(file)
        self._fire_callbacks(file)


# 全局单例
cfg = Config()
