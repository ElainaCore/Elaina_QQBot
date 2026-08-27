import assert from "node:assert/strict";
import test from "node:test";

process.env.ELAINAQQ_WORKER_TEST = "1";

const { QQInstance } = await import("../core/runtime/embedded/bridge/qq_runtime.mjs");

function createInstance(messageService = {}) {
  const instance = new QQInstance(
    { id: "onebot-test", uin: "10000" },
    { version: "test" },
    {},
    "",
  );
  instance.selfInfo = { uin: "10000", uid: "self-uid", nick: "Elaina" };
  instance.session = { getMsgService: () => messageService };
  return instance;
}

function quotedImageMessage() {
  return {
    chatType: 2,
    peerUid: "20000",
    peerUin: "20000",
    msgId: "quoted-native-message",
    msgSeq: "42",
    msgTime: "1700000000",
    senderUin: "30000",
    senderUid: "quoted-sender-uid",
    sendNickName: "quoted sender",
    elements: [{
      elementId: "quoted-image-element",
      picElement: {
        fileName: "quoted.jpg",
        fileSize: 1234,
        md5HexStr: "0123456789abcdef0123456789abcdef",
      },
    }],
  };
}

function replyMessage(target) {
  return {
    chatType: 2,
    peerUid: target.peerUid,
    peerUin: target.peerUin,
    msgId: "reply-native-message",
    msgSeq: "43",
    msgTime: "1700000001",
    senderUin: "40000",
    senderUid: "reply-sender-uid",
    elements: [{
      elementId: "reply-element",
      replyElement: {
        sourceMsgIdInRecords: target.msgId,
        replayMsgId: target.msgId,
        replayMsgSeq: target.msgSeq,
        replyMsgClientSeq: target.msgSeq,
        replyMsgTime: target.msgTime,
        senderUin: target.senderUin,
        senderUidStr: target.senderUid,
      },
    }],
    records: [target],
  };
}

test("quoted image is returned by get_msg through the OneBot reply id", async () => {
  const target = quotedImageMessage();
  const service = {
    getMsgsBySeqAndCount: async () => ({ msgList: [target] }),
  };
  const instance = createInstance(service);
  const current = replyMessage(target);

  const event = await instance.toOneBotEvent(current);
  const reply = event.message.find((segment) => segment.type === "reply");
  assert.ok(reply?.data?.id, "the incoming event must contain a OneBot reply id");

  await instance.rememberReplyTargets(current);
  const result = await instance.getOneBotMessage(reply.data.id);
  const images = result.message.filter((segment) => segment.type === "image");

  assert.equal(images.length, 1);
  assert.equal(images[0].data.file, "quoted.jpg");
  assert.equal(
    images[0].data.url,
    "https://gchat.qpic.cn/gchatpic_new/0/0-0-0123456789ABCDEF0123456789ABCDEF/0",
  );
});

test("current image and quoted image remain two distinct OneBot image segments", async () => {
  const target = quotedImageMessage();
  const current = replyMessage(target);
  current.elements.push({
    elementId: "current-image-element",
    picElement: {
      fileName: "current.jpg",
      fileSize: 4321,
      md5HexStr: "fedcba9876543210fedcba9876543210",
    },
  });
  const instance = createInstance({
    getMsgsBySeqAndCount: async () => ({ msgList: [target] }),
  });

  const event = await instance.toOneBotEvent(current);
  const images = event.message.filter((segment) => segment.type === "image");

  assert.equal(images.length, 1, "the event itself contains only its current image");
  await instance.rememberReplyTargets(current);
  const reply = event.message.find((segment) => segment.type === "reply");
  const quoted = await instance.getOneBotMessage(reply.data.id);
  const combined = [
    ...quoted.message.filter((segment) => segment.type === "image"),
    ...images,
  ];

  assert.equal(combined.length, 2);
  assert.deepEqual(combined.map((segment) => segment.data.file).sort(), ["current.jpg", "quoted.jpg"]);
});

test("failed reply lookup keeps context without caching an empty message", async () => {
  const target = quotedImageMessage();
  const current = replyMessage(target);
  current.records = [];
  const instance = createInstance({
    getMsgsBySeqAndCount: async () => ({ msgList: [] }),
  });
  const event = await instance.toOneBotEvent(current);
  const replyId = String(event.message.find((segment) => segment.type === "reply").data.id);

  await instance.rememberReplyTargets(current);

  assert.equal(instance.oneBotMessages.has(replyId), false);
  assert.equal(instance.oneBotReplyTargets.has(replyId), true);
});

test("NT image file ids use NapCat dynamic rkey download urls", async () => {
  const instance = createInstance();
  instance.fetchOneBotImageRkeys = async () => ({ private: "private-key", group: "group-key" });

  const url = new URL(await instance.incomingImageUrl({
    originImageUrl: "/download?appid=1407&fileid=group-file",
  }));

  assert.equal(url.origin, "https://multimedia.nt.qq.com.cn");
  assert.equal(url.searchParams.get("appid"), "1407");
  assert.equal(url.searchParams.get("fileid"), "group-file");
  assert.equal(url.searchParams.get("rkey"), "group-key");
  assert.equal(url.searchParams.has("spec"), false);
});
