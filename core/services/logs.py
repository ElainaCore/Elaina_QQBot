"""SQLite 日志存储服务 (异步架构)"""

import asyncio
import contextlib
import datetime
import os
import sqlite3
import threading
from collections import deque

from core.foundation.logging import SYSTEM, get_logger

log = get_logger(SYSTEM, '日志存储')


class LogService:
    """SQLite 日志服务 — 异步批量写入与定期清理"""

    _instance = None

    def __init__(self, base_dir: str, wal_mode: bool = True, insert_interval: float = 2.0, retention_days: int = 30):
        self._base_dir = base_dir
        self._wal_mode = wal_mode
        self._insert_interval = insert_interval
        self._retention_days = retention_days
        self._queues: dict[tuple[str, str], deque] = {}  # 日志类型和账号映射到待写队列
        self._connections: dict[tuple[str, str], sqlite3.Connection] = {}  # 日志类型和账号映射到数据库连接
        self._queue_lock = threading.Lock()
        self._db_lock = threading.RLock()
        self._lock = asyncio.Lock()
        self._running = False
        self._flush_task = None
        LogService._instance = self

    async def start(self):
        await asyncio.to_thread(os.makedirs, self._base_dir, exist_ok=True)
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        log.info(f'日志服务启动: {self._base_dir}')

    async def shutdown(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
        try:
            await self._flush_all()
        finally:
            with self._db_lock:
                for conn in self._connections.values():
                    conn.close()
                self._connections.clear()

    def _get_conn(self, log_type: str, bot_qq: str = '') -> sqlite3.Connection:
        key = (log_type, bot_qq or '')
        with self._db_lock:
            if key in self._connections:
                return self._connections[key]
            if bot_qq:
                db_dir = os.path.join(self._base_dir, str(bot_qq))
                os.makedirs(db_dir, exist_ok=True)
                db_path = os.path.join(db_dir, f'{log_type}.db')
            else:
                db_path = os.path.join(self._base_dir, f'{log_type}.db')
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

    def add_nowait(self, log_type: str, entry: dict, bot_qq: str = ''):
        """同步入队 (供同步上下文使用, 如日志 handler); 仅追加到内存队列, 不做 IO"""
        key = (log_type, bot_qq or '')
        with self._queue_lock:
            if key not in self._queues:
                self._queues[key] = deque()
            self._queues[key].append(entry)

    async def add(self, log_type: str, entry: dict, bot_qq: str = '', durable: bool = False):
        """添加日志条目；关键事件可要求在返回前确认 SQLite 已提交。"""
        self.add_nowait(log_type, entry, bot_qq)
        if durable:
            await self.flush(log_type, bot_qq)

    async def add_many(self, log_type: str, entries: list[dict], bot_qq: str = '', durable: bool = False):
        """批量添加日志，供 QQ 原生历史同步使用。"""
        if entries:
            key = (log_type, bot_qq or '')
            with self._queue_lock:
                self._queues.setdefault(key, deque()).extend(entries)
        if durable and entries:
            await self.flush(log_type, bot_qq)

    async def execute(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> int:
        """异步执行写操作（UPDATE/DELETE）"""
        return await asyncio.to_thread(self._execute_sync, log_type, sql, params, bot_qq)

    def _execute_sync(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> int:
        try:
            with self._db_lock:
                conn = self._get_conn(log_type, bot_qq)
                cursor = conn.execute(sql, params or [])
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            log.warning(f'执行写操作失败 [{log_type}]: {e}')
            return 0

    async def query(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
        """异步查询日志"""
        # 面板读取前立即写出目标分库的待处理项，使内置 QQ 的最新历史无需等待定时 flush。
        await self.flush(log_type, bot_qq)
        return await asyncio.to_thread(self._query_sync, log_type, sql, params, bot_qq)

    async def flush(self, log_type: str | None = None, bot_qq: str = '') -> None:
        """立即写出指定分库的待处理日志；不传类型时写出全部。"""
        async with self._lock:
            with self._queue_lock:
                keys = list(self._queues) if log_type is None else [(str(log_type), str(bot_qq or ''))]
            for key in keys:
                with self._queue_lock:
                    queue = self._queues.get(key)
                    entries = list(queue) if queue else []
                    if queue:
                        queue.clear()
                if not entries:
                    continue
                try:
                    await asyncio.to_thread(self._write_entries, key[0], key[1], entries)
                except Exception:
                    # 写入失败时把整批放回队首，不能静默丢失消息和事件。
                    with self._queue_lock:
                        queue = self._queues.setdefault(key, deque())
                        queue.extendleft(reversed(entries))
                    raise

    def _query_sync(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
        try:
            with self._db_lock:
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

    async def _flush_all(self):
        await self.flush()

    def _write_entries(self, log_type: str, bot_qq: str, entries: list):
        with self._db_lock:
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
        """异步清理过期日志"""
        if self._retention_days <= 0:
            return
        await asyncio.to_thread(self._cleanup_sync)

    def _cleanup_sync(self):
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=self._retention_days)).strftime('%Y-%m-%d %H:%M:%S')
        with self._db_lock:
            for conn in tuple(self._connections.values()):
                try:
                    conn.execute('DELETE FROM log WHERE timestamp < ?', (cutoff,))
                    conn.commit()
                except Exception:
                    pass
