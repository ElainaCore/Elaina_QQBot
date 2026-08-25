"""插件事件的索引构建、匹配与异步分发。"""

import asyncio
import time
from typing import Any

from core.foundation.logging import PLUGIN, get_logger, report_error
from core.plugins.context import plugin_scope
from core.protocols.onebot.api import api_call_source

log = get_logger(PLUGIN, '管理器')
_MAX_COOLDOWN_ENTRIES = 8192
_DEFAULT_HANDLER_TIMEOUT = 30.0
_SLOW_HANDLER_SECONDS = 1.0


async def _await_with_budget(awaitable, timeout) -> Any:
    seconds = _DEFAULT_HANDLER_TIMEOUT if timeout is None else float(timeout)
    if seconds <= 0:
        return await awaitable
    async with asyncio.timeout(seconds):
        return await awaitable


class _DispatchMixin:
    """异步事件分发"""

    _all_handlers: list[dict[str, Any]]
    _all_interceptors: list[dict[str, Any]]
    _all_handler_filters: list[dict[str, Any]]
    _msg_handlers: list[dict[str, Any]]
    _msg_handler_stages: dict[tuple[str, bool], tuple[dict[str, Any], ...]]
    _generic_handlers: list[dict[str, Any]]
    _typed_handlers: dict[str, list[dict[str, Any]]]
    _event_handlers: dict[str, list[dict[str, Any]]]
    _cooldowns: dict[tuple[str, ...], tuple[float, float]]
    _last_cooldown_cleanup: float

    def _is_owner(self, event) -> bool:
        """由插件管理器实现主人身份判断。"""
        raise NotImplementedError

    def _allows_bot(self, allowed, self_id: str) -> bool:
        if allowed is None:
            return True
        matcher = getattr(self, '_bot_identity_matcher', None)
        return matcher(allowed, self_id) if matcher else self_id in allowed

    def _build_dispatch_index(self):
        """按优先级预先建立事件索引，避免逐事件遍历全部处理器。"""
        self._all_handlers = sorted(self._all_handlers, key=lambda h: -h['priority'])
        self._all_interceptors = sorted(self._all_interceptors, key=lambda i: -i['priority'])

        msg, generic, typed = [], [], {}
        for h in self._all_handlers:
            event_types = h['event_types']
            if not event_types:
                msg.append(h)
                continue
            if 'message' in event_types or 'message_sent' in event_types:
                msg.append(h)
            for et in event_types:
                if et not in {'message', 'message_sent'}:
                    typed.setdefault(et, []).append(h)
        self._msg_handlers = msg
        stages: dict[tuple[str, bool], list[dict[str, Any]]] = {
            ('message', False): [],
            ('message', True): [],
            ('message_sent', False): [],
            ('message_sent', True): [],
        }
        for handler in msg:
            event_types = handler.get('event_types')
            post_types = []
            if not event_types or 'message' in event_types:
                post_types.append('message')
            if event_types and 'message_sent' in event_types:
                post_types.append('message_sent')
            fallback = handler.get('fallback', False)
            fallback_stages = (False, True) if callable(fallback) else (bool(fallback),)
            for post_type in post_types:
                for fallback_stage in fallback_stages:
                    stages[(post_type, fallback_stage)].append(handler)
        self._msg_handler_stages = {
            key: tuple(handlers)
            for key, handlers in stages.items()
        }
        self._generic_handlers = generic
        self._typed_handlers = typed
        self._event_handlers = {event_type: sorted((*generic, *handlers), key=lambda item: -item['priority']) for event_type, handlers in typed.items()}

    def _is_cooling_down(self, handler, event) -> bool:
        """检查并更新按机器人、会话和用户隔离的冷却状态。"""
        cooldown = float(handler.get('cooldown') or 0)
        if cooldown <= 0:
            return False
        key = (
            handler.get('_plugin', ''),
            handler['name'],
            str(getattr(event, 'self_id', '') or ''),
            str(getattr(event, 'message_type', '') or ''),
            str(getattr(event, 'group_id', '') or ''),
            str(getattr(event, 'user_id', '') or ''),
        )
        now = time.monotonic()
        previous = self._cooldowns.get(key)
        if previous is not None and now - previous[0] < cooldown:
            return True
        if len(self._cooldowns) >= _MAX_COOLDOWN_ENTRIES and now - self._last_cooldown_cleanup >= 60:
            self._last_cooldown_cleanup = now
            self._cooldowns = {item_key: value for item_key, value in self._cooldowns.items() if now - value[0] < value[1]}
        while len(self._cooldowns) >= _MAX_COOLDOWN_ENTRIES:
            self._cooldowns.pop(next(iter(self._cooldowns)))
        self._cooldowns[key] = (now, cooldown)
        return False

    async def _is_handler_filtered(self, handler, event, cache) -> bool:
        """运行插件级事件过滤器，并按目标插件缓存本次事件的结果。"""
        target_plugin = handler.get('_plugin', '')
        if target_plugin in cache:
            return cache[target_plugin]
        blocked = False
        for item in self._all_handler_filters:
            allowed = item.get('_allowed_bots')
            if not self._allows_bot(allowed, str(getattr(event, 'self_id', '') or '')):
                continue
            try:
                with plugin_scope(item['_context']):
                    result = await _await_with_budget(
                        item['func'](event, target_plugin),
                        item.get('timeout'),
                    )
                if result is True:
                    blocked = True
                    break
            except TimeoutError:
                report_error(PLUGIN, item.get('_plugin', '?'), '处理器过滤器超时')
            except Exception as exc:
                report_error(PLUGIN, item.get('_plugin', '?'), exc)
        cache[target_plugin] = blocked
        return blocked

    async def dispatch(self, event) -> bool:
        """异步分发事件到匹配的处理器, 返回是否命中"""
        content = event.content
        post_type = event.post_type

        # 拦截器
        for ic in self._all_interceptors:
            allowed = ic.get('_allowed_bots')
            if not self._allows_bot(allowed, str(getattr(event, 'self_id', '') or '')):
                continue
            try:
                with plugin_scope(ic['_context']):
                    r = await _await_with_budget(ic['func'](event), ic.get('timeout'))
                if r is True:
                    return True
            except TimeoutError:
                report_error(PLUGIN, ic.get('_plugin', '?'), '事件拦截器超时')
            except Exception as e:
                report_error(PLUGIN, ic.get('_plugin', '?'), e)

        # 消息事件：普通处理器先匹配原文和斜杠兼容文本，均未命中后才运行兜底处理器。
        if post_type in {'message', 'message_sent'}:
            filter_cache: dict[str, bool] = {}
            if await self._match_message_handlers(event, content, filter_cache, fallback_stage=False):
                return True
            alternative = content[1:] if content.startswith('/') else f'/{content}'
            if alternative != content and await self._match_message_handlers(
                event, alternative, filter_cache, fallback_stage=False
            ):
                return True
            return await self._match_message_handlers(
                event, content, filter_cache, fallback_stage=True
            )

        # 通知/请求/元事件 — 候选 = 通用桶 + 该事件类型桶, 按优先级合并
        else:
            event_type = post_type
            if hasattr(event, 'notice_type'):
                event_type = f'notice.{event.notice_type}'
            elif hasattr(event, 'request_type'):
                event_type = f'request.{event.request_type}'
            elif hasattr(event, 'meta_event_type'):
                event_type = f'meta_event.{event.meta_event_type}'

            candidates = self._event_handlers.get(event_type, self._generic_handlers)

            matched = []
            filter_cache = {}
            for h in candidates:
                allowed = h.get('_allowed_bots')
                if not self._allows_bot(allowed, str(getattr(event, 'self_id', '') or '')):
                    continue
                # 非消息事件同样允许通过正则模式筛选。
                m = h['compiled'].search(content or event_type)
                if not m:
                    continue
                if await self._is_handler_filtered(h, event, filter_cache):
                    continue
                matched.append((h, m))
                if h.get('block', False):  # 仅显式启用拦截时终止后续匹配。
                    break
            if not matched:
                return False
            await self._run_chain(matched, event)
            return True

    async def _match_message_handlers(self, event, content, filter_cache, *, fallback_stage):
        """匹配一个消息阶段；宽泛兜底不会阻止后续斜杠兼容指令。"""
        matched = []
        self_id = str(getattr(event, 'self_id', '') or '')
        post_type = str(getattr(event, 'post_type', '') or '')
        is_group = event.is_group
        is_private = event.is_private
        candidates = self._msg_handler_stages.get((post_type, fallback_stage), ())
        for h in candidates:
            if callable(h.get('fallback')) and _fallback_enabled(h, event) != fallback_stage:
                continue
            allowed = h.get('_allowed_bots')
            if not self._allows_bot(allowed, self_id):
                continue
            if h['group_only'] and not is_group:
                continue
            if h['private_only'] and not is_private:
                continue
            if h['owner_only'] and not self._is_owner(event):
                continue
            match = h['compiled'].search(content)
            if not match:
                continue
            if await self._is_handler_filtered(h, event, filter_cache):
                continue
            if self._is_cooling_down(h, event):
                continue
            matched.append((h, match))
            if h.get('block', False):
                break
        if not matched:
            return False
        await self._run_chain(matched, event)
        return True

    async def _run_chain(self, matched, event):
        """顺序执行命中的处理器链 (回复顺序与 priority 一致)"""
        for h, match in matched:
            await self._run_handler(h, event, match)

    async def _run_handler(self, h, event, match):
        """执行单个处理器 (带超时和异常捕获)"""
        plugin_name = h['name'] or h.get('_plugin', '')
        started = time.monotonic()
        timeout = _DEFAULT_HANDLER_TIMEOUT if h.get('timeout') is None else float(h['timeout'])
        try:
            fn = h['func']
            with plugin_scope(h['_context']), api_call_source(h.get('_plugin', ''), event):
                await _await_with_budget(fn(event, match), timeout)
        except TimeoutError:
            report_error(PLUGIN, plugin_name, f'处理器 [{h["name"]}] 超时({timeout:g}s)')
        except Exception as e:
            report_error(
                PLUGIN,
                plugin_name,
                e,
                context={
                    'handler': h['name'],
                    'user_id': str(getattr(event, 'user_id', '')),
                    'group_id': str(getattr(event, 'group_id', '')),
                    'content': (event.content if hasattr(event, 'content') else '')[:200],
                },
            )
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= _SLOW_HANDLER_SECONDS:
                log.warning('插件处理器 [%s/%s] 执行 %.3f 秒', h.get('_plugin', '?'), h['name'], elapsed)


def _fallback_enabled(handler, event) -> bool:
    """解析静态或按事件动态计算的兜底开关。"""
    value = handler.get('fallback', False)
    if not callable(value):
        return bool(value)
    try:
        return bool(value(event))
    except Exception as exc:
        report_error(PLUGIN, handler.get('_plugin', '?'), exc)
        return True
