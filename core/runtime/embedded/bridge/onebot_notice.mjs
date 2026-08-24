function asBuffer(value) {
  if (Buffer.isBuffer(value)) return value;
  if (value instanceof Uint8Array) return Buffer.from(value);
  if (Array.isArray(value)) return Buffer.from(value);
  return Buffer.alloc(0);
}

function readVarint(buffer, start) {
  let value = 0n;
  let shift = 0n;
  let offset = start;
  while (offset < buffer.length && shift < 70n) {
    const byte = buffer[offset++];
    value |= BigInt(byte & 0x7f) << shift;
    if ((byte & 0x80) === 0) return { value, offset };
    shift += 7n;
  }
  throw new Error("无效的 protobuf varint");
}

/** Minimal protobuf reader for the QQNT system-push messages used by NapCat. */
export function decodeProtoFields(value) {
  const buffer = asBuffer(value);
  const fields = new Map();
  let offset = 0;
  while (offset < buffer.length) {
    const tag = readVarint(buffer, offset);
    offset = tag.offset;
    const number = Number(tag.value >> 3n);
    const wire = Number(tag.value & 7n);
    if (!number) throw new Error("无效的 protobuf 字段号");
    let fieldValue;
    if (wire === 0) {
      const decoded = readVarint(buffer, offset);
      fieldValue = decoded.value;
      offset = decoded.offset;
    } else if (wire === 1) {
      if (offset + 8 > buffer.length) throw new Error("截断的 protobuf fixed64");
      fieldValue = buffer.subarray(offset, offset + 8);
      offset += 8;
    } else if (wire === 2) {
      const length = readVarint(buffer, offset);
      offset = length.offset;
      const end = offset + Number(length.value);
      if (end > buffer.length) throw new Error("截断的 protobuf bytes");
      fieldValue = buffer.subarray(offset, end);
      offset = end;
    } else if (wire === 5) {
      if (offset + 4 > buffer.length) throw new Error("截断的 protobuf fixed32");
      fieldValue = buffer.subarray(offset, offset + 4);
      offset += 4;
    } else {
      throw new Error("不支持的 protobuf wire type: " + wire);
    }
    const values = fields.get(number) || [];
    values.push({ wire, value: fieldValue });
    fields.set(number, values);
  }
  return fields;
}

function first(fields, number) {
  return fields.get(number)?.[0]?.value;
}

function integer(fields, number, fallback = 0) {
  const value = first(fields, number);
  if (typeof value !== "bigint") return fallback;
  const numeric = Number(value);
  return Number.isSafeInteger(numeric) ? numeric : value.toString();
}

function bytes(fields, number) {
  const value = first(fields, number);
  return Buffer.isBuffer(value) || value instanceof Uint8Array ? Buffer.from(value) : Buffer.alloc(0);
}

function string(fields, number) {
  return bytes(fields, number).toString("utf8");
}

function nested(fields, number) {
  const value = bytes(fields, number);
  return value.length ? decodeProtoFields(value) : new Map();
}

function asciiOrNestedOperator(value) {
  const buffer = asBuffer(value);
  if (!buffer.length) return "";
  if (buffer[0] === 0x0a) {
    try {
      return string(nested(decodeProtoFields(buffer), 1), 1);
    } catch {
    }
  }
  const text = buffer.toString("utf8");
  return /^[\x20-\x7e]+$/.test(text) ? text : "";
}

function parseProfileLike(content) {
  const root = decodeProtoFields(content);
  if (integer(root, 1) !== 0 || integer(root, 2) !== 203) return null;
  const likeMessage = nested(nested(root, 203), 14);
  const detail = nested(likeMessage, 3);
  const match = string(detail, 1).match(/\d+/);
  if (!detail.size) return null;
  return {
    post_type: "notice",
    notice_type: "notify",
    sub_type: "profile_like",
    operator_id: integer(detail, 3),
    operator_nick: string(detail, 5),
    times: Number(match?.[0] || 0),
    time: integer(likeMessage, 2),
  };
}

const GROUP_INCREASE_NOTIFY_TYPES = new Set([4, 5, 6, 7]);

