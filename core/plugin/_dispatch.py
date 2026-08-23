"""插件事件的索引构建、匹配与异步分发。"""

import asyncio
import time
from typing import Any

from core.base.logger import PLUGIN, get_logger, report_error
from core.onebot.api import api_call_source

log = get_logger(PLUGIN, '管理器')


class _DispatchMixin:
    """异步事件分发"""

    _all_handlers: list[dict[str, Any]]
    _all_interceptors: list[dict[str, Any]]
    _all_handler_filters: list[dict[str, Any]]
    _msg_handlers: list[dict[str, Any]]
    _generic_handlers: list[dict[str, Any]]
    _typed_handlers: dict[str, list[dict[str, Any]]]
    _event_handlers: dict[str, list[dict[str, Any]]]
    _cooldowns: dict[tuple[str, ...], tuple[float, float]]
    _last_cooldown_cleanup: float

    def _is_owner(self, event) -> bool:
        """由插件管理器实现主人身份判断。"""
        raise NotImplementedError

    def _build_dispatch_index(self):
        """按优先级预先建立事件索引，避免逐事件遍历全部处理器。"""
        self._all_handlers = sorted(self._all_handlers, key=lambda h: -h['priority'])
        self._all_interceptors = sorted(self._all_interceptors, key=lambda i: -i['priority'])

        msg, generic, typed = [], [], {}
        for h in self._all_handlers:
            event_types = h['event_types']
            if not event_types:
                msg.append(h)
                generic.append(h)
                continue
            if 'message' in event_types:
                msg.append(h)
            for et in event_types:
                if et != 'message':
                    typed.setdefault(et, []).append(h)
        self._msg_handlers = msg
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
        self._cooldowns[key] = (now, cooldown)

        if len(self._cooldowns) > 4096 and now - self._last_cooldown_cleanup >= 60:
            self._last_cooldown_cleanup = now
            self._cooldowns = {item_key: value for item_key, value in self._cooldowns.items() if now - value[0] < value[1]}
        return False

    async def _is_handler_filtered(self, handler, event, cache) -> bool:
        """运行插件级事件过滤器，并按目标插件缓存本次事件的结果。"""
        target_plugin = handler.get('_plugin', '')
        if target_plugin in cache:
            return cache[target_plugin]
        blocked = False
        for item in self._all_handler_filters:
            allowed = item.get('_allowed_bots')
            if allowed is not None and str(getattr(event, 'self_id', '') or '') not in allowed:
                continue
            try:
                if item['is_coro']:
                    result = await item['func'](event, target_plugin)
                else:
                    result = await asyncio.to_thread(item['func'], event, target_plugin)
                if result is True:
                    blocked = True
                    break
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
            if allowed is not None and str(getattr(event, 'self_id', '') or '') not in allowed:
                continue
            try:
                r = await ic['func'](event) if ic['is_coro'] else await asyncio.to_thread(ic['func'], event)
                if r is True:
                    return True
            except Exception as e:
                report_error(PLUGIN, ic.get('_plugin', '?'), e)

        # 消息事件 — 仅遍历消息桶 (event 必为 MessageEvent, 直取属性)
        if post_type == 'message':
            matched = []
            filter_cache = {}
            for h in self._msg_handlers:
                allowed = h.get('_allowed_bots')
                if allowed is not None and str(getattr(event, 'self_id', '') or '') not in allowed:
                    continue
                if await self._is_handler_filtered(h, event, filter_cache):
                    continue
                if h['group_only'] and not event.is_group:
                    continue
                if h['private_only'] and not event.is_private:
                    continue
                if h['owner_only'] and not self._is_owner(event):
                    continue
                m = h['compiled'].search(content)
                if not m:
                    continue
                if self._is_cooling_down(h, event):
                    continue
                matched.append((h, m))
                if h.get('block', False):  # 仅显式启用拦截时终止后续匹配。
                    break
            if not matched:
                return False
            await self._run_chain(matched, event)
            return True

        # 通知/请求/元事件 — 候选 = 通用桶 + 该事件类型桶, 按优先级合并
        else:
            event_type = post_type
            if hasattr(event, 'notice_type'):
                event_type = f'notice.{event.notice_type}'
            elif hasattr(event, 'request_type'):
                event_type = f'request.{event.request_type}'

            candidates = self._event_handlers.get(event_type, self._generic_handlers)

            matched = []
            filter_cache = {}
            for h in candidates:
                allowed = h.get('_allowed_bots')
                if allowed is not None and str(getattr(event, 'self_id', '') or '') not in allowed:
                    continue
                if await self._is_handler_filtered(h, event, filter_cache):
                    continue
                # 非消息事件同样允许通过正则模式筛选。
                m = h['compiled'].search(content or event_type)
                if not m:
                    continue
                matched.append((h, m))
                if h.get('block', False):  # 仅显式启用拦截时终止后续匹配。
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
        try:
            fn = h['func']
            with api_call_source(h.get('_plugin', ''), event):
                async with asyncio.timeout(300):
                    if h['is_coro']:
                        await fn(event, match)
                    else:
                        await asyncio.to_thread(fn, event, match)
        except TimeoutError:
            report_error(PLUGIN, plugin_name, f'处理器 [{h["name"]}] 超时(300s)')
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
