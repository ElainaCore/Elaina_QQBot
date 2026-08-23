const MAX_SAFE_MESSAGE_ID = 9007199254740991n;
const HASH_OFFSET = 1469598103934665603n;
const HASH_PRIME = 1099511628211n;

function usableId(value) {
  const text = String(value ?? "").trim();
  return text && text !== "0" ? text : "";
}

function stableHash(value) {
  let hash = HASH_OFFSET;
  for (const character of value) {
    hash ^= BigInt(character.codePointAt(0));
    hash = hash * HASH_PRIME % MAX_SAFE_MESSAGE_ID;
  }
  return hash || 1n;
}

/** 将 QQ 原生消息标识稳定映射为 OneBot 可安全传输的整数。 */
export function toOneBotMessageId(value) {
  const text = usableId(value) || String(value ?? "");
  if (/^[1-9]\d*$/.test(text)) {
    const numeric = BigInt(text);
    if (numeric <= MAX_SAFE_MESSAGE_ID) return Number(numeric);
  }
  return Number(stableHash(text));
}

/** 获取原生消息的稳定标识；缺少 msgId 时使用会话与序号组合兜底。 */
export function nativeMessageKey(message) {
  const nativeId = usableId(message?.msgId || message?.messageId || message?.msg_id);
  if (nativeId) return nativeId;
  return [
    "message",
    message?.chatType,
    message?.peerUid || message?.peerUin,
    message?.senderUid || message?.senderUin,
    message?.msgSeq || message?.clientSeq,
    message?.msgTime,
  ].map((item) => String(item ?? "")).join(":");
}

/** 从 QQ 引用元素中解析目标消息，并生成与目标事件一致的 OneBot 消息 ID。 */
export function resolveReplyReference(element, message) {
  const reply = element?.replyElement;
  if (!reply) return null;

  const recordId = usableId(reply.sourceMsgIdInRecords);
  const replyId = usableId(reply.replayMsgId || reply.replyMsgId);
  const sequence = usableId(reply.replayMsgSeq || reply.replyMsgSeq);
  const records = Array.isArray(message?.records) ? message.records : [];
  const record = records.find((item) => {
    const itemId = usableId(item?.msgId || item?.messageId);
    return (recordId && itemId === recordId) || (replyId && itemId === replyId);
  }) || records.find((item) => sequence && String(item?.msgSeq ?? "") === sequence) || null;

  const nativeId = usableId(record?.msgId || record?.messageId) || replyId || recordId;
  const realSequence = usableId(record?.msgSeq) || sequence;
  if (!nativeId && !realSequence) return null;

  const fallbackKey = [
    "reply",
    message?.chatType,
    message?.peerUid || message?.peerUin,
    reply?.senderUidStr || reply?.senderUin,
    realSequence,
  ].map((item) => String(item ?? "")).join(":");
  const key = nativeId || fallbackKey;
  return {
    messageId: toOneBotMessageId(key),
    nativeId,
    sequence: realSequence,
    record,
    senderUin: usableId(record?.senderUin) || usableId(reply?.senderUin),
    senderName: String(record?.sendMemberName || record?.sendNickName || ""),
  };
}
