"""应用程序顶层编排，组合所有子系统。"""

import asyncio
import contextlib
import copy
import gc
import os
import signal
from pathlib import Path

from core.foundation.branding import PRODUCT_NAME
from core.foundation.config import cfg
from core.foundation.logging import SYSTEM, get_logger
from core.foundation.logging import setup as setup_logger
from core.plugins._runtime import bind_application
from core.plugins.manager import PluginManager
from core.protocols.onebot.adapter import OneBotAdapter
from core.protocols.onebot.api import set_adapter, set_main_loop
from core.protocols.onebot.connection import ConnectionManager
from core.runtime.embedded.manager import EmbeddedQQManager
from core.runtime.event_dispatcher import EventDispatcher
from core.runtime.extensions.hook import HookManager, bind_hook_manager
from core.runtime.extensions.manager import ModuleManager
from core.services.config_watcher import ConfigWatcherService
from core.services.event_log import EventLogRecorder
from core.services.logs import LogService
from core.transport.http import HttpServer

log = get_logger(SYSTEM, '启动器')

_app = None


def get_app():
    return _app


def _tune_gc() -> None:
    """为长期运行且支持热重载的进程设置保守 GC 参数。"""
    gc.collect()
    with contextlib.suppress(AttributeError):
        gc.unfreeze()
    gc.set_threshold(700, 10, 10)


