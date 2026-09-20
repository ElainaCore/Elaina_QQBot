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
    if fallback_self_id and data.get("self_id") in (None, "", 0, "0"):
        data["self_id"] = str(fallback_self_id)

    def first_value(*keys: str) -> Any:
        for key in keys:
            value = data.get(key)
            if value not in (None, "", 0, "0"):
                return value
        return 0

    sequence_keys = (
        "real_seq", "realSeq", "message_seq", "messageSeq", "sequence",
        "msg_seq", "msgSeq",
    )
    # OneBot message_id may be a framework-generated hash, not the protocol
    # sequence used by QQ packets. Only legacy events without any sequence
    # field may fall back to message_id.
    sequence_value = first_value(*sequence_keys)
    if not sequence_value and not any(key in data for key in sequence_keys):
        sequence_value = first_value("message_id", "messageId", "msg_id", "msgId")
    sequence = int(sequence_value or 0)
    message_seq = int(first_value("message_seq", "messageSeq", "msg_seq", "msgSeq") or sequence)
    real_seq = int(first_value("real_seq", "realSeq") or message_seq)
    message_value = int(first_value("message_id", "messageId", "msg_id", "msgId") or real_seq)
    data["message_id"] = message_value
    data["message_seq"] = message_seq
    data["real_id"] = int(first_value("real_id", "realId") or message_value)
    data["real_seq"] = real_seq
    return data
