"""插件机器人绑定的加载、保存与应用。"""

import asyncio
import contextlib
import os

import yaml

from core.foundation.logging import PLUGIN, get_logger

log = get_logger(PLUGIN, '管理器')


class _PluginBotsMixin:
    @staticmethod
    def _normalize_plugin_bots(data):
        result = {}
        for key, values in data.items():
            name = str(key).strip()
            if not name or not isinstance(values, list):
                continue
            bots = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
            if bots:
                result[name] = bots
        return result

    def _load_plugin_bots(self):
        path = os.path.join(self._base_dir, 'data', 'plugin_bots.yaml')
        if not os.path.isfile(path):
            self._plugin_bots = {}
            return
        try:
            with open(path, encoding='utf-8') as file:
                data = yaml.safe_load(file) or {}
            if not isinstance(data, dict):
                raise ValueError('根节点必须是对象')
            self._plugin_bots = self._normalize_plugin_bots(data)
        except Exception as exc:
            log.warning(f'加载插件机器人绑定失败: {exc}')
            self._plugin_bots = {}

    async def _save_plugin_bots(self):
        await asyncio.to_thread(self._write_plugin_bots_sync, dict(self._plugin_bots))

    def _write_plugin_bots_sync(self, data):
        path = os.path.join(self._base_dir, 'data', 'plugin_bots.yaml')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = path + '.tmp'
        try:
            with open(temp, 'w', encoding='utf-8') as file:
                yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
            os.replace(temp, path)
        except Exception as exc:
            log.warning(f'保存插件机器人绑定失败: {exc}')
            with contextlib.suppress(OSError):
                os.remove(temp)

    def _apply_bot_bindings(self):
        for item in (
            *self._all_handlers,
            *self._all_interceptors,
            *self._all_handler_filters,
            *self._all_api_interceptors,
        ):
            item['_allowed_bots'] = _resolve_allowed_bots(
                self._plugin_bots,
                item.get('_plugin', ''),
                item.get('_file', ''),
            )

    def get_plugin_bots(self):
        return {key: list(values) for key, values in self._plugin_bots.items()}

    async def set_plugin_bots(self, data):
        self._plugin_bots = self._normalize_plugin_bots(data)
        self._apply_bot_bindings()
        await self._save_plugin_bots()


def _resolve_allowed_bots(mapping, plugin_name, file_name):
    if file_name:
        values = mapping.get(f'{plugin_name}/{file_name}')
        if values is not None:
            return frozenset(values) if values else None
    values = mapping.get(plugin_name)
    return frozenset(values) if values else None
