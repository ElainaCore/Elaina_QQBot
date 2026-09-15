"""OneBot 消息身份与序号规范化。"""

from __future__ import annotations

import hashlib
from typing import Any


def hash_message_id(sequence: int, session_id: int, event_name: str) -> int:
    """生成稳定的 OneBot int32 消息 ID。"""
    key = f"{int(sequence)}:{int(session_id)}:{event_name}".encode()
    value = int.from_bytes(
        hashlib.sha1(key, usedforsecurity=False).digest()[:4],
        "big",
        signed=True,
    )
    return value or 1


def message_id(
    sequence: int,
    *,
    group_id: int | None = None,
    peer_id: int = 0,
    self_id: int = 0,
    nt_msg_seq: int = 0,
) -> int:
    """按会话类型生成跨渠道一致的消息 ID。"""
    sequence = int(sequence or 0)
    if group_id not in (None, 0, ""):
        return hash_message_id(sequence, int(group_id), "group_message")
    peer_id = int(peer_id or 0)
    sent = peer_id == int(self_id or 0)
    if int(nt_msg_seq or 0) > 0:
        return hash_message_id(
            int(nt_msg_seq),
            peer_id,
            "private_message_sent" if sent else "private_message_nt",
        )
    return hash_message_id(
        sequence,
        peer_id,
        "private_message_sent" if sent else "private_message",
    )


def normalize_message_identity(payload: dict[str, Any], fallback_self_id: str = "") -> dict[str, Any]:
    """补齐 message_id、message_seq、real_id 与 real_seq。"""
    data = dict(payload)
    if fallback_self_id and not data.get("self_id"):
        data["self_id"] = str(fallback_self_id)
    sequence = int(
        data.get("real_seq")
        or data.get("message_seq")
        or data.get("sequence")
        or data.get("message_id")
        or 0
    )
    message_seq = int(data.get("message_seq") or sequence)
    real_seq = int(data.get("real_seq") or message_seq)
    message_value = int(data.get("message_id") or real_seq)
    data["message_id"] = message_value
    data["message_seq"] = message_seq
    data["real_id"] = int(data.get("real_id") or message_value)
    data["real_seq"] = real_seq
    return data
