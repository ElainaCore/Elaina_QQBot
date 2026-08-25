export const DEFAULT_PACKET_BYPASS = Object.freeze({
  hook: false,
  window: false,
  module: false,
  process: false,
  container: false,
  js: false,
});

export function packetBoolean(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  const normalized = String(value ?? "").trim().toLowerCase();
  if (["1", "true", "yes", "on", "enable", "enabled"].includes(normalized)) return true;
  if (["0", "false", "no", "off", "disable", "disabled"].includes(normalized)) return false;
  return fallback;
}

export function normalizePacketBypass(value = {}) {
  let source = value;
  if (typeof source === "string") {
    try {
      source = JSON.parse(source);
    } catch {
      source = {};
    }
  }
  if (!source || typeof source !== "object" || Array.isArray(source)) source = {};
  return Object.fromEntries(
    Object.keys(DEFAULT_PACKET_BYPASS).map((key) => [
      key,
      packetBoolean(source[key], DEFAULT_PACKET_BYPASS[key]),
    ]),
  );
}

export function readPacketRuntimeOptions(env = process.env) {
  return {
    mode: String(env.ELAINAQQ_PACKET_BACKEND || "auto"),
    verbose: packetBoolean(env.ELAINAQQ_PACKET_VERBOSE, false),
    o3HookMode: packetBoolean(env.ELAINAQQ_PACKET_O3_HOOK, false),
    bypassOptions: normalizePacketBypass(env.ELAINAQQ_PACKET_BYPASS),
  };
}
