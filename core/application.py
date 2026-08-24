"""应用程序顶层编排，组合所有子系统。"""

import asyncio
import contextlib
import datetime
import gc
import json
import os
import signal
import zlib

from core.base.branding import PRODUCT_NAME
from core.base.config import cfg
from core.base.logger import SYSTEM, get_logger
from core.base.logger import setup as setup_logger
from core.embedded_qq import EmbeddedQQManager
from core.module.hook import HookManager
from core.module.manager import ModuleManager
from core.onebot.adapter import OneBotAdapter
from core.onebot.api import set_adapter, set_main_loop
from core.onebot.connection import ConnectionManager
from core.onebot.event import MessageEvent, MetaEvent, NoticeEvent, RequestEvent
from core.onebot.event_labels import event_label
from core.onebot.protocol import action_succeeded
from core.plugin.manager import PluginManager
from core.server.http_server import HttpServer
from core.services.config_watcher import ConfigWatcherService
from core.storage.log import LogService

log = get_logger(SYSTEM, '启动器')

_app = None

_MESSAGE_LABELS = {
    'image': '图片',
    'face': '表情',
    'record': '语音',
    'video': '视频',
    'reply': '回复',
    'json': 'JSON',
    'xml': 'XML',
    'node': '合并转发',
}
_SEND_ACTIONS = {'send_msg', 'send_group_msg', 'send_private_msg'}


def _format_message_content(message) -> str:
    """将 OneBot 字符串或消息段转换为适合日志展示的文本。"""
    if isinstance(message, str):
        return message.strip() or '[空消息]'
    segments: list | tuple
    if isinstance(message, dict):
        segments = (message,)
    elif isinstance(message, (list, tuple)):
        segments = message
    else:
        content = str(message or '').strip()
        return content or '[空消息]'

    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_type = str(segment.get('type') or '')
        data = segment.get('data')
        if not isinstance(data, dict):
            data = {}
        if segment_type == 'text':
            parts.append(str(data.get('text') or '').strip())
        elif segment_type == 'at':
            parts.append(f'@{data.get("qq", "")}')
        elif segment_type in _MESSAGE_LABELS:
            parts.append(f'[{_MESSAGE_LABELS[segment_type]}]')
        elif segment_type:
            parts.append(f'[{segment_type}]')
    return ''.join(parts) or '[空消息]'


def get_app():
    return _app


def _tune_gc() -> None:
    """冻结启动期稳定对象并降低全量回收频率。"""
    gc.collect()
    with contextlib.suppress(AttributeError):
        gc.freeze()
    gc.set_threshold(50_000, 25, 25)


