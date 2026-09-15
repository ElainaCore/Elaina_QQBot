"""OneBot 消息短期缓存。"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class MessageCache:
    """提供按会话和序号读取的有界消息缓存。"""

    def __init__(self, limit: int = 2000) -> None:
        self._limit = max(1, int(limit))
        self._items: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()

    def put(self, payload: dict[str, Any], scope: str = "") -> None:
        message_id = _as_int(payload.get("message_id"))
        if not message_id:
            return
        key = (str(scope), abs(message_id))
        self._items[key] = dict(payload)
        self._items.move_to_end(key)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    def get(self, message_id: int, scope: str = "") -> dict[str, Any] | None:
        target = abs(_as_int(message_id))
        if not target:
            return None
        cached = self._items.get((str(scope), target))
        if cached is not None:
            return dict(cached)
        for (item_scope, _), item in reversed(self._items.items()):
            if item_scope != str(scope):
                continue
            sequence = item.get("real_seq") or item.get("message_seq") or item.get("sequence")
            if abs(_as_int(sequence)) == target:
                return dict(item)
        return None

    def __len__(self) -> int:
        return len(self._items)
