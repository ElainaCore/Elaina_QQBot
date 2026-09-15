"""内置 QQ 账号运行模型。"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbeddedBot:
    """表示一个内置 QQ 账号。"""

    bot_id: str
    bridge_port: int = 0
    bridge_token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    qq_version_key: str = ''
    qq_path: str = ''
    uin: str = ''
    nickname: str = ''
    force_quick_login: bool = False
    enabled: bool = True
    status: str = 'offline'
    qr_code: str = ''
    qr_url: str = ''
    error: str = ''
    created_at: float = field(default_factory=time.time)
    last_seen: float = 0.0
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    output_task: asyncio.Task | None = field(default=None, repr=False)
    reclaim_task: asyncio.Task | None = field(default=None, repr=False)
    launch_mode: str = field(default='', repr=False)

    def persisted(self) -> dict[str, Any]:
        """返回可持久化字段。"""
        return {
            'bot_id': self.bot_id,
            'bridge_port': self.bridge_port,
            'bridge_token': self.bridge_token,
            'qq_version_key': self.qq_version_key,
            'qq_path': self.qq_path,
            'uin': self.uin,
            'nickname': self.nickname,
            'force_quick_login': self.force_quick_login,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'last_seen': self.last_seen,
        }
