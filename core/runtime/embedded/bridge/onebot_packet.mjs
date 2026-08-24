import { OneBotActionError, checkNativeResult } from "./onebot_action_contract.mjs";
import { asOneBotBoolean } from "./onebot_message.mjs";

function encodeVarint(value) {
  let remaining = BigInt(value);
  if (remaining < 0n) remaining = BigInt.asUintN(64, remaining);
  const bytes = [];
  do {
    let byte = Number(remaining & 0x7fn);
    remaining >>= 7n;
    if (remaining) byte |= 0x80;
    bytes.push(byte);
  } while (remaining);
  return Buffer.from(bytes);
}

function varintField(fieldNumber, value) {
  return Buffer.concat([
    encodeVarint(BigInt(fieldNumber) << 3n),
    encodeVarint(value),
  ]);
}

function bytesField(fieldNumber, value) {
  const bytes = Buffer.from(value);
  return Buffer.concat([
    encodeVarint((BigInt(fieldNumber) << 3n) | 2n),
    encodeVarint(bytes.length),
    bytes,
  ]);
}

function stringField(fieldNumber, value) {
  return bytesField(fieldNumber, Buffer.from(String(value), "utf8"));
}

export function buildGroupSpecialTitlePacket(groupId, uid, title = "") {
  if (!/^\d+$/.test(String(groupId)) || !String(uid)) {
    throw new OneBotActionError("群号或成员 UID 无效", 1400, "set_group_special_title");
  }
  const memberBody = Buffer.concat([
    stringField(1, uid),
    stringField(5, title),
    varintField(6, -1),
    stringField(7, title),
  ]);
  const requestBody = Buffer.concat([
    varintField(1, BigInt(groupId)),
    bytesField(3, memberBody),
  ]);
  return {
    cmd: "OidbSvcTrpcTcp.0x8FC_2",
    data: Buffer.concat([
      varintField(1, 0x8FC),
      varintField(2, 2),
      bytesField(4, requestBody),
      varintField(12, 0),
    ]),
  };
}

export function normalizePacketRequest(params = {}) {
  const cmd = String(params.cmd || "").trim();
  const hex = String(params.data || "").replace(/\s+/g, "");
  if (!cmd || !hex || !/^(?:[0-9a-fA-F]{2})+$/.test(hex)) {
    throw new OneBotActionError("发包参数 cmd/data 无效", 1400, "send_packet");
  }
  return { cmd, data: Buffer.from(hex, "hex"), rsp: asOneBotBoolean(params.rsp, true) };
}

function bytesLike(value) {
  if (!value || typeof value !== "object") return null;
  try {
    if (Buffer.isBuffer(value)) return Buffer.from(value);
    if (ArrayBuffer.isView(value)) {
      return Buffer.from(value.buffer, value.byteOffset, value.byteLength);
    }
    const objectTag = Object.prototype.toString.call(value);
    if (objectTag === "[object ArrayBuffer]" || objectTag === "[object SharedArrayBuffer]") {
      return Buffer.from(value);
    }
    if (value.type === "Buffer" && Array.isArray(value.data)) {
      return Buffer.from(value.data);
    }
    if (Array.isArray(value) && value.every((item) => Number.isInteger(item) && item >= 0 && item <= 255)) {
      return Buffer.from(value);
    }
    if (Number.isInteger(value.length) && value.length >= 0 && value.length <= 32 * 1024 * 1024) {
      const data = Array.from({ length: value.length }, (_, index) => value[index]);
      if (data.every((item) => Number.isInteger(item) && item >= 0 && item <= 255)) {
        return Buffer.from(data);
      }
    }
  } catch {
  }
  return null;
}

function responseBytes(result, depth = 0) {
  const direct = bytesLike(result);
  if (direct) return direct;
  if (!result || typeof result !== "object" || depth >= 4) return null;
  for (const key of ["rspbuffer", "rspBuffer", "rsp", "data", "body", "payload", "buffer", "response"]) {
    if (!(key in result)) continue;
    const found = responseBytes(result[key], depth + 1);
    if (found) return found;
  }
  return null;
}

function responseHex(result, depth = 0) {
  if (typeof result === "string") {
    const value = result.trim().replace(/^0x/i, "");
    return /^(?:[0-9a-fA-F]{2})+$/.test(value) ? value : null;
  }
  if (!result || typeof result !== "object" || depth >= 4) return null;
  for (const key of ["rspbuffer", "rspBuffer", "rsp", "data", "body", "payload", "buffer", "response"]) {
    if (!(key in result)) continue;
    const found = responseHex(result[key], depth + 1);
    if (found !== null) return found;
  }
  return null;
}

/** Normalize QQNT's native packet result to NapCat's send_packet contract. */
export function normalizePacketResponse(result, waitForResponse = true) {
  checkNativeResult(result, "发送原始数据包失败");
  if (!waitForResponse || result === undefined || result === null) return undefined;

  const bytes = responseBytes(result);
  if (bytes?.length) return bytes.toString("hex");
  const hex = responseHex(result);
  if (hex) return hex;
  if (bytes || hex === "") {
    throw new OneBotActionError("原始发包响应正文为空", 1500, "send_packet");
  }
  throw new OneBotActionError("原始发包未返回可识别的响应正文", 1500, "send_packet");
}
