import assert from "node:assert/strict";
import test from "node:test";

import { NativePacketEventBackend } from "./packet_event_backend.mjs";

test("packet event backend disables cleanly without touching native hooks", () => {
  const backend = new NativePacketEventBackend({ version: "3.2.32-52194", mode: "off" });
  assert.equal(backend.init(), false);
  assert.deepEqual(backend.status(), {
    enabled: false, available: false, loaded: false, backend: "moehoo",
    version: "3.2.32-52194", arch: process.arch, offsets: null,
    reason: "配置已禁用原始包事件后端",
  });
});

test("packet event backend reports a missing native module without throwing", () => {
  const backend = new NativePacketEventBackend({
    version: "3.2.32-52194",
    nativePath: "this-file-does-not-exist.node",
  });
  assert.equal(backend.init(), false);
  assert.match(backend.status().reason, /未找到 MoeHoo/);
});
