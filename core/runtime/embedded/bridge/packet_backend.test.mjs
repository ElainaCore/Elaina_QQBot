import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { NativePacketBackend } from "./packet_backend.mjs";

test("loads bypass before installing the packet hook", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "elaina-packet-"));
  const nativePath = path.join(directory, "napi2native.node");
  const offsetsPath = path.join(directory, "napi2native.json");
  fs.writeFileSync(nativePath, "test");
  fs.writeFileSync(offsetsPath, JSON.stringify({
    [`test-version-${process.arch}`]: { send: "SEND", recv: "RECV" },
  }));

  const calls = [];
  const originalDlopen = process.dlopen;
  process.dlopen = (module) => {
    module.exports = {
      enableAllBypasses(options) {
        calls.push(["bypass", options]);
        return true;
      },
      initHook(send, recv) {
        calls.push(["hook", send, recv]);
        return true;
      },
    };
  };

  try {
    const backend = new NativePacketBackend({
      version: "test-version",
      nativePath,
      offsetsPath,
    });
    assert.equal(backend.load(), true);
    assert.equal(backend.status().loaded, true);
    assert.equal(backend.status().bypass_enabled, true);
    assert.equal(backend.status().hook_initialized, false);
    assert.equal(backend.load(), true);
    assert.equal(calls.length, 1);
    assert.equal(backend.initHook(), true);
    assert.equal(backend.status().hook_initialized, true);
    assert.deepEqual(calls.map((item) => item[0]), ["bypass", "hook"]);
    assert.deepEqual(calls[1], ["hook", "SEND", "RECV"]);
  } finally {
    process.dlopen = originalDlopen;
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
