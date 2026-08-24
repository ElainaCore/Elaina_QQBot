import assert from "node:assert/strict";
import test from "node:test";

import { findAddedGroupMember, normalizeNativeMemberListCallback } from "./onebot_data.mjs";

test("normalizes current QQNT member-list callback payload", () => {
  const infos = new Map([["u_member", { uid: "u_member", uin: "123456" }]]);
  const payload = { sceneId: "1105225787", ids: ["u_member"], infos, hasPrev: false, hasNext: false };
  assert.deepEqual(normalizeNativeMemberListCallback([payload]), {
    groupId: "1105225787",
    infos,
    payload,
  });
});

test("keeps compatibility with legacy member-list callback arguments", () => {
  const members = [{ uid: "u_member", uin: "123456" }];
  assert.deepEqual(normalizeNativeMemberListCallback(["1105225787", members]), {
    groupId: "1105225787",
    infos: members,
    payload: null,
  });
});

test("prefers an explicit group id over a QQNT member-list scene id", () => {
  const infos = new Map([["u_member", { uid: "u_member", uin: "123456" }]]);
  const payload = {
    sceneId: "temporary-scene", groupCode: "1105225787", infos,
    hasPrev: false, hasNext: false,
  };
  assert.equal(normalizeNativeMemberListCallback([payload]).groupId, "1105225787");
});

test("finds one new member across UID and UIN snapshot identities", () => {
  const previous = new Map([
    ["u_existing", { uid: "u_existing", uin: "10001" }],
  ]);
  const current = new Map([
    ["legacy-key", { uid: "u_existing", uin: "10001" }],
    ["u_new", { uid: "u_new", uin: "10002" }],
  ]);
  assert.deepEqual(findAddedGroupMember(previous, current), { uid: "u_new", uin: "10002" });
  current.set("u_other", { uid: "u_other", uin: "10003" });
  assert.equal(findAddedGroupMember(previous, current), null);
});
