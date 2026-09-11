"""统一四渠道事件入口。"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from core.protocols.onebot.adapter import OneBotAdapter
from core.protocols.onebot.contract import event_deduplication_key, event_ordering_key
from core.runtime.event_dispatcher import EventDispatcher


class EventPipeline:
    """规范化、幂等和排队的单一入口。"""

    def __init__(
        self,
        adapter: OneBotAdapter,
        dispatcher: EventDispatcher,
        *,
        dedup_ttl: float = 5.0,
        dedup_limit: int = 8192,
    ) -> None:
        self._adapter = adapter
        self._dispatcher = dispatcher
        self._dedup_ttl = max(0.0, float(dedup_ttl))
        self._dedup_limit = max(128, int(dedup_limit))
        self._recent: OrderedDict[tuple[str, ...], float] = OrderedDict()
        self._dropped_duplicates = 0
        self._accepted = 0
        self._rejected = 0

    @property
    def stats(self) -> dict[str, int]:
        return {
            'accepted': self._accepted,
            'rejected': self._rejected,
            'duplicates': self._dropped_duplicates,
            'pending': self._dispatcher.pending_count,
        }

    async def ingest(
        self,
        payload: dict,
        default_self_id: str = '',
        *,
        source: str = '',
    ) -> bool:
        event = self._adapter.parse_event(payload, default_self_id, source)
        if event is None:
            self._rejected += 1
            return False
        if self._is_duplicate(event):
            self._dropped_duplicates += 1
            return True
        accepted = await self._dispatcher.submit(event_ordering_key(event), event)
        if accepted:
            self._accepted += 1
            self._remember(event)
        else:
            self._rejected += 1
        return accepted

    def _is_duplicate(self, event: Any) -> bool:
        key = event_deduplication_key(event)
        if key is None or self._dedup_ttl <= 0:
            return False
        now = time.monotonic()
        # 只在访问路径清理过期项，避免每条事件创建后台任务。
        while self._recent:
            first_key, first_seen = next(iter(self._recent.items()))
            if now - first_seen <= self._dedup_ttl:
                break
            self._recent.pop(first_key, None)
        previous = self._recent.get(key)
        if previous is not None and now - previous <= self._dedup_ttl:
            self._recent.move_to_end(key)
            return True
        return False

    def _remember(self, event: Any) -> None:
        key = event_deduplication_key(event)
        if key is None or self._dedup_ttl <= 0:
            return
        now = time.monotonic()
        self._recent[key] = now
        self._recent.move_to_end(key)
        while len(self._recent) > self._dedup_limit:
            self._recent.popitem(last=False)

    async def shutdown(self) -> None:
        self._recent.clear()
        await self._dispatcher.shutdown()


__all__ = ['EventPipeline']
