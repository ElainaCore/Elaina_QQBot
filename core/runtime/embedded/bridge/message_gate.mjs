function normalizeMessageTime(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return raw > 1e10 ? Math.floor(raw / 1e3) : Math.floor(raw);
}

export class IncomingMessageGate {
  constructor(startedAt = Math.floor(Date.now() / 1e3), maxSeen = 1000) {
    this.startedAt = Math.floor(Number(startedAt));
    this.maxSeen = Math.max(1, Math.floor(Number(maxSeen)));
    this.seen = new Map();
  }

  inspect(msg) {
    const isOnlineMessage = msg?.isOnlineMsg;
    if (isOnlineMessage === false) return { accept: false, reason: "history" };

    const messageTime = normalizeMessageTime(msg?.msgTime);
    if (!messageTime && isOnlineMessage !== true) {
      return { accept: false, reason: "invalid_time" };
    }
    if (isOnlineMessage !== true && messageTime < this.startedAt) {
      return { accept: false, reason: "history" };
    }

    const messageId = String(msg?.msgId || "").trim();
    if (!messageId) return { accept: true, reason: "live" };
    const key = `${msg?.chatType || ""}:${msg?.peerUid || msg?.peerUin || ""}:${messageId}`;
    if (this.seen.has(key)) return { accept: false, reason: "duplicate" };

    this.seen.set(key, true);
    if (this.seen.size > this.maxSeen) {
      this.seen.delete(this.seen.keys().next().value);
    }
    return { accept: true, reason: "live" };
  }
}

export { normalizeMessageTime };