/** Build a recent-member candidate from QQNT's accepted group request notice. */
export function groupIncreaseCandidateFromNotify(notify, observedAt = Date.now()) {
  const type = Number(notify?.type || 0);
  const status = Number(notify?.status || 0);
  const groupId = String(notify?.group?.groupCode || notify?.groupCode || "");
  const memberUid = String(notify?.user1?.uid || "");
  const operatorUid = String(notify?.actionUser?.uid || notify?.user2?.uid || "");
  if (!GROUP_INCREASE_NOTIFY_TYPES.has(type) || status !== 2 || !groupId || !memberUid) return null;
  return {
    groupId,
    memberUid,
    operatorUid,
    type,
    observedAt: Number(observedAt) || Date.now(),
    seq: String(notify?.seq || ""),
  };
}

/** Return a candidate only when the recent notices identify one unique member. */
export function findGroupIncreaseCandidate(candidates, groupId, operatorUid = "", now = Date.now(), maxAge = 10000) {
  const group = String(groupId || "");
  const operator = String(operatorUid || "");
  const cutoff = Number(now) - Math.max(0, Number(maxAge) || 0);
  const matches = Array.from(candidates || []).filter((candidate) => {
    if (!candidate || String(candidate.groupId || "") !== group) return false;
    if (operator && String(candidate.operatorUid || "") !== operator) return false;
    return Number(candidate.observedAt || 0) >= cutoff;
  });
  const members = new Set(matches.map((candidate) => String(candidate.memberUid || "")).filter(Boolean));
  if (members.size !== 1) return null;
  return matches
    .filter((candidate) => String(candidate.memberUid || "") === members.values().next().value)
    .sort((left, right) => Number(right.observedAt || 0) - Number(left.observedAt || 0))[0] || null;
}

/** Decode the OneBot event-bearing branches handled by NapCat's onRecvSysMsg. */
export function decodeNapCatSystemNotice(payload) {
  const root = decodeProtoFields(payload);
  const response = nested(root, 1);
  const content = nested(root, 2);
  const body = nested(root, 3);
  const type = Number(integer(content, 1));
  const subType = Number(integer(content, 2));
  const c2cCmd = Number(integer(content, 3));
  const msgContent = bytes(body, 2);
  const peerId = integer(response, 1);

  if (type === 33 && msgContent.length) {
    const change = decodeProtoFields(msgContent);
    return {
      post_type: "notice", notice_type: "group_increase",
      group_id: integer(change, 1), member_uid: string(change, 3),
      operator_uid: asciiOrNestedOperator(bytes(change, 5)),
      sub_type: Number(integer(change, 4)) === 131 ? "invite" : "approve",
    };
  }
  if (type === 34 && msgContent.length) {
    const change = decodeProtoFields(msgContent);
    const decreaseType = Number(integer(change, 4));
    const types = new Map([[130, "leave"], [131, "kick"], [3, "kick_me"], [129, "disband"]]);
    return {
      post_type: "notice", notice_type: "group_decrease",
      group_id: integer(change, 1), member_uid: string(change, 3),
      operator_uid: asciiOrNestedOperator(bytes(change, 5)),
      sub_type: types.get(decreaseType) || "kick",
    };
  }
  if (type === 44 && msgContent.length) {
    const admin = decodeProtoFields(msgContent);
    const adminBody = nested(admin, 4);
    const enabled = adminBody.has(2);
    const entry = nested(adminBody, enabled ? 2 : 1);
    return {
      post_type: "notice", notice_type: "group_admin",
      group_id: integer(admin, 1), member_uid: string(entry, 1),
      sub_type: enabled ? "set" : "unset",
    };
  }
  if (type === 87 && msgContent.length) {
    const invite = decodeProtoFields(msgContent);
    return {
      post_type: "request", request_type: "group", sub_type: "invite",
      group_id: integer(invite, 1), inviter_uid: string(invite, 5),
    };
  }
  if (type === 528 && subType === 39 && msgContent.length) return parseProfileLike(msgContent);
  if (type === 166 && c2cCmd === 133 && msgContent.length > 17) {
    const mainCmd = msgContent[15];
    const command = msgContent[17];
    if (![101, 136].includes(mainCmd)) return null;
    if (command === 225) {
      return { post_type: "notice", notice_type: "online_file_receive", sub_type: "cancel", peer_id: peerId };
    }
    if (command === 230) {
      return { post_type: "notice", notice_type: "online_file_send", sub_type: "refuse", peer_id: peerId };
    }
    return null;
  }
  if (type === 166 && c2cCmd === 131 && msgContent.length) {
    return { post_type: "notice", notice_type: "online_file_send", sub_type: "receive", peer_id: peerId };
  }
  return null;
}

