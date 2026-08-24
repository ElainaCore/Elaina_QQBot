const AT_TYPE_UNKNOWN = 0;
const AT_TYPE_ALL = 1;

export function asOneBotBoolean(value, fallback = false) {
  if (value === undefined || value === null) return fallback;
  if (typeof value === "string") {
    return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
  }
  return Boolean(value);
}

function decodeCq(value) {
  return String(value).replace(/&#44;/g, ",").replace(/&#91;/g, "[").replace(/&#93;/g, "]").replace(/&amp;/g, "&");
}

function normalizeSegment(segment) {
  if (!segment || typeof segment !== "object") {
    return segment === undefined || segment === null
      ? null
      : { type: "text", data: { text: String(segment) } };
  }
  let type = String(segment.type || "").trim().toLowerCase();
  if (!type) return null;
  if (type === "voice" || type === "audio") type = "record";
  const data = segment.data && typeof segment.data === "object" && !Array.isArray(segment.data)
    ? { ...segment.data }
    : {};
  return { type, data };
}

/** Canonical OneBot array message shared by every embedded send action. */
export function normalizeOneBotMessage(message, autoEscape = false) {
  if (Array.isArray(message)) return message.map(normalizeSegment).filter(Boolean);
  if (message && typeof message === "object") {
    const segment = normalizeSegment(message);
    return segment ? [segment] : [];
  }
  const value = String(message ?? "");
  if (asOneBotBoolean(autoEscape) || !value.includes("[CQ:")) {
    return [{ type: "text", data: { text: value } }];
  }
  const result = [];
  const pattern = /\[CQ:([A-Za-z0-9_]+)((?:,[^\]]*)?)\]/g;
  let offset = 0;
  let match;
  while ((match = pattern.exec(value)) !== null) {
    if (match.index > offset) {
      result.push({ type: "text", data: { text: decodeCq(value.slice(offset, match.index)) } });
    }
    const data = {};
    for (const item of String(match[2] || "").replace(/^,/, "").split(",")) {
      if (!item) continue;
      const separator = item.indexOf("=");
      const key = separator < 0 ? item : item.slice(0, separator);
      data[key] = decodeCq(separator < 0 ? "" : item.slice(separator + 1));
    }
    const segment = normalizeSegment({ type: match[1], data });
    if (segment) result.push(segment);
    offset = pattern.lastIndex;
  }
  if (offset < value.length) result.push({ type: "text", data: { text: decodeCq(value.slice(offset)) } });
  return result.length ? result : [{ type: "text", data: { text: value } }];
}

function uint32Uin(value) {
  const text = String(value ?? "").trim();
  if (!text || text === "0") return "";
  const numeric = Number(text);
  if (!Number.isInteger(numeric)) return "";
  return String(numeric >>> 0);
}

/** Convert a QQNT text element to the same OneBot segment shape used by NapCat. */
export async function oneBotTextSegment(textElement, resolveUin) {
  const content = String(textElement?.content || "");
  const atType = Number(textElement?.atType || AT_TYPE_UNKNOWN);
  if (atType === AT_TYPE_UNKNOWN) {
    return content ? { type: "text", data: { text: content } } : null;
  }
  if (atType === AT_TYPE_ALL) {
    return { type: "at", data: { qq: "all", name: content.replace(/^@/, "") } };
  }

  let qq = uint32Uin(textElement?.atUid);
  const ntUid = String(textElement?.atNtUid || "").trim();
  if (!qq && ntUid && typeof resolveUin === "function") {
    const converted = String(await resolveUin(ntUid) || "").trim();
    if (/^[1-9]\d*$/.test(converted)) qq = converted;
  }
  if (!qq) qq = uint32Uin(textElement?.atTinyId);

  return {
    type: "at",
    data: { qq, name: content.replace(/^@/, "") },
  };
}

export { uint32Uin };
