"""内置 QQ 设备标识工具。"""

from __future__ import annotations

import hashlib
import os
import re


def stable_device_guid(bot_id: str) -> str:
    """生成稳定设备 GUID。"""
    raw = hashlib.sha256(f'elainaqq-device:{bot_id}'.encode()).hexdigest()[:32]
    return f'{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}'


def device_name(bot_id: str) -> str:
    """生成账号独立设备名。"""
    host = os.uname().nodename if hasattr(os, 'uname') else (os.environ.get('COMPUTERNAME') or 'elainaqq')
    safe_id = re.sub(r'[^A-Za-z0-9._-]', '_', bot_id).strip('._') or 'account'
    return f'{host[:48]}-{safe_id}'