function xmlAttribute(content, tag, name) {
  const element = String(content || "").match(new RegExp("<" + tag + "\\b[^>]*>", "i"))?.[0] || "";
  const match = element.match(new RegExp("\\b" + name + "\\s*=\\s*([\"'])((?:(?!\\1).)*)\\1", "i"));
  return match?.[2] || "";
}

export function parseEmojiLikeGrayTip(content) {
  const senderUin = xmlAttribute(content, "qq", "jp");
  const messageSeq = xmlAttribute(content, "url", "msgseq");
  const emojiId = xmlAttribute(content, "face", "id");
  return senderUin && messageSeq && emojiId
    ? { senderUin, messageSeq, emojiId, count: 1, isAdd: true }
    : null;
}

/** Decode NapCat's raw OlPush group-reaction packet without a protobuf dependency. */
export function parseGroupReactionPacket(payload) {
  try {
    const packet = typeof payload === "string"
      ? Buffer.from(payload, "hex")
      : asBuffer(payload);
    if (!packet.length) return null;

    const push = decodeProtoFields(packet);
    const message = nested(push, 1);
    const contentHead = nested(message, 2);
    if (Number(integer(contentHead, 1)) !== 732 || Number(integer(contentHead, 2)) !== 16) return null;

    const msgContent = bytes(nested(message, 3), 2);
    if (msgContent.length <= 7) return null;
    const notify = decodeProtoFields(msgContent.subarray(7));
    if (Number(integer(notify, 13)) !== 35) return null;

    const reactionData = nested(nested(nested(notify, 44), 1), 1);
    const target = nested(reactionData, 2);
    const content = nested(reactionData, 3);
    const groupId = String(integer(notify, 4, "") || "");
    const operatorUid = string(content, 4);
    const messageSeq = String(integer(target, 1, "") || "");
    const emojiId = string(content, 1);
    if (!groupId || !operatorUid || !messageSeq || !emojiId) return null;
    return {
      groupId,
      operatorUid,
      messageSeq,
      emojiId,
      count: content.has(3) ? Number(integer(content, 3)) : 1,
      isAdd: Number(integer(content, 5)) === 1,
    };
  } catch {
    return null;
  }
}

export function parseEssenceGrayTip(jsonValue) {
  let data;
  try {
    data = typeof jsonValue === "string" ? JSON.parse(jsonValue) : jsonValue;
  } catch {
    return null;
  }
  const jump = String(data?.items?.[0]?.jp || "");
  if (!jump) return null;
  try {
    const url = new URL(jump, "https://qun.qq.com/");
    const messageSeq = url.searchParams.get("msgSeq") || url.searchParams.get("msgseq") || "";
    const groupId = url.searchParams.get("groupCode") || url.searchParams.get("groupcode") || "";
    return messageSeq && groupId ? { messageSeq, groupId } : null;
  } catch {
    return null;
  }
}

export function parseGroupInviteArk(message, selfUin = "") {
  if (Number(message?.msgType || 0) !== 11) return null;
  const ark = Array.from(message?.elements || []).find((element) => element?.arkElement)?.arkElement;
  if (!ark?.bytesData) return null;
  try {
    const data = typeof ark.bytesData === "string" ? JSON.parse(ark.bytesData) : ark.bytesData;
    const jump = String(data?.meta?.news?.jumpUrl || "");
    if (!jump) return null;
    const url = new URL(jump, "https://qun.qq.com/");
    const groupId = url.searchParams.get("groupcode") || url.searchParams.get("groupCode") || "";
    const receiverUin = url.searchParams.get("receiveruin") || url.searchParams.get("receiverUin") || "";
    const flag = url.searchParams.get("msgseq") || url.searchParams.get("msgSeq") || "";
    const inviterUid = String(message?.senderUid || "");
    if (!groupId || !flag || !inviterUid || (selfUin && receiverUin !== String(selfUin))) return null;
    return { groupId, inviterUid, receiverUin, flag };
  } catch {
    return null;
  }
}

export function isThirdPartyGroupIncreaseGrayTip(jsonValue) {
  let data;
  try {
    data = typeof jsonValue === "string" ? JSON.parse(jsonValue) : jsonValue;
  } catch {
    return false;
  }
  const items = Array.from(data?.items || []);
  return items.length === 1 && String(items[0]?.txt || "").endsWith("加入群");
}