class Application:
    """ElainaQQ 应用入口。"""

    def __init__(self):
        self._base_dir = str(Path(__file__).resolve().parents[2])
        self._hook_manager = HookManager()
        bind_hook_manager(self._hook_manager)
        self._module_manager = None
        self._plugin_manager = None
        self._log_service = None
        self._http_server = None
        self._config_watcher = None
        self._adapter = None
        self._connection_manager = None
        self._stop_event = None
        self._loop = None
        self._restart_requested = False
        self._web_log_cb = None
        self._embedded_qq = None
        self._embedded_qq_start_task = None
        self._event_dispatcher = None
        self._event_log_recorder = None
        self._last_queue_warning = 0.0
        self._static_settings = {}

    @property
    def adapter(self):
        return self._adapter

    @property
    def connection_manager(self):
        return self._connection_manager

    @property
    def embedded_qq(self):
        return self._embedded_qq

    async def reload_connections(self):
        """重新应用 OneBot 连接配置 (网络配置页面保存后调用)"""
        if self._connection_manager:
            await self._connection_manager.reload()

    @property
    def hook_manager(self):
        return self._hook_manager

    @property
    def module_manager(self):
        return self._module_manager

    @property
    def plugin_manager(self):
        return self._plugin_manager

    @property
    def log_service(self):
        return self._log_service

    def _path(self, *parts):
        return os.path.join(self._base_dir, *parts)

    async def start(self):
        global _app
        _app = self
        bind_application(self)
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        if self._restart_requested:
            self._stop_event.set()

        # 1) 配置
        cfg.init(self._path('config'))
        self._static_settings = self._static_setting_values()
        fw_name = cfg.get('settings', 'web.framework_name', PRODUCT_NAME)
        setup_logger(framework_name=fw_name)
        log.info(f'{"=" * 5} {fw_name} 启动中 {"=" * 5}')
        # 2) OneBot 适配器 (每条连接自带 token/secret, 无需全局配置)
        self._adapter = OneBotAdapter(self.log_sent_message)
        set_adapter(self._adapter)
        set_main_loop(asyncio.get_running_loop())

        # 先创建内置 QQ 管理器，使插件加载钩子可以直接注册原生能力回调。
        # QQ 进程仍在 HTTP 和连接服务就绪后启动。
        self._embedded_qq = EmbeddedQQManager(self)

        # 3) HTTP 服务器
        self._http_server = HttpServer(self)
        self._http_server.init_app()

        # 4) 模块管理器
        self._module_manager = ModuleManager(self._path('modules'), self._hook_manager)
        await self._module_manager.discover()
        await self._module_manager.start_enabled()

        # 5) 插件管理器
        self._plugin_manager = PluginManager(self._path('plugins'))
        self._plugin_manager.set_bot_identity_matcher(self._adapter.allows_self_id)
        owner_ids = cfg.get('settings', 'owner.ids', []) or []
        owner_ids = [str(uid).strip() for uid in owner_ids if str(uid).strip()]
        self._plugin_manager.set_owner_ids(owner_ids)
        await self._plugin_manager.load_all()
        self._plugin_manager.start_watcher()

        # 6) 日志服务
        log_base = self._path('data', cfg.get('settings', 'logging.dir', 'log'))
        log_cfg = cfg.get('settings', 'logging') or {}
        self._log_service = LogService(
            base_dir=log_base,
            wal_mode=log_cfg.get('wal_mode', True) if isinstance(log_cfg, dict) else True,
            insert_interval=log_cfg.get('insert_interval', 2) if isinstance(log_cfg, dict) else 2,
            retention_days=log_cfg.get('retention_days', 30) if isinstance(log_cfg, dict) else 30,
            max_queue_entries=log_cfg.get('max_queue_entries', 100_000) if isinstance(log_cfg, dict) else 100_000,
            max_batch_size=log_cfg.get('max_batch_size', 500) if isinstance(log_cfg, dict) else 500,
        )
        await self._log_service.start()
        self._event_log_recorder = EventLogRecorder(
            self._log_service,
            lambda log_type, entry: self.push_web_log(log_type, entry),
        )
        self._event_dispatcher = EventDispatcher(self._process_event)

        # 7) Web 面板由应用编排层装配，HTTP 传输层只维护网络生命周期。
        self._mount_web_panel()

        # 8) 启动 HTTP 服务
        await self._http_server.start()

        # 8.5) OneBot 连接管理器 (正向 WS 客户端 / HTTP 客户端 / 反向鉴权)
        self._connection_manager = ConnectionManager(self)
        await self._connection_manager.start()

        # 8.6) 内置 QQ 运行时。关闭时由 shutdown 统一回收。
        if self._embedded_qq.enabled:
            log.info('内置 QQ 运行时已启用')
            self._embedded_qq_start_task = asyncio.create_task(self._embedded_qq.start_enabled(), name='embedded-qq-autostart')
            self._embedded_qq_start_task.add_done_callback(self._report_embedded_start_failure)

        # 9) 配置监视
        self._config_watcher = ConfigWatcherService(interval=5.0, on_reload=self.apply_config)
        self._config_watcher.start()

        _tune_gc()

        log.info(f'启动完成: {len(self._plugin_manager._plugins)} 个插件, {self._plugin_manager.handler_count} 个处理器')

        # 等待停止信号
        self._install_signal_handlers()
        try:
            await self._stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.shutdown()
        return self._restart_requested

    def request_restart(self) -> bool:
        """请求主循环完成清理后重新拉起进程。"""
        self._restart_requested = True
        if not self._stop_event:
            return False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop_event.set)
        else:
            self._stop_event.set()
        return True

    def _install_signal_handlers(self):
        loop = asyncio.get_running_loop()

        def _handle(signame):
            log.info(f'收到 {signame} 信号')
            if self._stop_event and not self._stop_event.is_set():
                self._stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _handle, sig.name)
            except (NotImplementedError, RuntimeError):
                with contextlib.suppress(ValueError, OSError):
                    signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(_handle, signal.Signals(s).name))

    def _mount_web_panel(self) -> None:
        if not self._http_server:
            raise RuntimeError('HTTP 服务尚未初始化')
        try:
            from web.setup import setup_web
            from web.ws import get_broadcast

            setup_web(self._http_server.app, self, self._base_dir)
            self._http_server.add_shutdown_callback(get_broadcast().shutdown)
        except Exception as error:
            log.error('Web 面板挂载失败: %s', error)

    async def shutdown(self):
        global _app
        log.info('正在关闭...')
        if self._plugin_manager:
            self._plugin_manager.stop_watcher()
        if self._config_watcher:
            self._config_watcher.stop()

        # 尽早释放主监听端口，避免重启后的新进程绑定失败。
        if self._http_server:
            await self._shutdown_step('HTTP 服务', self._http_server.stop(), timeout=5)
        if self._connection_manager:
            await self._shutdown_step('OneBot 连接', self._connection_manager.stop(), timeout=8)
        if self._adapter:
            await self._shutdown_step('OneBot 网络会话', self._adapter.close(), timeout=5)
        if self._embedded_qq_start_task and not self._embedded_qq_start_task.done():
            self._embedded_qq_start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._embedded_qq_start_task
        if self._embedded_qq:
            await self._shutdown_step('内置 QQ 进程', self._embedded_qq.stop_all(), timeout=20)
        if self._event_dispatcher:
            await self._shutdown_step('事件调度器', self._event_dispatcher.shutdown(), timeout=15)
        if self._config_watcher:
            await self._shutdown_step('配置监视', self._config_watcher.shutdown(), timeout=3)
        if self._plugin_manager:
            await self._shutdown_step('插件管理器', self._plugin_manager.shutdown(), timeout=10)
        if self._module_manager:
            await self._shutdown_step('模块管理器', self._module_manager.shutdown(), timeout=10)
        if self._log_service:
            await self._shutdown_step('日志服务', self._log_service.shutdown(), timeout=10)
        bind_application(None)
        bind_hook_manager(None)
        if _app is self:
            _app = None
        self._loop = None
        log.info('已关闭')

    @staticmethod
    async def _shutdown_step(name: str, operation, timeout: float) -> None:
        """限时关闭单个子系统，避免一个组件阻塞整体重启。"""
        try:
            async with asyncio.timeout(timeout):
                await operation
        except TimeoutError:
            log.warning('%s 关闭超时（%.0f 秒），继续回收其他资源', name, timeout)
        except Exception as error:
            log.warning('%s 关闭失败: %s', name, error)

    @staticmethod
    def _report_embedded_start_failure(task):
        if task.cancelled():
            return
        error = task.exception()
        if error:
            log.error('内置 QQ 自动启动任务失败: %s', error, exc_info=error)

    async def _process_event(self, event):
        """记录并分发已经完成规范化的 OneBot 事件。"""
        # 注入 API 引用, 使插件可通过 event.reply() 调用
        from core.protocols.onebot.api import get_api, routed_self_id

        event._api = get_api()

        # 同一事件链中的 API 调用始终回到产生事件的 QQ，避免多账号串号。
        with routed_self_id(str(event.self_id or '')):
            # 日志转换与插件分发并行启动；SQLite 仍由后台批量写入。
            log_task = None
            if self._event_log_recorder:
                log_task = asyncio.create_task(
                    self._event_log_recorder.log_event(event),
                    name='记录 OneBot 事件',
                )
            try:
                if self._hook_manager.has('on_raw_event'):
                    await self._hook_manager.emit('on_raw_event', event)
                await self._plugin_manager.dispatch(event)
            finally:
                if log_task is not None:
                    result = await asyncio.gather(log_task, return_exceptions=True)
                    if isinstance(result[0], Exception):
                        log.warning('事件日志记录失败: %s', result[0])

    async def ingest_event(self, payload: dict, default_self_id: str = '') -> bool:
        """所有内置及网络来源共用的唯一 OneBot 事件入口。"""
        if not self._adapter:
            return False
        event = self._adapter.parse_event(payload, default_self_id)
        if event is None:
            return False
        if not self._event_dispatcher:
            return False
        self_id = str(getattr(event, 'self_id', '') or '')
        conversation_id = str(
            getattr(event, 'group_id', '')
            or getattr(event, 'target_id', '')
            or getattr(event, 'user_id', '')
            or getattr(event, 'peer_id', '')
            or ''
        )
        ordering_key = f'{self_id}:{conversation_id}'
        accepted = await self._event_dispatcher.submit(ordering_key, event)
        if not accepted:
            now = asyncio.get_running_loop().time()
            if now - self._last_queue_warning >= 10:
                self._last_queue_warning = now
                log.warning('事件队列持续繁忙，拒绝新事件以保护框架内存')
        return accepted

    async def log_sent_message(
        self,
        self_id: str,
        action: str,
        params: dict,
        response: dict,
    ) -> bool:
        """兼容适配器回调，并转交事件日志服务。"""
        if not self._event_log_recorder:
            return False
        return await self._event_log_recorder.log_sent_message(self_id, action, params, response)

    def push_web_log(self, log_type: str, entry: dict):
        if self._web_log_cb:
            self._web_log_cb(log_type, entry)

    @staticmethod
    def _static_setting_values() -> dict[str, object]:
        def snapshot(key: str, default):
            return copy.deepcopy(cfg.get('settings', key, default))

        return {
            'server.host': snapshot('server.host', '0.0.0.0'),
            'server.port': snapshot('server.port', 5201),
            'web.framework_name': snapshot('web.framework_name', PRODUCT_NAME),
            'web.favicon_url': snapshot('web.favicon_url', ''),
            'logging.dir': snapshot('logging.dir', 'log'),
            'logging.wal_mode': snapshot('logging.wal_mode', True),
            'embedded_qq.enabled': snapshot('embedded_qq.enabled', True),
            'embedded_qq.bridge_port_start': snapshot('embedded_qq.bridge_port_start', 30010),
            'embedded_qq.command': snapshot('embedded_qq.command', ''),
            'embedded_qq.qq_path': snapshot('embedded_qq.qq_path', ''),
            'embedded_qq.packet_backend': snapshot('embedded_qq.packet_backend', 'auto'),
            'embedded_qq.packet_verbose': snapshot('embedded_qq.packet_verbose', False),
            'embedded_qq.packet_o3_hook': snapshot('embedded_qq.packet_o3_hook', False),
            'embedded_qq.packet_bypass': snapshot('embedded_qq.packet_bypass', {}),
            'embedded_qq.data_dir': snapshot('embedded_qq.data_dir', 'data/qq'),
            'embedded_qq.headless': snapshot('embedded_qq.headless', True),
            'embedded_qq.single_process': snapshot('embedded_qq.single_process', False),
            'embedded_qq.accounts': tuple(snapshot('embedded_qq.accounts', []) or ()),
        }

    async def apply_config(self, name: str) -> dict[str, list[str]]:
        """把已重新读取的配置应用到可热更新组件。"""
        if name == 'connections':
            await self.reload_connections()
            if self._config_watcher:
                self._config_watcher.mark_current(name)
            return {'restart_required': []}
        if name != 'settings':
            return {'restart_required': []}

        if self._plugin_manager:
            owner_ids = cfg.get('settings', 'owner.ids', []) or []
            self._plugin_manager.set_owner_ids([str(uid).strip() for uid in owner_ids if str(uid).strip()])
        if self._log_service:
            log_cfg = cfg.get('settings', 'logging') or {}
            if isinstance(log_cfg, dict):
                self._log_service.update_config(
                    insert_interval=log_cfg.get('insert_interval', 2),
                    retention_days=log_cfg.get('retention_days', 30),
                    max_queue_entries=log_cfg.get('max_queue_entries', 100_000),
                    max_batch_size=log_cfg.get('max_batch_size', 500),
                )
        current = self._static_setting_values()
        restart_required = [key for key, initial in self._static_settings.items() if current.get(key) != initial]
        if self._config_watcher:
            self._config_watcher.mark_current(name)
        return {'restart_required': restart_required}
