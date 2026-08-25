"""OneBot v11 API 调用封装 (含常见扩展动作; 未封装的动作可直接用 call_api)"""

import asyncio
import contextvars
import json
import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from core.protocols.onebot.inline_keyboard import (
    GROUP_MESSAGE_COMMAND,
    build_group_message_request,
    extract_inline_keyboard_buttons,
)
from core.protocols.onebot.message import normalize_action_request
from core.protocols.onebot.protocol import action_failed, normalize_action_response

logger = logging.getLogger('ElainaQQ.onebot.api')

# 常用 OneBot v11 与 QQ 动作；call_api 不设白名单，新增动作无需升级框架即可调用。
SUPPORTED_ACTIONS = frozenset(
    {
        '.get_word_slices',
        '.handle_quick_operation',
        '.ocr_image',
        'ArkShareGroup',
        'ArkSharePeer',
        '_del_group_notice',
        '_get_group_notice',
        '_get_model_show',
        '_mark_all_as_read',
        '_send_group_notice',
        '_set_model_show',
        'add_custom_face',
        'bot_exit',
        'cancel_group_album_media_like',
        'cancel_group_todo',
        'cancel_online_file',
        'can_send_image',
        'can_send_record',
        'check_url_safely',
        'clean_cache',
        'clean_stream_temp_file',
        'complete_group_todo',
        'create_collection',
        'create_group_file_folder',
        'create_flash_task',
        'delete_custom_face',
        'delete_essence_msg',
        'delete_friend',
        'delete_group_file',
        'delete_group_folder',
        'delete_msg',
        'delete_qzone_msg',
        'del_group_album_media',
        'do_group_album_comment',
        'download_file',
        'download_file_image_stream',
        'download_file_record_stream',
        'download_file_stream',
        'download_fileset',
        'fetch_custom_face',
        'fetch_custom_face_detail',
        'fetch_emoji_like',
        'fetch_ptt_text',
        'forward_friend_single_msg',
        'forward_group_single_msg',
        'friend_poke',
        'get_ai_characters',
        'get_ai_record',
        'get_clientkey',
        'get_collection_list',
        'get_cookies',
        'get_credentials',
        'get_csrf_token',
        'get_doubt_friends_add_request',
        'get_emoji_likes',
        'get_essence_msg_list',
        'get_file',
        'get_fileset_id',
        'get_fileset_info',
        'get_flash_file_list',
        'get_flash_file_url',
        'get_forward_msg',
        'get_friend_list',
        'get_friend_msg_history',
        'get_friends_with_category',
        'get_group_album_media_list',
        'get_group_at_all_remain',
        'get_group_detail_info',
        'get_group_file_system_info',
        'get_group_file_url',
        'get_group_files_by_folder',
        'get_group_honor_info',
        'get_group_ignore_add_request',
        'get_group_ignored_notifies',
        'get_group_info',
        'get_group_info_ex',
        'get_group_list',
        'get_group_member_info',
        'get_group_member_list',
        'get_group_msg_history',
        'get_group_notice',
        'get_group_root_files',
        'get_group_shut_list',
        'get_group_signed_list',
        'get_group_system_msg',
        'group_poke',
        'get_guild_list',
        'get_guild_service_profile',
        'get_image',
        'get_login_info',
        'get_mini_app_ark',
        'get_model_show',
        'get_msg',
        'get_online_clients',
        'get_online_file_msg',
        'ocr_image',
        'get_packet_status',
        'get_private_file_url',
        'get_profile_like',
        'get_qun_album_list',
        'get_recent_contact',
        'get_record',
        'get_rkey',
        'get_rkey_server',
        'get_robot_uin_range',
        'get_share_link',
        'get_status',
        'get_stranger_info',
        'get_unidirectional_friend_list',
        'get_user_status',
        'get_version_info',
        'mark_all_as_read',
        'mark_group_msg_as_read',
        'mark_msg_as_read',
        'mark_private_msg_as_read',
        'move_group_file',
        'nc_get_packet_status',
        'nc_get_rkey',
        'nc_get_user_status',
        'receive_online_file',
        'refuse_online_file',
        'rename_group_file',
        'send_ark_share',
        'send_flash_msg',
        'click_inline_keyboard_button',
        'send_forward_msg',
        'send_group_ai_record',
        'send_group_ark_share',
        'send_group_forward_msg',
        'send_group_msg',
        'send_group_notice',
        'send_group_sign',
        'send_like',
        'send_msg',
        'send_online_file',
        'send_online_folder',
        'send_packet',
        'send_poke',
        'send_private_forward_msg',
        'send_private_msg',
        'send_qzone_msg',
        'set_custom_face_desc',
        'set_diy_online_status',
        'set_doubt_friends_add_request',
        'set_essence_msg',
        'set_friend_add_request',
        'set_friend_remark',
        'set_group_add_option',
        'set_group_add_request',
        'set_group_admin',
        'set_group_album_media_like',
        'set_group_ban',
        'set_group_card',
        'set_group_kick',
        'set_group_kick_members',
        'set_group_leave',
        'set_group_member_invite_policy',
        'set_group_member_permissions',
        'set_group_name',
        'set_group_new_member_history_visibility',
        'set_group_portrait',
        'set_group_remark',
        'set_group_robot_add_option',
        'set_group_search',
        'set_group_sign',
        'set_group_special_title',
        'set_group_todo',
        'set_group_whole_ban',
        'set_input_status',
        'set_model_show',
        'set_msg_emoji_like',
        'set_online_status',
        'set_qq_avatar',
        'set_qq_profile',
        'set_restart',
        'set_self_longnick',
        'trans_group_file',
        'translate_en2zh',
        'upload_file_stream',
        'upload_group_file',
        'upload_image_to_qun_album',
        'upload_private_file',
    }
)


