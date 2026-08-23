"""SQLite 日志存储服务 (异步架构)"""

import asyncio
import datetime
import os
import sqlite3
from collections import deque

from core.base.logger import SYSTEM, get_logger

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
        self._lock = asyncio.Lock()
        self._running = False
        self._flush_task = None
        LogService._instance = self

    async def start(self):
        os.makedirs(self._base_dir, exist_ok=True)
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        log.info(f'日志服务启动: {self._base_dir}')

    async def shutdown(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_all()
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()

    def _get_conn(self, log_type: str, bot_qq: str = '') -> sqlite3.Connection:
        key = (log_type, bot_qq or '')
        if key in self._connections:
            return self._connections[key]
        if bot_qq:
            db_dir = os.path.join(self._base_dir, str(bot_qq))
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, f'{log_type}.db')
        else:
            db_path = os.path.join(self._base_dir, f'{log_type}.db')
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if self._wal_mode:
            conn.execute('PRAGMA journal_mode=WAL')
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
        conn.commit()
        self._connections[key] = conn
        return conn

    def add_nowait(self, log_type: str, entry: dict, bot_qq: str = ''):
        """同步入队 (供同步上下文使用, 如日志 handler); 仅追加到内存队列, 不做 IO"""
        key = (log_type, bot_qq or '')
        if key not in self._queues:
            self._queues[key] = deque()
        self._queues[key].append(entry)

    async def add(self, log_type: str, entry: dict, bot_qq: str = ''):
        """异步添加日志条目到队列"""
        self.add_nowait(log_type, entry, bot_qq)

    async def execute(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> int:
        """异步执行写操作（UPDATE/DELETE）"""
        return await asyncio.to_thread(self._execute_sync, log_type, sql, params, bot_qq)

    def _execute_sync(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> int:
        try:
            conn = self._get_conn(log_type, bot_qq)
            cursor = conn.execute(sql, params or [])
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            log.warning(f'执行写操作失败 [{log_type}]: {e}')
            return 0

    async def query(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
        """异步查询日志"""
        return await asyncio.to_thread(self._query_sync, log_type, sql, params, bot_qq)

    def _query_sync(self, log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
        try:
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
            await self._flush_all()

    async def _flush_all(self):
        for key in list(self._queues.keys()):
            queue = self._queues.get(key)
            if not queue:
                continue
            entries = []
            while queue:
                entries.append(queue.popleft())
            if not entries:
                continue
            log_type, bot_qq = key
            await asyncio.to_thread(self._write_entries, log_type, bot_qq, entries)

    def _write_entries(self, log_type: str, bot_qq: str, entries: list):
        try:
            conn = self._get_conn(log_type, bot_qq)
            for entry in entries:
                conn.execute(
                    """INSERT INTO log (timestamp, content, source, level, user_id, group_id, message_id, message_type, raw_data, extra)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.get('timestamp', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                        entry.get('content', ''),
                        entry.get('source', ''),
                        entry.get('level', 'INFO'),
                        entry.get('user_id', ''),
                        entry.get('group_id', ''),
                        entry.get('message_id', ''),
                        entry.get('message_type', ''),
                        entry.get('raw_data', ''),
                        entry.get('extra', ''),
                    ),
                )
            conn.commit()
        except Exception as e:
            log.warning(f'写入日志失败 [{log_type}]: {e}')

    async def cleanup(self):
        """异步清理过期日志"""
        if self._retention_days <= 0:
            return
        await asyncio.to_thread(self._cleanup_sync)

    def _cleanup_sync(self):
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=self._retention_days)).strftime('%Y-%m-%d %H:%M:%S')
        for conn in self._connections.values():
            try:
                conn.execute('DELETE FROM log WHERE timestamp < ?', (cutoff,))
                conn.commit()
            except Exception:
                pass
