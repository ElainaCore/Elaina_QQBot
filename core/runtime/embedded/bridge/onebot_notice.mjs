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
  return senderUin && messageSeq && emojiId ? { senderUin, messageSeq, emojiId } : null;
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