def get_supported_actions() -> list[str]:
    """返回已登记的标准动作与扩展动作清单。"""
    return sorted(SUPPORTED_ACTIONS)


_main_loop = None
_adapter_ref = None
_routed_self_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'onebot_self_id',
    default=None,
)
_api_source: contextvars.ContextVar[tuple[str, dict[str, Any]]] = contextvars.ContextVar(
    'onebot_api_source',
    default=('', {}),
)
_skip_api_interceptors: contextvars.ContextVar[bool] = contextvars.ContextVar(
    'skip_onebot_api_interceptors',
    default=False,
)
_api_interceptors: tuple[dict, ...] = ()


@dataclass(slots=True)
class ApiCallRequest:
    """传给插件出站 API 中间件的可变调用对象。"""

    action: str
    params: dict
    self_id: str | None
    source_plugin: str = ''
    context: dict[str, Any] = field(default_factory=dict)
    local: bool = False


def set_api_interceptors(interceptors) -> None:
    """由插件管理器发布当前已启用的出站 API 中间件快照。"""
    global _api_interceptors
    _api_interceptors = tuple(interceptors or ())


@contextmanager
def api_call_source(plugin_name: str, event=None):
    """记录当前处理器发起 API 调用时的插件和事件上下文。"""
    context = {}
    if event is not None:
        for key in ('self_id', 'user_id', 'group_id', 'message_type', 'post_type'):
            value = getattr(event, key, None)
            if value is not None:
                context[key] = value
    token = _api_source.set((str(plugin_name or ''), context))
    try:
        yield
    finally:
        _api_source.reset(token)


@contextmanager
def bypass_api_interceptors():
    """让插件执行不再进入出站中间件的原始 OneBot 调用。"""
    token = _skip_api_interceptors.set(True)
    try:
        yield
    finally:
        _skip_api_interceptors.reset(token)


@contextmanager
def routed_self_id(self_id: str | None):
    """为当前事件及其异步处理链固定 API 目标账号。"""
    if self_id is None:
        yield
        return
    token = _routed_self_id.set(str(self_id))
    try:
        yield
    finally:
        _routed_self_id.reset(token)


def set_main_loop(loop):
    global _main_loop
    _main_loop = loop


def set_adapter(adapter):
    global _adapter_ref
    _adapter_ref = adapter


