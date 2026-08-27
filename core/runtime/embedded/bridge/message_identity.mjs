import { createHash } from "crypto";

function usableId(value) {
  const text = String(value ?? "").trim();
  return text && text !== "0" ? text : "";
}

function messagePeer(peerOrMessage = {}, fallbackChatType = 0, fallbackPeerUid = "") {
  return {
    chatType: Number(peerOrMessage?.chatType || fallbackChatType || 0),
    peerUid: String(peerOrMessage?.peerUid || peerOrMessage?.peerUin || fallbackPeerUid || ""),
  };
}

/** 生成线路层使用的稳定 OneBot 消息编号。 */
export function toOneBotMessageId(value, peerOrMessage = {}, fallbackChatType = 0, fallbackPeerUid = "") {
  const msgId = usableId(value) || String(value ?? "");
  const peer = messagePeer(peerOrMessage, fallbackChatType, fallbackPeerUid);
  const digest = createHash("md5").update(msgId + "|" + peer.chatType + "|" + peer.peerUid).digest();
  digest[0] &= 0x7f;
  return digest.readInt32BE(0);
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
    messageId: toOneBotMessageId(key, message),
    nativeId,
    recordId,
    replyId,
    sequence: realSequence,
    clientSequence: usableId(reply?.replyMsgClientSeq || record?.clientSeq),
    record,
    senderUin: usableId(record?.senderUin) || usableId(reply?.senderUin || reply?.senderUinStr),
    senderUid: usableId(record?.senderUid) || usableId(reply?.senderUidStr),
    senderName: String(record?.sendMemberName || record?.sendNickName || ""),
    msgTime: usableId(record?.msgTime) || usableId(reply?.replyMsgTime),
    msgRandom: usableId(record?.msgRandom),
  };
}
