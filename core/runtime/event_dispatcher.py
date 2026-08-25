"""按会话顺序分发事件，并限制框架全局并发量。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger('ElainaQQ.event_dispatcher')

EventProcessor = Callable[[Any, asyncio.Future[bool]], Awaitable[None]]


class EventDispatcher:
    """同一会话串行、不同会话并行的有界事件调度器。"""

    def __init__(
        self,
        processor: EventProcessor,
        *,
        max_concurrency: int = 32,
        max_pending: int = 2000,
    ) -> None:
        self._processor = processor
        self._concurrency = asyncio.Semaphore(max(1, max_concurrency))
        self._max_pending = max(1, max_pending)
        self._queues: dict[str, deque[tuple[Any, asyncio.Future[bool]]]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._pending = 0
        self._accepting = True

    @property
    def pending_count(self) -> int:
        return self._pending

    async def submit(self, ordering_key: str, event: Any) -> bool:
        """提交事件，并在事件完成持久化后返回。"""
        if not self._accepting or self._pending >= self._max_pending:
            return False

        persisted = asyncio.get_running_loop().create_future()
        queue = self._queues.setdefault(ordering_key, deque())
        queue.append((event, persisted))
        self._pending += 1
        if ordering_key not in self._workers:
            self._workers[ordering_key] = asyncio.create_task(
                self._drain(ordering_key),
                name=f'事件分发:{ordering_key[-48:]}',
            )

        try:
            return bool(await asyncio.shield(persisted))
        except asyncio.CancelledError:
            raise
        except Exception:
            return False

    async def _drain(self, ordering_key: str) -> None:
        queue = self._queues[ordering_key]
        try:
            while queue:
                event, persisted = queue[0]
                try:
                    async with self._concurrency:
                        await self._processor(event, persisted)
                    if not persisted.done():
                        persisted.set_result(True)
                except asyncio.CancelledError:
                    if not persisted.done():
                        persisted.set_result(False)
                    raise
                except Exception as error:
                    if not persisted.done():
                        persisted.set_result(False)
                    log.error('事件处理失败: %s', error, exc_info=error)
                finally:
                    queue.popleft()
                    self._pending -= 1
        finally:
            self._workers.pop(ordering_key, None)
            if not queue:
                self._queues.pop(ordering_key, None)

    async def shutdown(self) -> None:
        """停止接收新事件，并等待已经接收的事件处理完毕。"""
        self._accepting = False
        tasks = tuple(self._workers.values())
        if not tasks:
            return
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._reject_pending()
            raise

    def _reject_pending(self) -> None:
        """拒绝强制关闭时尚未处理的事件，并释放全部队列引用。"""
        for queue in self._queues.values():
            for _event, persisted in queue:
                if not persisted.done():
                    persisted.set_result(False)
        self._queues.clear()
        self._workers.clear()
        self._pending = 0
