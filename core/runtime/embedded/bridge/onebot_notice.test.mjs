import assert from "node:assert/strict";
import test from "node:test";

import {
  decodeNapCatSystemNotice,
  findGroupIncreaseCandidate,
  groupIncreaseCandidateFromNotify,
  isThirdPartyGroupIncreaseGrayTip,
  parseEmojiLikeGrayTip,
  parseGroupReactionPacket,
  parseGroupInviteArk,
} from "./onebot_notice.mjs";

function varint(value) {
  let remaining = BigInt(value);
  const bytes = [];
  do {
    let byte = Number(remaining & 0x7fn);
    remaining >>= 7n;
    if (remaining) byte |= 0x80;
    bytes.push(byte);
  } while (remaining);
  return Buffer.from(bytes);
}

function intField(number, value) {
  return Buffer.concat([varint(BigInt(number) << 3n), varint(value)]);
}

function bytesField(number, value) {
  const body = Buffer.isBuffer(value) ? value : Buffer.from(String(value));
  return Buffer.concat([varint((BigInt(number) << 3n) | 2n), varint(body.length), body]);
}

function systemPush(type, content, { subType = 0, c2cCmd = 0, peerId = 0 } = {}) {
  const response = intField(1, peerId);
  const head = Buffer.concat([intField(1, type), intField(2, subType), intField(3, c2cCmd)]);
  const body = bytesField(2, content);
  return Buffer.concat([bytesField(1, response), bytesField(2, head), bytesField(3, body)]);
}

function groupNotify(overrides = {}) {
  return {
    seq: "1787608205000000",
    type: 7,
    status: 2,
    group: { groupCode: "1105225787" },
    user1: { uid: "u_new_member" },
    user2: { uid: "u_fallback_operator" },
    actionUser: { uid: "u_admin" },
    ...overrides,
  };
}

test("extracts the joined member from an accepted QQNT group notice", () => {
  assert.deepEqual(groupIncreaseCandidateFromNotify(groupNotify(), 1000), {
    groupId: "1105225787",
    memberUid: "u_new_member",
    operatorUid: "u_admin",
    type: 7,
    observedAt: 1000,
    seq: "1787608205000000",
  });
});

test("does not treat pending or unrelated group notices as joined members", () => {
  assert.equal(groupIncreaseCandidateFromNotify(groupNotify({ status: 1 })), null);
  assert.equal(groupIncreaseCandidateFromNotify(groupNotify({ type: 8 })), null);
});

test("matches a missing member UID by group and operator", () => {
  const candidates = [
    groupIncreaseCandidateFromNotify(groupNotify(), 9000),
    groupIncreaseCandidateFromNotify(groupNotify({
      group: { groupCode: "2200000000" },
      user1: { uid: "u_other_member" },
    }), 9000),
  ];
  assert.equal(
    findGroupIncreaseCandidate(candidates, "1105225787", "u_admin", 10000)?.memberUid,
    "u_new_member",
  );
});

test("rejects ambiguous or expired group increase candidates", () => {
  const first = groupIncreaseCandidateFromNotify(groupNotify(), 1000);
  const second = groupIncreaseCandidateFromNotify(groupNotify({
    user1: { uid: "u_second_member" },
  }), 1000);
  assert.equal(findGroupIncreaseCandidate([first, second], "1105225787", "u_admin", 1500), null);
  assert.equal(findGroupIncreaseCandidate([first], "1105225787", "u_admin", 12000), null);
});

test("decodes NapCat group increase, admin and invite system pushes", () => {
  const increase = Buffer.concat([
    intField(1, 1105225787), bytesField(3, "u_member"), intField(4, 131), bytesField(5, "u_admin"),
  ]);
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(33, increase)), {
    post_type: "notice", notice_type: "group_increase", group_id: 1105225787,
    member_uid: "u_member", operator_uid: "u_admin", sub_type: "invite",
  });

  const adminBody = bytesField(2, bytesField(1, "u_member"));
  const admin = Buffer.concat([intField(1, 1105225787), bytesField(4, adminBody)]);
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(44, admin)), {
    post_type: "notice", notice_type: "group_admin", group_id: 1105225787,
    member_uid: "u_member", sub_type: "set",
  });

  const invite = Buffer.concat([intField(1, 1105225787), bytesField(5, "u_inviter")]);
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(87, invite)), {
    post_type: "request", request_type: "group", sub_type: "invite",
    group_id: 1105225787, inviter_uid: "u_inviter",
  });
});

