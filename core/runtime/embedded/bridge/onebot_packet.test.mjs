import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";

import { normalizePacketResponse, normalizePacketRequest } from "./onebot_packet.mjs";

test("normalizes OneBot packet request to bytes", () => {
  const request = normalizePacketRequest({ cmd: "Test.Cmd", data: "0801", rsp: true });
  assert.equal(request.cmd, "Test.Cmd");
  assert.deepEqual(Array.from(request.data), [8, 1]);
  assert.equal(request.rsp, true);
});

test("keeps QQNT cross-realm response bytes", () => {
  const rspbuffer = vm.runInNewContext("new Uint8Array([8, 1, 18, 2, 111, 107])");
  assert.equal(normalizePacketResponse({ rspbuffer }), "080112026f6b");
});

test("accepts serialized and nested response buffers", () => {
  assert.equal(normalizePacketResponse({
    response: { data: { type: "Buffer", data: [8, 1] } },
  }), "0801");
});

test("rejects an empty response instead of returning fake success", () => {
  assert.throws(
    () => normalizePacketResponse({ rspbuffer: Buffer.alloc(0) }),
    /响应正文为空/,
  );
});

test("preserves QQNT packet decode errors", () => {
  assert.throws(
    () => normalizePacketResponse({
      result: 1,
      errMsg: "request body decode failed",
      rsp: "",
    }),
    /request body decode failed/,
  );
});
