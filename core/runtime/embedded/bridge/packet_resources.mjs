import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const NATIVE_ROOT = fileURLToPath(new URL("../native/", import.meta.url));
const SUPPORTED_PLATFORMS = new Set([
  "win32.x64",
  "linux.x64",
  "linux.arm64",
  "darwin.arm64",
]);
const RESOURCE_LAYOUT = Object.freeze({
  sender: Object.freeze({
    directory: "packet",
    nativePrefix: "packet_sender",
    offsetsFile: "packet_offsets.json",
  }),
  events: Object.freeze({
    directory: "events",
    nativePrefix: "packet_events",
    offsetsFile: "event_offsets.json",
  }),
});
const OFFSET_TABLES = new Map();

export function currentPacketPlatform() {
  return process.platform + "." + process.arch;
}

export function packetResource(kind, platform = currentPacketPlatform()) {
  const layout = RESOURCE_LAYOUT[kind];
  if (!layout) throw new TypeError("未知的原始包资源类型: " + kind);
  const directory = path.join(NATIVE_ROOT, layout.directory);
  return {
    kind,
    platform,
    supported: SUPPORTED_PLATFORMS.has(platform),
    nativePath: path.join(directory, layout.nativePrefix + "." + platform + ".node"),
    offsetsPath: path.join(directory, layout.offsetsFile),
  };
}

export function readPacketOffsets(resource, version, arch = process.arch) {
  let table = OFFSET_TABLES.get(resource.offsetsPath);
  if (!table) {
    table = JSON.parse(fs.readFileSync(resource.offsetsPath, "utf8"));
    OFFSET_TABLES.set(resource.offsetsPath, table);
  }
  const key = String(version || "") + "-" + arch;
  return { key, offsets: table?.[key] };
}

export function clearPacketOffsetCache() {
  OFFSET_TABLES.clear();
}