test("decodes every NapCat group-decrease subtype and nested operator", () => {
  const expected = new Map([[130, "leave"], [131, "kick"], [3, "kick_me"], [129, "disband"]]);
  for (const [type, subType] of expected) {
    const operator = type === 3 ? bytesField(1, bytesField(1, "u_admin")) : Buffer.from("u_admin");
    const change = Buffer.concat([
      intField(1, 1105225787), bytesField(3, "u_member"), intField(4, type), bytesField(5, operator),
    ]);
    assert.deepEqual(decodeNapCatSystemNotice(systemPush(34, change)), {
      post_type: "notice", notice_type: "group_decrease", group_id: 1105225787,
      member_uid: "u_member", operator_uid: "u_admin", sub_type: subType,
    });
  }
});

test("decodes profile-like and online-file system pushes", () => {
  const detail = Buffer.concat([
    bytesField(1, "赞了您3次"), intField(3, 2218872014), bytesField(5, "tester"),
  ]);
  const likeMessage = Buffer.concat([intField(2, 1787608205), bytesField(3, detail)]);
  const likeContent = Buffer.concat([
    intField(1, 0), intField(2, 203), bytesField(203, bytesField(14, likeMessage)),
  ]);
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(528, likeContent, { subType: 39 })), {
    post_type: "notice", notice_type: "notify", sub_type: "profile_like",
    operator_id: 2218872014, operator_nick: "tester", times: 3, time: 1787608205,
  });

  const canceled = Buffer.alloc(18);
  canceled[15] = 101;
  canceled[17] = 225;
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(166, canceled, { c2cCmd: 133, peerId: 2218872014 })), {
    post_type: "notice", notice_type: "online_file_receive", sub_type: "cancel", peer_id: 2218872014,
  });
  const refused = Buffer.from(canceled);
  refused[15] = 136;
  refused[17] = 230;
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(166, refused, { c2cCmd: 133, peerId: 2218872014 })), {
    post_type: "notice", notice_type: "online_file_send", sub_type: "refuse", peer_id: 2218872014,
  });
  assert.deepEqual(decodeNapCatSystemNotice(systemPush(166, Buffer.from([101]), { c2cCmd: 131, peerId: 2218872014 })), {
    post_type: "notice", notice_type: "online_file_send", sub_type: "receive", peer_id: 2218872014,
  });
});

test("extracts the actionable flag from a QQNT group invite Ark", () => {
  const message = {
    msgType: 11,
    senderUid: "u_inviter",
    elements: [{ arkElement: { bytesData: JSON.stringify({
      meta: { news: { jumpUrl: "https://example.test/?groupcode=1105225787&receiveruin=3412574108&msgseq=123456" } },
    }) } }],
  };
  assert.deepEqual(parseGroupInviteArk(message, "3412574108"), {
    groupId: "1105225787", inviterUid: "u_inviter", receiverUin: "3412574108", flag: "123456",
  });
  assert.equal(parseGroupInviteArk(message, "999"), null);
});

test("recognizes only NapCat's third-party group increase gray tip shape", () => {
  assert.equal(isThirdPartyGroupIncreaseGrayTip({ items: [{ txt: "用户通过王者荣耀加入群" }] }), true);
  assert.equal(isThirdPartyGroupIncreaseGrayTip({ items: [{ txt: "用户加入群" }, { txt: "extra" }] }), false);
});

test("normalizes a gray-tip emoji reaction as an add event", () => {
  const content = '<qq jp="2218872014"/><url msgseq="456789"/><face id="66"/>';
  assert.deepEqual(parseEmojiLikeGrayTip(content), {
    senderUin: "2218872014", messageSeq: "456789", emojiId: "66", count: 1, isAdd: true,
  });
});

function groupReactionPacket({ type = 1, count = 3 } = {}) {
  const target = intField(1, 456789);
  const content = Buffer.concat([
    bytesField(1, "66"), intField(3, count), bytesField(4, "u_operator"), intField(5, type),
  ]);
  const reactionData = bytesField(1, bytesField(1, Buffer.concat([
    bytesField(2, target), bytesField(3, content),
  ])));
  const notify = Buffer.concat([
    intField(4, 1105225787), intField(13, 35), bytesField(44, reactionData),
  ]);
  const head = Buffer.concat([intField(1, 732), intField(2, 16)]);
  const body = bytesField(2, Buffer.concat([Buffer.alloc(7), notify]));
  return bytesField(1, Buffer.concat([bytesField(2, head), bytesField(3, body)]));
}

test("decodes NapCat group-reaction add and remove packets", () => {
  assert.deepEqual(parseGroupReactionPacket(groupReactionPacket()), {
    groupId: "1105225787", operatorUid: "u_operator", messageSeq: "456789",
    emojiId: "66", count: 3, isAdd: true,
  });
  assert.deepEqual(parseGroupReactionPacket(groupReactionPacket({ type: 2, count: 1 }).toString("hex")), {
    groupId: "1105225787", operatorUid: "u_operator", messageSeq: "456789",
    emojiId: "66", count: 1, isAdd: false,
  });
  assert.equal(parseGroupReactionPacket(bytesField(1, bytesField(2, intField(1, 1)))), null);
});
