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

function responseBytes(result) {
  if (Buffer.isBuffer(result) || result instanceof Uint8Array) return Buffer.from(result);
  if (!result || typeof result !== "object") return null;
  for (const value of [result.rspbuffer, result.rspBuffer, result.rsp, result.data, result.body, result.payload, result.buffer]) {
    if (Buffer.isBuffer(value) || value instanceof Uint8Array) return Buffer.from(value);
    if (value?.type === "Buffer" && Array.isArray(value.data)) return Buffer.from(value.data);
  }
  return null;
}

/** Normalize QQNT's native packet result to NapCat's send_packet contract. */
export function normalizePacketResponse(result, waitForResponse = true) {
  checkNativeResult(result, "发送原始数据包失败");
  if (!waitForResponse || result === undefined || result === null) return undefined;

  const bytes = responseBytes(result);
  if (bytes) return bytes.toString("hex");
  if (typeof result === "string") return result;
  if (result && typeof result === "object") {
    const value = [result.rsp, result.data].find((item) => typeof item === "string");
    return value || undefined;
  }
  return undefined;
}
