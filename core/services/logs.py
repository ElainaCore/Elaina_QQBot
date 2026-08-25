"""SQLite 日志存储服务 (异步架构)"""

import asyncio
import contextlib
import datetime
import os
import sqlite3
import threading
import time
from collections import deque

from core.foundation.logging import SYSTEM, get_logger

log = get_logger(SYSTEM, '日志存储')


class LogService:
    """SQLite 日志服务 — 异步批量写入与定期清理"""

    _instance = None

    def __init__(
        self,
        base_dir: str,
        wal_mode: bool = True,
        insert_interval: float = 2.0,
        retention_days: int = 30,
        max_queue_entries: int = 100_000,
        max_batch_size: int = 500,
    ):
        self._base_dir = base_dir
        self._wal_mode = wal_mode
        self._insert_interval = insert_interval
        self._retention_days = retention_days
        self._max_queue_entries = max(1, int(max_queue_entries))
        self._max_batch_size = max(1, int(max_batch_size))
        self._queued_entries = 0
        self._dropped_entries = 0
        self._last_drop_warning = 0.0
        self._queues: dict[tuple[str, str], deque] = {}  # 日志类型和账号映射到待写队列
        self._connections: dict[tuple[str, str], sqlite3.Connection] = {}  # 日志类型和账号映射到数据库连接
        self._queue_lock = threading.Lock()
        self._connection_lock = threading.RLock()
        self._database_locks: dict[tuple[str, str], threading.RLock] = {}
        self._flush_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._running = False
        self._flush_task = None
        self._cleanup_task = None
        LogService._instance = self

    async def start(self):
        await asyncio.to_thread(os.makedirs, self._base_dir, exist_ok=True)
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(), name='log-retention-cleanup')
        log.info(f'日志服务启动: {self._base_dir}')

    async def shutdown(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
        try:
            await self._flush_all()
        finally:
            with self._connection_lock:
                connections = tuple(self._connections.items())
                self._connections.clear()
            for key, connection in connections:
                with self._database_lock(key):
                    connection.close()

    def _database_lock(self, key: tuple[str, str]) -> threading.RLock:
        with self._connection_lock:
            return self._database_locks.setdefault(key, threading.RLock())

    def _flush_lock(self, key: tuple[str, str]) -> asyncio.Lock:
        return self._flush_locks.setdefault(key, asyncio.Lock())

    @property
    def stats(self) -> dict[str, int]:
        """返回无需磁盘访问的队列状态快照。"""
        with self._queue_lock:
            return {
                'queued': self._queued_entries,
                'dropped': self._dropped_entries,
                'limit': self._max_queue_entries,
            }

    def update_config(
        self,
        *,
        insert_interval: float | None = None,
        retention_days: int | None = None,
        max_queue_entries: int | None = None,
        max_batch_size: int | None = None,
    ) -> None:
        """热更新不需要重建 SQLite 连接的日志参数。"""
        if insert_interval is not None:
            self._insert_interval = max(0.05, float(insert_interval))
        if retention_days is not None:
            self._retention_days = int(retention_days)
        if max_queue_entries is not None:
            self._max_queue_entries = max(1, int(max_queue_entries))
        if max_batch_size is not None:
            self._max_batch_size = max(1, int(max_batch_size))

    def _get_conn(self, log_type: str, bot_qq: str = '') -> sqlite3.Connection:
        key = (log_type, bot_qq or '')
        with self._connection_lock:
            if key in self._connections:
                return self._connections[key]
            db_path = self._database_path(key)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            if self._wal_mode:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute("""
                CREATE TABLE IF NOT EXISTS log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    content TEXT,
                    source TEXT DEFAULT '',
                    level TEXT DEFAULT 'INFO',
                    user_id TEXT DEFAULT '',
                    group_id TEXT DEFAULT '',
                    message_id TEXT DEFAULT '',
                    message_type TEXT DEFAULT '',
                    raw_data TEXT DEFAULT '',
                    extra TEXT DEFAULT ''
                )
            """)
            conn.execute('CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_log_group ON log(group_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_log_user ON log(user_id, group_id)')
            if log_type == 'message':
                # 内置 QQ 的实时回调和历史同步可能命中同一条消息。先清理旧重复，
                # 再按会话保证后续同步幂等。群消息的 user_id 是发送者，不能参与
                # 会话身份；私聊则使用 user_id 作为会话身份。
                schema_version = int(conn.execute('PRAGMA user_version').fetchone()[0])
                if schema_version < 2:
                    conn.execute('DROP INDEX IF EXISTS idx_log_message_identity')
                    conn.execute(
                        """DELETE FROM log
                           WHERE message_id != ''
                             AND id NOT IN (
                                 SELECT MIN(id) FROM log
                                 WHERE message_id != ''
                                 GROUP BY message_type, group_id,
                                          CASE WHEN group_id = '' THEN user_id ELSE '' END,
                                          message_id
                             )"""
                    )
                conn.execute(
                    'CREATE UNIQUE INDEX IF NOT EXISTS idx_log_message_identity '
                    "ON log(message_type, group_id, "
                    "CASE WHEN group_id = '' THEN user_id ELSE '' END, message_id) "
                    "WHERE message_id != ''"
                )
                conn.execute('PRAGMA user_version=2')
            conn.commit()
            self._connections[key] = conn
            return conn

    def _database_path(self, key: tuple[str, str]) -> str:
        log_type, bot_qq = key
        if bot_qq:
            return os.path.join(self._base_dir, bot_qq, f'{log_type}.db')
        return os.path.join(self._base_dir, f'{log_type}.db')

    def _warn_queue_drop(self, log_type: str) -> None:
        now = time.monotonic()
        if now - self._last_drop_warning < 30:
            return
        self._last_drop_warning = now
        log.warning(
            '日志队列已满，开始丢弃新日志 [%s]（queued=%d, dropped=%d）',
            log_type,
            self._queued_entries,
            self._dropped_entries,
        )

    def add_nowait(self, log_type: str, entry: dict, bot_qq: str = '') -> bool:
        """同步入队，仅追加到内存队列，不执行磁盘读写。

        队列有界，避免数据库异常或磁盘拥塞时无限占用内存。
        """
        key = (log_type, bot_qq or '')
        with self._queue_lock:
            if self._queued_entries >= self._max_queue_entries:
                self._dropped_entries += 1
                accepted = False
            else:
                queue = self._queues.setdefault(key, deque())
                queue.append(entry)
                self._queued_entries += 1
                accepted = True
        if not accepted:
            self._warn_queue_drop(log_type)
        return accepted

    async def add(self, log_type: str, entry: dict, bot_qq: str = '', durable: bool = False):
        """添加日志条目；关键事件可要求在返回前确认 SQLite 已提交。"""
        accepted = self.add_nowait(log_type, entry, bot_qq)
        if not accepted:
            return False
        if durable:
            await self.flush(log_type, bot_qq)
        return True

    async def add_many(self, log_type: str, entries: list[dict], bot_qq: str = '', durable: bool = False):
        """批量添加日志，供 QQ 原生历史同步使用。"""
        if durable and entries:
            await self.flush(log_type, bot_qq)
            for offset in range(0, len(entries), self._max_batch_size):
                await asyncio.to_thread(
                    self._write_entries,
                    log_type,
                    str(bot_qq or ''),
                    entries[offset : offset + self._max_batch_size],
                )
            return True
        if entries:
            key = (log_type, bot_qq or '')
            with self._queue_lock:
                available = self._max_queue_entries - self._queued_entries
                accepted = max(0, min(len(entries), available))
                if accepted:
                    self._queues.setdefault(key, deque()).extend(entries[:accepted])
                    self._queued_entries += accepted
                if accepted < len(entries):
                    self._dropped_entries += len(entries) - accepted
            if accepted < len(entries):
                self._warn_queue_drop(log_type)
            return accepted == len(entries)
        return True

    async def execute(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> int:
        """异步执行更新或删除操作。"""
        await self.flush(log_type, bot_qq)
        return await asyncio.to_thread(self._execute_sync, log_type, sql, params, bot_qq)

    def _execute_sync(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> int:
        try:
            key = (log_type, bot_qq or '')
            with self._database_lock(key):
                conn = self._get_conn(log_type, bot_qq)
                cursor = conn.execute(sql, params or [])
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            log.warning(f'执行写操作失败 [{log_type}]: {e}')
            return 0

    async def query(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
        """异步查询日志。"""
        # 面板读取前立即写出目标分库的待处理项，使最新历史无需等待定时写入。
        await self.flush(log_type, bot_qq)
        return await asyncio.to_thread(self._query_sync, log_type, sql, params, bot_qq)

    async def flush(self, log_type: str | None = None, bot_qq: str = '') -> None:
        """立即写出指定分库的待处理日志；不传类型时写出全部。"""
        with self._queue_lock:
            keys = tuple(self._queues) if log_type is None else ((str(log_type), str(bot_qq or '')),)
        if keys:
            await asyncio.gather(*(self._flush_key(key) for key in keys))

    async def _flush_key(self, key: tuple[str, str]) -> None:
        """分批写出开始刷新时已有的日志，不长期占用该分库的刷新锁。"""
        async with self._flush_lock(key):
            with self._queue_lock:
                queue = self._queues.get(key)
                remaining = len(queue) if queue else 0
            while remaining > 0:
                with self._queue_lock:
                    queue = self._queues.get(key)
                    if not queue:
                        return
                    batch_size = min(len(queue), remaining, self._max_batch_size)
                    entries = [queue.popleft() for _ in range(batch_size)]
                    self._queued_entries -= len(entries)
                    remaining -= len(entries)
                if not entries:
                    return
                try:
                    await asyncio.to_thread(self._write_entries, key[0], key[1], entries)
                except Exception:
                    # 失败批次完整放回。短暂超过软上限时，新日志会被拒绝，
                    # 但已经接收的日志不会因为并发入队而丢失。
                    with self._queue_lock:
                        queue = self._queues.setdefault(key, deque())
                        queue.extendleft(reversed(entries))
                        self._queued_entries += len(entries)
                    raise
            with self._queue_lock:
                queue = self._queues.get(key)
                if queue is not None and not queue:
                    self._queues.pop(key, None)

    def _query_sync(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
        try:
            key = (log_type, bot_qq or '')
            with self._database_lock(key):
                conn = self._get_conn(log_type, bot_qq)
                cursor = conn.execute(sql, params or [])
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            log.warning(f'查询日志失败 [{log_type}]: {e}')
            return []

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(self._insert_interval)
            try:
                await self._flush_all()
            except Exception as error:
                log.warning(f'定时写入日志失败，将在下次重试: {error}')

    async def _cleanup_loop(self):
        """定期执行日志保留清理，并回收 WAL 文件。"""
        while self._running:
            try:
                await self.cleanup()
                await asyncio.sleep(86_400)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning('日志清理失败: %s', error)

    async def _flush_all(self):
        await self.flush()

    def _write_entries(self, log_type: str, bot_qq: str, entries: list):
        key = (log_type, bot_qq or '')
        with self._database_lock(key):
            conn = self._get_conn(log_type, bot_qq)
            statement = (
                'INSERT OR IGNORE INTO log ' if log_type == 'message' else 'INSERT INTO log '
            ) + """(timestamp, content, source, level, user_id, group_id, message_id, message_type, raw_data, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            try:
                conn.execute('BEGIN')
                timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.executemany(
                    statement,
                    [
                        (
                            entry.get('timestamp', timestamp),
                            entry.get('content', ''),
                            entry.get('source', ''),
                            entry.get('level', 'INFO'),
                            entry.get('user_id', ''),
                            entry.get('group_id', ''),
                            entry.get('message_id', ''),
                            entry.get('message_type', ''),
                            entry.get('raw_data', ''),
                            entry.get('extra', ''),
                        )
                        for entry in entries
                    ],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def cleanup(self):
        """异步清理过期日志。"""
        if self._retention_days <= 0:
            return
        await self.flush()
        await asyncio.to_thread(self._cleanup_sync)

    def _cleanup_sync(self):
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=self._retention_days)).strftime('%Y-%m-%d %H:%M:%S')
        with self._connection_lock:
            connections = tuple(self._connections.items())
        active_paths = {os.path.realpath(self._database_path(key)) for key, _ in connections}
        for key, conn in connections:
            with self._database_lock(key):
                self._cleanup_connection(conn, cutoff, self._database_path(key))

        # 未在本次进程中打开的历史账号分库也必须遵守保留期限。
        for root, dirs, files in os.walk(self._base_dir):
            dirs[:] = [name for name in dirs if name != '__pycache__']
            for filename in files:
                if not filename.endswith('.db'):
                    continue
                path = os.path.realpath(os.path.join(root, filename))
                if path in active_paths:
                    continue
                try:
                    conn = sqlite3.connect(path, timeout=30)
                    try:
                        self._cleanup_connection(conn, cutoff, path)
                    finally:
                        conn.close()
                except Exception as error:
                    log.warning('清理历史日志失败 [%s]: %s', path, error)

    def _cleanup_connection(self, conn: sqlite3.Connection, cutoff: str, path: str) -> None:
        try:
            table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='log'").fetchone()
            if table is None:
                return
            while True:
                cursor = conn.execute(
                    'DELETE FROM log WHERE id IN '
                    '(SELECT id FROM log WHERE timestamp < ? LIMIT 5000)',
                    (cutoff,),
                )
                conn.commit()
                if cursor.rowcount < 5000:
                    break
            if self._wal_mode:
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception as error:
            with contextlib.suppress(Exception):
                conn.rollback()
            log.warning('清理历史日志失败 [%s]: %s', path, error)