class OneBotAPI:
    """OneBot v11 API (内置常见扩展动作封装)"""

    def __init__(self, adapter=None):
        self._adapter = adapter or _adapter_ref
        self._routed_methods = {}

    @staticmethod
    def supported_actions() -> list[str]:
        return get_supported_actions()

    def __getattribute__(self, name):
        """让显式 API 封装统一接受 self_id/_self_id。

        路由账号存入 ContextVar，避免不同 QQ 的并发事件互相覆盖目标账号。
        """
        attr = object.__getattribute__(self, name)
        if name == 'call_api' or name.startswith('_') or not asyncio.iscoroutinefunction(attr):
            return attr
        cache = object.__getattribute__(self, '_routed_methods')
        if name in cache:
            return cache[name]

        async def routed(*args, **kwargs):
            self_id = kwargs.pop('self_id', kwargs.pop('_self_id', None))
            if self_id is None:
                return await attr(*args, **kwargs)
            token = _routed_self_id.set(str(self_id))
            try:
                return await attr(*args, **kwargs)
            finally:
                _routed_self_id.reset(token)

        cache[name] = routed
        return routed

    async def call_api(
        self,
        action: str,
        params: dict | None = None,
        self_id: str | None = None,
    ) -> dict | None:
        """通过指定账号的 OneBot WebSocket/HTTP 连接调用任意 action。"""
        params = dict(params or {})
        route_id = params.pop('_self_id', None)
        if route_id is None:
            route_id = params.pop('self_id', None)
        if self_id is None:
            self_id = route_id if route_id is not None else _routed_self_id.get()
        if not self._adapter:
            return action_failed('OneBot 适配器未初始化', 1500)
        self_id = self._adapter.default_self_id() if self_id is None else self._adapter.resolve_self_id(self_id)

        action, params = normalize_action_request(action, params)
        source_plugin, source_context = _api_source.get()
        local_actions = getattr(self._adapter, 'local_actions', {})
        request = ApiCallRequest(
            action=action,
            params=params,
            self_id=str(self_id) if self_id is not None else None,
            source_plugin=source_plugin,
            context=dict(source_context),
            local=(str(self_id) in local_actions if self_id is not None else bool(local_actions)),
        )
        if _api_interceptors and not _skip_api_interceptors.get():
            result = await self._run_api_interceptors(request, 0)
        else:
            result = await self._call_transport(request)
        return normalize_action_response(result, action=action)

    async def _run_api_interceptors(self, request: ApiCallRequest, index: int):
        if index >= len(_api_interceptors):
            return await self._call_transport(request)

        interceptor = _api_interceptors[index]
        allowed = interceptor.get('_allowed_bots')
        if not self._adapter.allows_self_id(allowed, str(request.self_id or '')):
            return await self._run_api_interceptors(request, index + 1)

        advanced = False

        async def call_next():
            nonlocal advanced
            if advanced:
                raise RuntimeError('同一个 API 中间件不能重复调用 call_next()')
            advanced = True
            return await self._run_api_interceptors(request, index + 1)

        try:
            from core.plugins.context import plugin_scope

            with plugin_scope(interceptor['_context']):
                return await interceptor['func'](request, call_next)
        except Exception:
            logger.exception(
                '插件出站 API 中间件异常: %s (%s)',
                interceptor.get('_plugin', '?'),
                request.action,
            )
            if advanced:
                return None
            return await call_next()

    async def _call_transport(self, request: ApiCallRequest) -> dict:
        """选择唯一可用传输，并统一响应与调用后处理。"""
        action = request.action
        params = request.params
        self_id = request.self_id
        response = None
        try:
            request.local = bool(
                self._adapter.local_actions
                and (self_id is None or str(self_id) in self._adapter.local_actions)
            )
            response = await self._adapter.call_local_action(action, params, self_id)
            if response is None:
                ws = self._adapter.get_bot_ws(self_id)
                if ws is not None:
                    echo = str(uuid.uuid4())
                    future = asyncio.get_running_loop().create_future()
                    self._adapter.register_api_response(echo, future, ws)
                    try:
                        send = getattr(ws, 'send_str', None) or ws.send_text
                        await send(json.dumps({'action': action, 'params': params, 'echo': echo}, ensure_ascii=False))
                        async with asyncio.timeout(30):
                            response = await future
                    finally:
                        self._adapter.discard_api_response(echo)
                elif getattr(self._adapter, 'http_clients', None):
                    response = await self._adapter.http_call_action(action, params, self_id)
                else:
                    logger.debug('API 未调用: 机器人未连接 (%s, self_id=%s)', action, self_id or '-')
        except TimeoutError:
            logger.warning('API 超时: %s', action)
            response = action_failed('OneBot 接口响应超时', 1500)
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            logger.debug('API 连接已断开: %s', action)
            response = action_failed('OneBot 连接已断开', 1500)
        except Exception as e:
            logger.error('API 错误: %s - %s', action, e)
            response = action_failed(str(e), 1500)

        normalized = normalize_action_response(response, action=action)
        handler = getattr(self._adapter, 'action_result_handler', None)
        if handler is not None:
            try:
                await handler(str(self_id or ''), action, params, normalized)
            except Exception:
                logger.exception('OneBot 动作后处理失败: %s', action)
        return normalized

    def __getattr__(self, name):
        """将任意 OneBot action 暴露为异步方法，兼容未预先封装的扩展接口。"""
        if name.startswith('_'):
            raise AttributeError(name)

        async def action_method(**params):
            self_id = params.pop('self_id', params.pop('_self_id', None))
            return await self.call_api(name, params, self_id=str(self_id) if self_id is not None else None)

        return action_method

    async def send_group_msg(self, group_id, message, **kwargs) -> dict | None:
        self_id = kwargs.pop('self_id', kwargs.pop('_self_id', None))
        return await self.call_api(
            'send_group_msg', {'group_id': int(group_id), 'message': message, **kwargs}, self_id=str(self_id) if self_id is not None else None
        )

    async def send_private_msg(self, user_id, message, **kwargs) -> dict | None:
        self_id = kwargs.pop('self_id', kwargs.pop('_self_id', None))
        return await self.call_api(
            'send_private_msg', {'user_id': int(user_id), 'message': message, **kwargs}, self_id=str(self_id) if self_id is not None else None
        )

    async def send_msg(self, message_type: str, target_id, message, **kwargs) -> dict | None:
        self_id = kwargs.pop('self_id', kwargs.pop('_self_id', None))
        params = {'message_type': message_type, 'message': message, **kwargs}
        if message_type == 'group':
            params['group_id'] = int(target_id)
        else:
            params['user_id'] = int(target_id)
        return await self.call_api(
            'send_msg', params, self_id=str(self_id) if self_id is not None else None
        )

    async def delete_msg(self, message_id) -> dict | None:
        return await self.call_api('delete_msg', {'message_id': int(message_id)})

    async def get_msg(self, message_id) -> dict | None:
        return await self.call_api('get_msg', {'message_id': int(message_id)})

    async def get_inline_keyboard_buttons(
        self,
        group_id,
        message_id,
        real_seq=None,
        bot_appid='',
    ) -> list[dict[str, str]]:
        """通过原始 protobuf 读取群消息中的官方机器人键盘。"""
        sequence = real_seq
        detail = await self.call_api('get_msg', {'message_id': message_id})
        data = detail.get('data') if isinstance(detail, dict) else None
        if not isinstance(data, dict):
            data = detail if isinstance(detail, dict) else {}
        embedded = data.get('_inline_keyboard')
        if isinstance(embedded, list) and embedded:
            return [item for item in embedded if isinstance(item, dict)]
        if not sequence:
            sequence = data.get('real_seq') or data.get('message_seq')
        if not sequence:
            return []
        try:
            packet = build_group_message_request(group_id, sequence)
        except (TypeError, ValueError):
            return []
        response = await self.call_api('send_packet', {
            'cmd': GROUP_MESSAGE_COMMAND,
            'data': packet,
        })
        if not isinstance(response, dict):
            raise RuntimeError('send_packet 未返回 OneBot 响应')
        if response.get('status') == 'failed':
            raise RuntimeError(
                str(response.get('message') or response.get('wording') or 'send_packet 读取消息 PB 失败')
            )
        return extract_inline_keyboard_buttons(response, bot_appid=str(bot_appid or ''))

    async def get_login_info(self) -> dict | None:
        return await self.call_api('get_login_info')

    async def get_stranger_info(self, user_id, **kwargs) -> dict | None:
        self_id = kwargs.pop('self_id', kwargs.pop('_self_id', None))
        return await self.call_api(
            'get_stranger_info',
            {'user_id': int(user_id), **kwargs},
            self_id=str(self_id) if self_id is not None else None,
        )

    async def get_friend_list(self, no_cache=False, **kwargs) -> dict | None:
        return await self.call_api('get_friend_list', {'no_cache': no_cache, **kwargs})

    async def get_group_list(self, no_cache=False, **kwargs) -> dict | None:
        return await self.call_api('get_group_list', {'no_cache': no_cache, **kwargs})

    async def get_group_info(self, group_id, **kwargs) -> dict | None:
        return await self.call_api('get_group_info', {'group_id': int(group_id), **kwargs})

    async def get_group_member_list(self, group_id, no_cache=False, **kwargs) -> dict | None:
        return await self.call_api('get_group_member_list', {'group_id': int(group_id), 'no_cache': no_cache, **kwargs})

    async def get_group_member_info(self, group_id, user_id, no_cache=True, **kwargs) -> dict | None:
        return await self.call_api(
            'get_group_member_info',
            {'group_id': int(group_id), 'user_id': int(user_id), 'no_cache': no_cache, **kwargs},
        )

    async def set_group_kick(self, group_id, user_id, reject_add=False) -> dict | None:
        return await self.call_api('set_group_kick', {'group_id': int(group_id), 'user_id': int(user_id), 'reject_add_request': reject_add})

    async def set_group_ban(self, group_id, user_id, duration=1800) -> dict | None:
        return await self.call_api('set_group_ban', {'group_id': int(group_id), 'user_id': int(user_id), 'duration': duration})

    async def set_group_whole_ban(self, group_id, enable=True) -> dict | None:
        return await self.call_api('set_group_whole_ban', {'group_id': int(group_id), 'enable': enable})

    async def set_friend_add_request(self, flag, approve=True) -> dict | None:
        return await self.call_api('set_friend_add_request', {'flag': flag, 'approve': approve})

    async def set_group_add_request(self, flag, sub_type, approve=True) -> dict | None:
        return await self.call_api('set_group_add_request', {'flag': flag, 'sub_type': sub_type, 'approve': approve})

    # ── 消息扩展 ──
    async def send_forward_msg(self, messages, **kwargs) -> dict | None:
        return await self.call_api('send_forward_msg', {'messages': messages, **kwargs})

    async def send_group_forward_msg(self, group_id, messages, **kwargs) -> dict | None:
        return await self.call_api('send_group_forward_msg', {'group_id': int(group_id), 'messages': messages, **kwargs})

    async def send_private_forward_msg(self, user_id, messages, **kwargs) -> dict | None:
        return await self.call_api('send_private_forward_msg', {'user_id': int(user_id), 'messages': messages, **kwargs})

    async def get_forward_msg(self, message_id) -> dict | None:
        return await self.call_api('get_forward_msg', {'message_id': message_id})

    async def get_group_msg_history(self, group_id, message_seq=0, count=20, reverse_order=False, **kwargs) -> dict | None:
        return await self.call_api(
            'get_group_msg_history',
            {'group_id': int(group_id), 'message_seq': message_seq, 'count': count, 'reverseOrder': reverse_order, **kwargs},
        )

    async def get_friend_msg_history(self, user_id, message_seq=0, count=20, reverse_order=False, **kwargs) -> dict | None:
        return await self.call_api(
            'get_friend_msg_history',
            {'user_id': int(user_id), 'message_seq': message_seq, 'count': count, 'reverseOrder': reverse_order, **kwargs},
        )

    async def mark_group_msg_as_read(self, group_id) -> dict | None:
        return await self.call_api('mark_group_msg_as_read', {'group_id': int(group_id)})

    async def mark_private_msg_as_read(self, user_id) -> dict | None:
        return await self.call_api('mark_private_msg_as_read', {'user_id': int(user_id)})

    async def set_msg_emoji_like(self, message_id, emoji_id, enable=True) -> dict | None:
        return await self.call_api('set_msg_emoji_like', {'message_id': message_id, 'emoji_id': str(emoji_id), 'set': enable})

    async def send_poke(self, user_id, group_id=None) -> dict | None:
        params = {'user_id': int(user_id)}
        if group_id is not None:
            params['group_id'] = int(group_id)
        return await self.call_api('send_poke', params)

    # ── 群组扩展 ──
    async def set_group_card(self, group_id, user_id, card='') -> dict | None:
        return await self.call_api('set_group_card', {'group_id': int(group_id), 'user_id': int(user_id), 'card': card})

    async def set_group_name(self, group_id, group_name) -> dict | None:
        return await self.call_api('set_group_name', {'group_id': int(group_id), 'group_name': group_name})

    async def set_group_admin(self, group_id, user_id, enable=True) -> dict | None:
        return await self.call_api('set_group_admin', {'group_id': int(group_id), 'user_id': int(user_id), 'enable': enable})

    async def set_group_special_title(self, group_id, user_id, special_title='') -> dict | None:
        return await self.call_api('set_group_special_title', {'group_id': int(group_id), 'user_id': int(user_id), 'special_title': special_title})

    async def set_group_leave(self, group_id, is_dismiss=False) -> dict | None:
        return await self.call_api('set_group_leave', {'group_id': int(group_id), 'is_dismiss': is_dismiss})

    async def set_group_portrait(self, group_id, file) -> dict | None:
        return await self.call_api('set_group_portrait', {'group_id': int(group_id), 'file': file})

    async def set_group_sign(self, group_id) -> dict | None:
        return await self.call_api('set_group_sign', {'group_id': int(group_id)})

    async def get_group_honor_info(self, group_id, honor_type='all') -> dict | None:
        return await self.call_api('get_group_honor_info', {'group_id': int(group_id), 'type': honor_type})

    async def get_group_at_all_remain(self, group_id) -> dict | None:
        return await self.call_api('get_group_at_all_remain', {'group_id': int(group_id)})

    async def get_group_system_msg(self) -> dict | None:
        return await self.call_api('get_group_system_msg')

    async def get_essence_msg_list(self, group_id) -> dict | None:
        return await self.call_api('get_essence_msg_list', {'group_id': int(group_id)})

    async def set_essence_msg(self, message_id) -> dict | None:
        return await self.call_api('set_essence_msg', {'message_id': int(message_id)})

    async def delete_essence_msg(self, message_id) -> dict | None:
        return await self.call_api('delete_essence_msg', {'message_id': int(message_id)})

    # ── 用户扩展 ──
    async def send_like(self, user_id, times=1) -> dict | None:
        return await self.call_api('send_like', {'user_id': int(user_id), 'times': int(times)})

    async def delete_friend(self, user_id) -> dict | None:
        return await self.call_api('delete_friend', {'user_id': int(user_id)})

    async def set_qq_avatar(self, file) -> dict | None:
        return await self.call_api('set_qq_avatar', {'file': file})

    async def set_qq_profile(self, **kwargs) -> dict | None:
        return await self.call_api('set_qq_profile', kwargs)

    async def get_unidirectional_friend_list(self) -> dict | None:
        return await self.call_api('get_unidirectional_friend_list')

    async def ocr_image(self, image) -> dict | None:
        return await self.call_api('ocr_image', {'image': image})

    # ── 系统扩展 ──
    async def get_version_info(self) -> dict | None:
        return await self.call_api('get_version_info')

    async def get_status(self) -> dict | None:
        return await self.call_api('get_status')

    async def can_send_image(self) -> dict | None:
        return await self.call_api('can_send_image')

    async def can_send_record(self) -> dict | None:
        return await self.call_api('can_send_record')

    async def get_cookies(self, domain='qun.qq.com') -> dict | None:
        return await self.call_api('get_cookies', {'domain': domain})

    async def get_csrf_token(self) -> dict | None:
        return await self.call_api('get_csrf_token')

    async def get_credentials(self, domain='qun.qq.com') -> dict | None:
        return await self.call_api('get_credentials', {'domain': domain})

    async def clean_cache(self) -> dict | None:
        return await self.call_api('clean_cache')

    # ── 文件扩展 ──
    async def upload_group_file(self, group_id, file, name, folder='') -> dict | None:
        return await self.call_api('upload_group_file', {'group_id': int(group_id), 'file': file, 'name': name, 'folder': folder})

    async def upload_private_file(self, user_id, file, name) -> dict | None:
        return await self.call_api('upload_private_file', {'user_id': int(user_id), 'file': file, 'name': name})

    async def get_group_root_files(self, group_id) -> dict | None:
        return await self.call_api('get_group_root_files', {'group_id': int(group_id)})

    async def get_group_files_by_folder(self, group_id, folder_id) -> dict | None:
        return await self.call_api('get_group_files_by_folder', {'group_id': int(group_id), 'folder_id': folder_id})

    async def get_group_file_url(self, group_id, file_id, busid=None) -> dict | None:
        params = {'group_id': int(group_id), 'file_id': file_id}
        if busid is not None:
            params['busid'] = busid
        return await self.call_api('get_group_file_url', params)

    async def delete_group_file(self, group_id, file_id, busid=None) -> dict | None:
        params = {'group_id': int(group_id), 'file_id': file_id}
        if busid is not None:
            params['busid'] = busid
        return await self.call_api('delete_group_file', params)

    async def create_group_file_folder(self, group_id, name) -> dict | None:
        return await self.call_api('create_group_file_folder', {'group_id': int(group_id), 'name': name})


def get_api() -> OneBotAPI:
    return OneBotAPI(_adapter_ref)
