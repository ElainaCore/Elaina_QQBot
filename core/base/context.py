"""基础上下文 — 模块/插件通用"""

import os

import yaml

from core.base.logger import get_logger


class BaseContext:
    """基础上下文，提供日志、配置、数据目录等通用能力"""

    __slots__ = ('name', '_root_dir', '_module_type', 'log')

    def __init__(self, name: str, root_dir: str, module_type: str):
        self.name = name
        self._root_dir = root_dir
        self._module_type = module_type
        self.log = get_logger(module_type, name)

    def get_data_path(self, filename: str = '') -> str:
        """获取数据目录路径（自动创建）"""
        data_dir = os.path.join(self._root_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, filename) if filename else data_dir

    def ensure_config(self, defaults: dict, comments: dict | None = None) -> dict:
        """确保配置文件存在，返回配置字典"""
        config_path = os.path.join(self._root_dir, 'config.yaml')
        if os.path.isfile(config_path):
            try:
                with open(config_path, encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                # 合并默认值
                merged = dict(defaults)
                merged.update(data)
                return merged
            except Exception as e:
                self.log.warning(f'读取配置失败: {e}')
        # 写入默认配置
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(defaults, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception:
            pass
        return dict(defaults)