class Application:
    """ElainaQQ 应用入口。"""

    def __init__(self):
        self._base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._hook_manager = HookManager()
        self._module_manager = None
        self._plugin_manager = None
        self._log_service = None
        self._http_server = None
        self._config_watcher = None
        self._adapter = None
        self._connection_manager = None
        self._stop_event = None
        self._restart_requested = False
        self._web_log_cb = None
        self._embedded_qq = None
        self._embedded_qq_start_task = None
        self._event_queues = []
        self._event_workers = []
        self._last_queue_warning = 0.0

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

        # 1) 配置
        cfg.init(self._path('config'))
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
        self._http_server = HttpServer(self, self._base_dir)
        self._http_server.init_app()

        # 4) 模块管理器
        self._module_manager = ModuleManager(self._path('modules'), self._hook_manager)
        self._module_manager.discover()
        await self._module_manager.start_enabled()

        # 5) 插件管理器
        self._plugin_manager = PluginManager(self._path('plugins'))
        self._plugin_manager.set_bot_identity_matcher(self._adapter.allows_self_id)
        owner_ids = cfg.get('settings', 'owner.ids', []) or []
        owner_ids = [str(uid).strip() for uid in owner_ids if str(uid).strip()]
        self._plugin_manager.set_owner_ids(owner_ids)
        await self._plugin_manager.load_all()
        self._plugin_manager.start_watcher()

        # 有界队列可避免慢插件在多账号突发消息时无限创建任务。
        self._event_queues = [asyncio.Queue(maxsize=250) for _ in range(4)]
        self._event_workers = [asyncio.create_task(self._event_worker(queue), name=f'event-worker-{index}') for index, queue in enumerate(self._event_queues)]

        # 6) 日志服务
        log_base = self._path('data', cfg.get('settings', 'logging.dir', 'log'))
        log_cfg = cfg.get('settings', 'logging') or {}
        self._log_service = LogService(
            base_dir=log_base,
            wal_mode=log_cfg.get('wal_mode', True) if isinstance(log_cfg, dict) else True,
            insert_interval=log_cfg.get('insert_interval', 2) if isinstance(log_cfg, dict) else 2,
            retention_days=log_cfg.get('retention_days', 30) if isinstance(log_cfg, dict) else 30,
        )
        await self._log_service.start()

        # 7) Web 面板
        self._http_server.mount_web_panel()

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
        self._config_watcher = ConfigWatcherService(interval=5.0)
        self._config_watcher.start()

        _tune_gc()

        log.info(f'启动完成: {len(self._plugin_manager._plugins)} 个插件, {self._plugin_manager.handler_count} 个处理器')

        # 等待停止信号
        self._stop_event = asyncio.Event()
        self._install_signal_handlers()
        try:
            await self._stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.shutdown()
        return self._restart_requested

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

    async def shutdown(self):
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
        for task in self._event_workers:
            task.cancel()
        if self._event_workers:
            await asyncio.gather(*self._event_workers, return_exceptions=True)
            self._event_workers.clear()
        if self._plugin_manager:
            await self._shutdown_step('插件管理器', self._plugin_manager.shutdown(), timeout=10)
        if self._module_manager:
            await self._shutdown_step('模块管理器', self._module_manager.shutdown(), timeout=10)
        if self._log_service:
            await self._shutdown_step('日志服务', self._log_service.shutdown(), timeout=10)
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

    async def _process_event(self, event, persisted):
        """持久化并分发已经完成规范化的 OneBot 事件。"""
        # 注入 API 引用, 使插件可通过 event.reply() 调用
        from core.onebot.api import get_api, routed_self_id

        event._api = get_api()

        # 同一事件链中的 API 调用始终回到产生事件的 QQ，避免多账号串号。
        with routed_self_id(str(event.self_id or '')):
            # 日志属于事件接入的基础链路，必须先于可扩展钩子持久化。
            # 这样模块或插件异常不会导致内置 QQ / OneBot 的日志一起丢失。
            await self._log_event(event)
            if persisted is not None and not persisted.done():
                persisted.set_result(True)
            await self._hook_manager.emit('on_raw_event', event)
            await self._plugin_manager.dispatch(event)

    async def ingest_event(self, payload: dict, default_self_id: str = '') -> bool:
        """所有内置及网络来源共用的唯一 OneBot 事件入口。"""
        if not self._adapter:
            return False
        event = self._adapter.parse_event(payload, default_self_id)
        if event is None:
            return False
        if isinstance(event, MetaEvent) and event.meta_event_type != 'lifecycle':
            return True
        if not self._event_queues:
            return False
        self_id = str(getattr(event, 'self_id', '') or '')
        queue_index = zlib.crc32(self_id.encode('utf-8')) % len(self._event_queues) if self_id else 0
        persisted = asyncio.get_running_loop().create_future()
        try:
            async with asyncio.timeout(2):
                await self._event_queues[queue_index].put((event, persisted))
        except TimeoutError:
            now = asyncio.get_running_loop().time()
            if now - self._last_queue_warning >= 10:
                self._last_queue_warning = now
                log.warning('事件队列持续繁忙，拒绝新事件以保护框架内存')
            return False
        try:
            await persisted
            return True
        except Exception:
            return False

    async def _event_worker(self, queue):
        while True:
            event, persisted = await queue.get()
            try:
                await self._process_event(event, persisted)
            except asyncio.CancelledError:
                if persisted is not None and not persisted.done():
                    persisted.cancel()
                raise
            except Exception as error:
                if persisted is not None and not persisted.done():
                    persisted.set_exception(error)
                log.error('事件处理失败: %s', error, exc_info=error)
            finally:
                queue.task_done()

    async def log_sent_message(
        self,
        self_id: str,
        action: str,
        params: dict,
        response: dict,
    ) -> bool:
        """记录成功发送的 OneBot 消息，并推送到 Web 面板。"""
        if action not in _SEND_ACTIONS or not action_succeeded(response):
            return False

        message_type = str(params.get('message_type') or '')
        if action == 'send_group_msg' or params.get('group_id') is not None:
            message_type = 'group'
        elif action == 'send_private_msg' or params.get('user_id') is not None:
            message_type = 'private'
        if message_type not in {'group', 'private'}:
            return False

        target_key = 'group_id' if message_type == 'group' else 'user_id'
        target_id = str(params.get(target_key) or '')
        if not target_id:
            return False

        bot_qq = str(self_id or '')
        content = _format_message_content(params.get('message'))
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result_data = response.get('data')
        if not isinstance(result_data, dict):
            result_data = {}
        message_id = str(result_data.get('message_id') or '')
        group_id = target_id if message_type == 'group' else ''
        user_id = '' if message_type == 'group' else target_id
        location = f'群({target_id})' if message_type == 'group' else f'私聊({target_id})'
        display = content[:100] + '...' if len(content) > 100 else content
        log.info(
            '[%s] 发送%s | %s | %s',
            bot_qq,
            '群聊' if message_type == 'group' else '私聊',
            location,
            display,
            extra={'web_skip': True},
        )

        if self._log_service:
            await self._log_service.add(
                'message',
                {
                    'timestamp': timestamp,
                    'content': content,
                    'source': bot_qq,
                    'user_id': user_id,
                    'group_id': group_id,
                    'message_id': message_id,
                    'message_type': message_type,
                    'raw_data': '',
                    'extra': 'send',
                },
                bot_qq=bot_qq,
                durable=True,
            )

        if self._web_log_cb:
            self._web_log_cb(
                'message',
                {
                    'timestamp': timestamp,
                    'content': content,
                    'user_id': user_id,
                    'group_id': group_id,
                    'message_id': message_id,
                    'message_type': message_type,
                    'sender': bot_qq,
                    'bot_qq': bot_qq,
                    'direction': 'send',
                    'raw_message': '',
                },
            )
        return True

    async def _log_event(self, event):
        """记录事件日志"""
        if isinstance(event, MessageEvent):
            msg_type = '群聊' if event.is_group else '私聊'
            sender = event.sender_card or event.sender_nickname or str(event.user_id)
            location = f'群({event.group_id})' if event.is_group else f'私聊({event.user_id})'

            content = _format_message_content(event.message)
            display = content[:100] + '...' if len(content) > 100 else content
            # 消息内容属于「消息记录」(按 QQ 分库), 不应混入「框架日志」: web_skip=True
            log.info(f'[{event.self_id}] {msg_type} | {location} | {sender}: {display}', extra={'web_skip': True})

            # 写入 SQLite
            if self._log_service:
                nickname = ''
                if isinstance(event.sender, dict):
                    nickname = event.sender.get('card') or event.sender.get('nickname') or ''
                await self._log_service.add(
                    'message',
                    {
                        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'content': content,
                        'source': str(event.self_id or ''),
                        'user_id': str(event.user_id),
                        'group_id': str(event.group_id or ''),
                        'message_id': str(event.message_id),
                        'message_type': event.message_type,
                        'raw_data': json.dumps(event.raw_data, ensure_ascii=False),
                        'extra': json.dumps({'nickname': nickname}, ensure_ascii=False),
                    },
                    bot_qq=str(event.self_id or ''),
                    durable=True,
                )

            # 推送到 Web 面板
            if self._web_log_cb:
                self._web_log_cb(
                    'message',
                    {
                        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'content': content,
                        'user_id': str(event.user_id),
                        'group_id': str(event.group_id or ''),
                        'message_id': str(event.message_id),
                        'message_type': event.message_type,
                        'sender': sender,
                        'bot_qq': str(event.self_id or ''),
                        'direction': 'receive',
                        'raw_message': json.dumps(event.raw_data, ensure_ascii=False),
                    },
                )

        elif isinstance(event, (NoticeEvent, RequestEvent, MetaEvent)):
            # 通知、请求和生命周期事件进入「事件」面板，并统一使用中文名称。
            if isinstance(event, NoticeEvent):
                event_type = event.notice_type
            elif isinstance(event, RequestEvent):
                event_type = f'request.{event.request_type}'
            else:
                event_type = f'meta_event.{event.meta_event_type}'
            sub_type = str(getattr(event, 'sub_type', '') or event.raw_data.get('sub_type') or '')
            user_id = str(getattr(event, 'user_id', '') or '')
            group_id = str(getattr(event, 'group_id', '') or '')
            type_label = event_label(event_type, sub_type)
            log.debug(f'事件: {type_label} | 群 {group_id} | 用户 {user_id}', extra={'web_skip': True})
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            bot_qq = str(event.self_id or '')
            raw_json = json.dumps(event.raw_data, ensure_ascii=False)
            content = f'{type_label} | 群{group_id} | 用户{user_id}'
            if self._log_service:
                await self._log_service.add(
                    'lifecycle',
                    {
                        'timestamp': now,
                        'content': content,
                        'source': bot_qq,
                        'user_id': user_id,
                        'group_id': group_id,
                        'message_type': event_type,
                        'raw_data': raw_json,
                    },
                    bot_qq=bot_qq,
                    durable=True,
                )
            if self._web_log_cb:
                self._web_log_cb(
                    'lifecycle',
                    {
                        'timestamp': now,
                        'type': event_type,
                        'event_type': event_type,
                        'type_label': type_label,
                        'user_id': user_id,
                        'group_id': group_id,
                        'bot_qq': bot_qq,
                        'content': content,
                        'raw_message': raw_json,
                    },
                )
            # 撤回事件：标记对应消息为已撤回
            if self._log_service and isinstance(event, NoticeEvent) and event.notice_type in ('group_recall', 'friend_recall'):
                recalled_mid = str(event.raw_data.get('message_id', '') or '')
                if recalled_mid:
                    await self._log_service.execute(
                        'message',
                        "UPDATE log SET extra = 'recalled' WHERE message_id = ?",
                        (recalled_mid,),
                        bot_qq=str(event.self_id or ''),
                    )

    def push_web_log(self, log_type: str, entry: dict):
        if self._web_log_cb:
            self._web_log_cb(log_type, entry)
