import https from 'https';
import { createHash, randomUUID } from 'crypto';
import fs from 'fs';
import path from 'path';
import os from 'os';
import {
  BuddyListener,
  GlobalAdapter,
  GroupListener,
  LoginListener,
  MessageListener,
  O3MiscListener,
  SessionDependsAdapter,
  SessionDispatcherAdapter,
  SessionListener
} from './session_adapters.mjs';
import { IncomingMessageGate } from './message_gate.mjs';
import { extractInlineKeyboardButtons } from './inline_keyboard.mjs';
import { nativeMessageKey, resolveReplyReference, toOneBotMessageId } from './message_identity.mjs';
import { asOneBotBoolean, encodeOneBotCqMessage, normalizeOneBotMessage, oneBotTextSegment } from './onebot_message.mjs';
import { createHeartbeatEvent, createLifecycleEvent, createOneBotEvent } from './onebot_event.mjs';
import {
  decodeSystemNotice,
  findGroupIncreaseCandidate,
  groupIncreaseCandidateFromNotify,
  isThirdPartyGroupIncreaseGrayTip,
  parseEmojiLikeGrayTip,
  parseEssenceGrayTip,
  parseGroupReactionPacket,
  parseGroupInviteArk,
} from './onebot_notice.mjs';
import { PacketRuntime } from './packet_runtime.mjs';
import { EmbeddedManagerChannel } from './manager_channel.mjs';
import { findQQPath, getDataPaths, getQQInfo, loadWrapper } from './qq_platform.mjs';
import {
  collectionValues,
  extractNativeGroupDetail,
  extractNativeGroupList,
  extractNativeMemberMap,
  findAddedGroupMember,
  groupAddOptionRequest,
  groupManagementRequests,
  groupRobotOptionRequest,
  groupSearchRequest,
  oneBotFriend,
  oneBotGroup,
  oneBotGroupMember,
  normalizeNativeMemberListCallback,
} from './onebot_data.mjs';
import {
  ONEBOT_ACTIONS,
  OneBotActionError,
  assertKnownOneBotAction,
  checkNativeResult,
  normalizeOneBotAction,
  requireNativeMethod
} from './onebot_action_contract.mjs';

const botUinMap = /* @__PURE__ */ new Map();
function botTag(botId) {
  return botUinMap.get(botId) || botId.slice(0, 8);
}
function log(botId, ...args) {
  console.log(`[机器人 ${botTag(botId)}]`, ...args);
}
function logErr(botId, ...args) {
  console.error(`[机器人 ${botTag(botId)}]`, ...args);
}
function safeJson(value, limit = 500) {
  try {
    const text = JSON.stringify(value, (_, item) => typeof item === "bigint" ? item.toString() : item);
    return String(text || "").substring(0, limit);
  } catch {
    return String(value);
  }
}
function stringifyJson(value) {
  const seen = new WeakSet();
  return JSON.stringify(value, (_, item) => {
    if (typeof item === "bigint") return item.toString();
    if (item instanceof Map) return Object.fromEntries(item);
    if (item instanceof Set) return Array.from(item);
    if (item instanceof Uint8Array) return Buffer.from(item).toString("base64");
    if (item && typeof item === "object") {
      if (seen.has(item)) return undefined;
      seen.add(item);
    }
    return item;
  });
}
function qrValue(value) {
  if (value === undefined || value === null) return "";
  if (Buffer.isBuffer(value)) return value.toString("base64");
  if (value instanceof Uint8Array) return Buffer.from(value).toString("base64");
  return String(value);
}
function normalizeQrData(data) {
  const value = data && typeof data === "object" ? data : {};
  const nested = value.data && typeof value.data === "object" ? value.data : {};
  const qrcodeUrl = qrValue(
    value.qrcodeUrl || value.qrCodeUrl || value.qrUrl || value.url || nested.qrcodeUrl || nested.qrCodeUrl || nested.qrUrl || nested.url
  );
  let qrcodeBase64 = qrValue(
    value.pngBase64QrcodeData || value.pngBase64 || value.qrcodeBase64 || value.qrCodeBase64 || value.base64 ||
    nested.pngBase64QrcodeData || nested.pngBase64 || nested.qrcodeBase64 || nested.qrCodeBase64 || nested.base64
  );
  qrcodeBase64 = qrcodeBase64.replace(/^data:image\/[^;]+;base64,/i, "");
  return { qrcodeUrl, qrcodeBase64 };
}
function proxied(listener, _tag) {
  return new Proxy(listener, {
    get(target, prop, receiver) {
      if (typeof target[prop] === "undefined") {
        return () => {
        };
      }
      return Reflect.get(target, prop, receiver);
    }
  });
}

class QQInstance {
  botConfig;
  qqInfo;
  wrapper;
  engine = null;
  loginService = null;
  session = null;
  startupSession = null;
  o3Service = null;
  o3Listener = null;
  globalAdapter = null;
  loginListener = null;
  sessionDependsAdapter = null;
  sessionDispatcherAdapter = null;
  sessionListener = null;
  selfInfo = null;
  msgListener = null;
  buddyListener = null;
  buddyListenerHandle = null;
  groupListener = null;
  groupListenerHandle = null;
  incomingMessageGate = null;
  incomingMessageTails = /* @__PURE__ */ new Map();
  packetRuntime = null;
  statusCallback = null;
  oneBotEventCallback = null;
  redPacketCallback = null;
  oneBotMessages = /* @__PURE__ */ new Map();
  oneBotNativeMessageIds = /* @__PURE__ */ new Map();
  oneBotRawMessages = /* @__PURE__ */ new Map();
  oneBotForwardMessages = /* @__PURE__ */ new Map();
  oneBotNoticeKeys = /* @__PURE__ */ new Map();
  oneBotGroupCards = /* @__PURE__ */ new Map();
  oneBotGroupOperators = /* @__PURE__ */ new Map();
  oneBotGroupIncreaseCandidates = /* @__PURE__ */ new Map();
  oneBotGroupInviteArks = /* @__PURE__ */ new Map();
  oneBotGroupInviteRequests = /* @__PURE__ */ new Map();
  oneBotGroupMemberSnapshots = /* @__PURE__ */ new Map();
  oneBotUidToUin = /* @__PURE__ */ new Map();
  oneBotUinPending = /* @__PURE__ */ new Map();
  oneBotGroupUinPending = /* @__PURE__ */ new Map();
  oneBotHeartbeatTimer = null;
  pendingSentMessages = /* @__PURE__ */ new Set();
  pendingNativeEvents = /* @__PURE__ */ new Map();
  forwardSendTail = Promise.resolve();
  oneBotFiles = /* @__PURE__ */ new Map();
  oneBotFileStreams = /* @__PURE__ */ new Map();
  oneBotStreamFiles = /* @__PURE__ */ new Set();
  oneBotOnlineClients = [];
  redPackets = /* @__PURE__ */ new Map();
  redPacketCleanupAt = 0;
  runtime;
  constructor(botConfig, qqInfo, wrapper, _baseDataDir) {
    this.botConfig = botConfig;
    this.qqInfo = qqInfo;
    this.wrapper = wrapper;
    this.runtime = { botId: botConfig.id, status: "offline" };
    if (botConfig.uin) botUinMap.set(botConfig.id, botConfig.uin);
  }
  setStatusCallback(cb) {
    this.statusCallback = cb;
  }
  setOneBotEventCallback(cb) {
    this.oneBotEventCallback = cb;
  }
  setRedPacketCallback(cb) {
    this.redPacketCallback = cb;
  }
  setStatus(status, extra) {
      this.runtime = { ...this.runtime, status, ...extra };
    log(this.botConfig.id, "状态变更:", status, extra ? safeJson(extra, 200) : "");
      this.statusCallback?.(this.runtime);
  }
  async start() {
    const id = this.botConfig.id;
    try {
      this.setStatus("logging_in");
      log(id, "=== 开始启动 ElainaQQ ===");
      const [dataPath, dataPathGlobal] = getDataPaths(this.wrapper);
      fs.mkdirSync(dataPathGlobal, { recursive: true });
      log(id, "dataPath:", dataPath, "dataPathGlobal:", dataPathGlobal);
      const platformType = this.getPlatformType();
      log(id, "平台:", platformType, "版本:", this.qqInfo.version, "appid:", this.qqInfo.appid, "qua:", this.qqInfo.qua);
      // 先加载原始发包模块并启用 bypass，再创建 QQ session。
      // initHook 必须等 session 初始化完成后再安装。
      this.packetRuntime = new PacketRuntime({
        version: this.qqInfo.version,
        logger: (channel, message) => log(
          id,
          channel === "events" ? "[原始包事件]" : "[原始包]",
          message,
        ),
        onMessagePush: (packet) => this.handlePacketEvent(packet),
      });
      this.packetRuntime.loadBeforeSession();
      log(id, "步骤1: 初始化 O3MiscService...");
      try {
        this.o3Service = this.wrapper.NodeIO3MiscService.get();
        this.o3Listener = new O3MiscListener();
        this.o3Service.addO3MiscListener(this.o3Listener);
        log(id, "O3MiscService 初始化成功");
      } catch (e) {
        log(id, "O3MiscService 初始化跳过:", e.message);
      }
      log(id, "步骤2: 创建 QQ session...");
      this.createSession();
      log(id, "session 创建成功");
      log(id, "步骤3: 初始化引擎...");
      this.engine = this.wrapper.NodeIQQNTWrapperEngine.get();
      this.globalAdapter = new GlobalAdapter();
      this.engine.initWithDeskTopConfig({
        base_path_prefix: "",
        platform_type: platformType,
        app_type: 4,
        app_version: this.qqInfo.version,
        os_version: os.release(),
        use_xlog: false,
        qua: this.qqInfo.qua,
        global_path_config: { desktopGlobalPath: dataPathGlobal },
        thumb_config: { maxSide: 324, minSide: 48, longLimit: 6, density: 2 }
      }, this.globalAdapter);
      log(id, "引擎初始化成功");
      log(id, "步骤4: 初始化登录服务...");
      this.loginService = this.wrapper.NodeIKernelLoginService.get();
      this.loginService.initConfig({
        machineId: "",
        appid: this.qqInfo.appid,
        platVer: os.release(),
        commonPath: dataPathGlobal,
        clientVer: this.qqInfo.version,
        hostName: os.hostname(),
        externalVersion: false
      });
      log(id, "登录服务初始化成功");
      const dataTimestamp = Date.now().toString();
      if (this.o3Service) {
        try {
          this.o3Service.reportAmgomWeather("login", "a1", [dataTimestamp, "0", "0"]);
          log(id, "amgom a1 上报成功");
        } catch (e) {
          log(id, "amgom a1 跳过:", e.message);
        }
      }
      log(id, "步骤4: 开始登录...");
      this.selfInfo = await this.doLogin();
      log(id, "登录完成:", JSON.stringify(this.selfInfo));
      if (this.o3Service) {
        try {
          const amgomHex = "eb1fd6ac257461580dc7438eb099f23aae04ca679f4d88f53072dc56e3bb1129";
          this.o3Service.setAmgomDataPiece(this.qqInfo.appid, new Uint8Array(Buffer.from(amgomHex, "hex")));
          this.o3Service.reportAmgomWeather("login", "a6", [dataTimestamp, "184", "329"]);
          log(id, "amgom a6 上报成功");
        } catch (e) {
          log(id, "amgom a6 跳过:", e.message);
        }
      }
      log(id, "步骤5: 初始化 session...");
      await this.initSession(dataPath);
      log(id, "session 初始化完成");
      this.packetRuntime.initializeAfterSession();
      log(id, "步骤6: 注册消息监听...");
      this.registerMsgListener();
      this.registerEventListeners();
      this.initializeGroupMemberSnapshots().catch((error) => {
        logErr(id, "[事件] 初始化群成员快照失败:", error?.message || error);
      });
      this.botConfig.uin = this.selfInfo.uin;
      this.botConfig.nickname = this.selfInfo.nick || this.selfInfo.uin;
      botUinMap.set(this.botConfig.id, this.selfInfo.uin);
      this.setStatus("online", {
        loginUin: this.selfInfo.uin,
        nickname: this.botConfig.nickname,
      });
      this.oneBotEventCallback?.(createLifecycleEvent(this.getSelfUin()));
      this.startOneBotHeartbeat();
      log(id, "=== 启动完成, 已上线 ===");
    } catch (e) {
      logErr(id, "=== 启动失败 ===", e.message, e.stack);
      this.setStatus("error", { error: e.message });
      throw e;
    }
  }
  createSession() {
    const id = this.botConfig.id;
    const sessionApi = this.wrapper?.NodeIQQNTWrapperSession;
    const startupApi = this.wrapper?.NodeIQQNTStartupSessionWrapper;
    const apiKeys = (value) => {
      try {
        return Object.getOwnPropertyNames(value || {}).slice(0, 32);
      } catch {
        return [];
      }
    };
    const methods = {
      sessionType: typeof sessionApi,
      create: typeof sessionApi?.create,
      get: typeof sessionApi?.get,
      getNTWrapperSession: typeof sessionApi?.getNTWrapperSession,
      newMethod: typeof sessionApi?.new,
      startupType: typeof startupApi,
      startupCreate: typeof startupApi?.create
    };
    log(id, "WrapperSession API:", JSON.stringify(methods), "sessionKeys:", JSON.stringify(apiKeys(sessionApi)), "startupKeys:", JSON.stringify(apiKeys(startupApi)));
    const errors = [];

    // 先创建 StartupSession，再取得 nt_1。
    // 部分 QQNT 版本没有可调用的 WrapperSession.create。
    if (typeof startupApi?.create === "function") {
      try {
        this.startupSession = startupApi.create();
        if (typeof sessionApi?.getNTWrapperSession === "function") {
          this.session = sessionApi.getNTWrapperSession("nt_1");
          if (this.session) {
            log(id, "session 创建成功 (StartupSession/getNTWrapperSession)");
            return this.session;
          }
        }
      } catch (error) {
        errors.push(`StartupSession: ${error?.message || error}`);
      }
    }

    if (typeof sessionApi?.getNTWrapperSession === "function") {
      try {
        this.session = sessionApi.getNTWrapperSession("nt_1");
        if (this.session) {
          log(id, "session 创建成功 (getNTWrapperSession)");
          return this.session;
        }
      } catch (error) {
        errors.push(`getNTWrapperSession: ${error?.message || error}`);
      }
    }

    if (typeof sessionApi?.get === "function") {
      try {
        this.session = sessionApi.get();
        if (this.session) {
          log(id, "session 创建成功 (WrapperSession.get)");
          return this.session;
        }
      } catch (error) {
        errors.push(`get: ${error?.message || error}`);
      }
    }

    if (typeof sessionApi?.new === "function") {
      try {
        this.session = sessionApi.new();
        if (this.session) {
          log(id, "session 创建成功 (WrapperSession.new)");
          return this.session;
        }
      } catch (error) {
        errors.push("new: " + (error?.message || error));
      }
    }

    if (typeof sessionApi?.create === "function") {
      try {
        this.session = sessionApi.create();
        if (this.session) {
          log(id, "session 创建成功 (WrapperSession.create)");
          return this.session;
        }
      } catch (error) {
        errors.push(`create: ${error?.message || error}`);
      }
    }

    if (typeof sessionApi === "function") {
      try {
        this.session = new sessionApi();
        if (this.session) {
          log(id, "session 创建成功 (WrapperSession constructor)");
          return this.session;
        }
      } catch (error) {
        errors.push("constructor: " + (error?.message || error));
      }
    }

    const detail = errors.length ? `; ${errors.join(" | ")}` : "";
    throw new Error(`QQNT 会话接口不兼容: ${JSON.stringify(methods)}${detail}`);
  }
  refreshQrCode() {
    if (!this.loginService) throw new Error("登录服务未初始化");
    this.setStatus("logging_in", { qrcodeUrl: "", qrcodeBase64: "", qrcode: "", error: "" });
    const started = this.loginService.getQRCodePicture();
    if (started === false) throw new Error("QQ 无法生成登录二维码");
    return { started: true };
  }
  async stop() {
    try {
      if (this.oneBotHeartbeatTimer) clearInterval(this.oneBotHeartbeatTimer);
      this.oneBotHeartbeatTimer = null;
      for (const pending of Array.from(this.pendingSentMessages)) {
        pending.reject(new OneBotActionError("QQ 会话已停止", 1500, "send_msg"));
      }
      for (const waiters of this.pendingNativeEvents.values()) {
        for (const pending of Array.from(waiters)) pending.reject(new OneBotActionError("QQ 会话已停止", 1500));
      }
      this.pendingNativeEvents.clear();
      if (this.session && this.msgListener) {
        try {
          this.session.getMsgService().removeKernelMsgListener(this.msgListener);
        } catch {
        }
      }
      if (this.session && this.buddyListener) {
        try {
          this.session.getBuddyService?.().removeKernelBuddyListener?.(this.buddyListenerHandle ?? this.buddyListener);
        } catch {
        }
      }
      if (this.session && this.groupListener) {
        try {
          this.session.getGroupService?.().removeKernelGroupListener?.(this.groupListenerHandle ?? this.groupListener);
        } catch {
        }
      }
      this.buddyListener = null;
      this.buddyListenerHandle = null;
      this.groupListener = null;
      this.groupListenerHandle = null;
      this.incomingMessageGate = null;
      this.incomingMessageTails.clear();
      this.oneBotGroupIncreaseCandidates.clear();
      this.oneBotGroupInviteArks.clear();
      this.oneBotGroupInviteRequests.clear();
      this.oneBotGroupMemberSnapshots.clear();
      this.oneBotUidToUin.clear();
      this.oneBotUinPending.clear();
      this.oneBotGroupUinPending.clear();
      this.packetRuntime?.close();
      this.packetRuntime = null;
      this.cleanOneBotStreams();
      if (this.startupSession && typeof this.startupSession.stop === "function") {
        try {
          this.startupSession.stop();
        } catch {
        }
      }
      this.setStatus("offline");
      log(this.botConfig.id, "已停止");
    } catch (e) {
      logErr(this.botConfig.id, "停止失败:", e.message);
    }
  }
  startOneBotHeartbeat(interval = 30000) {
    if (this.oneBotHeartbeatTimer) clearInterval(this.oneBotHeartbeatTimer);
    this.oneBotHeartbeatTimer = setInterval(() => {
      const online = this.runtime.status === "online";
      this.oneBotEventCallback?.(createHeartbeatEvent(this.getSelfUin(), interval, online, true));
    }, interval);
    this.oneBotHeartbeatTimer.unref?.();
  }
  getMsgService() {
    return this.session?.getMsgService();
  }
  getPacketStatus() {
    return this.packetRuntime?.status() || {
      enabled: false, available: false, loaded: false,
      backend: "native_packet", version: this.qqInfo.version, arch: process.arch,
      reason: "原始包运行时尚未初始化",
      sender: { enabled: false, available: false, loaded: false, reason: "原始发包后端尚未初始化" },
      events: { enabled: false, available: false, loaded: false, reason: "原始包事件后端尚未初始化" },
      event_available: false,
    };
  }
  getSelfUin() {
    return this.selfInfo?.uin || "";
  }
  getSelfNick() {
    return this.selfInfo?.nick || "";
  }
  async sendGroupMsg(groupId, text) {
    await this.sendNativeElements("group", groupId, [this.textElement(text)]);
  }
  async sendPrivateMsg(userId, text) {
    await this.sendNativeElements("private", userId, [this.textElement(text)]);
  }
  async callOneBotAction(action, params = {}) {
    action = normalizeOneBotAction(action);
    assertKnownOneBotAction(action);
    switch (action) {
      case "send_msg":
        return params.message_type === "group" || params.group_id !== void 0 ? this.sendOneBotMessage("group", String(params.group_id), params.message, params.auto_escape) : this.sendOneBotMessage("private", String(params.user_id), params.message, params.auto_escape);
      case "send_group_msg":
        return this.sendOneBotMessage("group", String(params.group_id), params.message, params.auto_escape);
      case "send_private_msg":
        return this.sendOneBotMessage("private", String(params.user_id), params.message, params.auto_escape);
      case "click_inline_keyboard_button":
        return this.clickInlineKeyboardButton(params);
      case "get_login_info":
        return { user_id: Number(this.getSelfUin()) || this.getSelfUin(), nickname: this.getSelfNick() };
      case "get_status":
        return { online: this.runtime.status === "online", good: this.runtime.status === "online", stat: {} };
      case "get_version_info":
        return {
          app_name: "ElainaQQ Embedded QQ",
          app_version: this.qqInfo.version,
          protocol_version: "v11",
        };
      case "can_send_image":
        return { yes: true };
      case "can_send_record":
        return { yes: true };
      case "get_msg":
        return this.getOneBotMessage(String(params.message_id));
      case "get_group_list":
        return this.queryGroupList(params);
      case "get_group_info":
        return this.queryGroupInfo(String(params.group_id), params);
      case "get_group_member_list":
        return this.queryGroupMemberList(String(params.group_id), params);
      case "get_group_member_info":
        return this.queryGroupMemberInfo(String(params.group_id), String(params.user_id), params);
      case "get_friend_list":
        return this.queryFriendList(params);
      case "get_stranger_info":
        return this.queryStrangerInfo(params);
      case "delete_msg":
        await this.deleteOneBotMessage(String(params.message_id));
        return null;
      case "mark_group_msg_as_read":
        await this.markOneBotMessageRead("group", String(params.group_id));
        return null;
      case "mark_private_msg_as_read":
        await this.markOneBotMessageRead("private", String(params.user_id));
        return null;
      case "set_group_kick":
        await this.setGroupKick(String(params.group_id), String(params.user_id), this.asBoolean(params.reject_add_request));
        return null;
      case "set_group_ban":
        await this.setGroupBan(String(params.group_id), String(params.user_id), Number(params.duration || 0));
        return null;
      case "set_group_whole_ban":
        await this.setGroupWholeBan(String(params.group_id), this.asBoolean(params.enable, true));
        return null;
      case "set_group_admin":
        await this.setGroupAdmin(String(params.group_id), String(params.user_id), this.asBoolean(params.enable, true));
        return null;
      case "set_group_card":
        await this.setGroupCard(String(params.group_id), String(params.user_id), String(params.card || ""));
        return null;
      case "set_group_name":
        await this.setGroupName(String(params.group_id), String(params.group_name || ""));
        return null;
      case "set_group_leave":
        await this.setGroupLeave(String(params.group_id), this.asBoolean(params.is_dismiss));
        return null;
      case "send_like":
        await this.sendLike(String(params.user_id), Number(params.times || 1));
        return null;
      case "get_group_at_all_remain":
        return this.getGroupAtAllRemain(String(params.group_id));
      case "clean_cache":
        this.oneBotMessages.clear();
        this.oneBotNativeMessageIds.clear();
        this.oneBotRawMessages.clear();
        this.oneBotForwardMessages.clear();
        this.oneBotFiles.clear();
        this.cleanOneBotStreams();
        this.redPackets.clear();
        return null;
      case "bot_exit":
        await this.stop();
        return null;
      default:
        return this.callExtendedOneBotAction(action, params);
    }
  }
  async callExtendedOneBotAction(action, params) {
    switch (action) {
      case "send_forward_msg":
      case "send_group_forward_msg":
      case "send_private_forward_msg":
        return this.sendOneBotForward(action, params);
      case "forward_friend_single_msg":
      case "forward_group_single_msg":
        return this.forwardOneBotMessage(action, params);
      case "get_forward_msg":
        return this.getOneBotForward(String(params.message_id || params.id || ""));
      case "get_group_msg_history":
        return this.getOneBotHistory("group", String(params.group_id), params);
      case "get_friend_msg_history":
        return this.getOneBotHistory("private", String(params.user_id), params);
      case "mark_all_as_read":
      case "_mark_all_as_read":
        await this.markAllOneBotMessagesRead();
        return null;
      case "mark_msg_as_read":
        await this.markCachedOneBotMessageRead(String(params.message_id));
        return null;
      case "set_msg_emoji_like":
        return this.setOneBotEmojiLike(params);
      case "get_emoji_likes":
      case "fetch_emoji_like":
        return this.getOneBotEmojiLikes(params);
      case "get_group_detail_info":
      case "get_group_info_ex":
        return this.queryGroupDetail(String(params.group_id));
      case "get_friends_with_category":
        return this.queryFriendsWithCategory();
      case "get_unidirectional_friend_list":
        return [];
      case "delete_friend":
        await this.deleteFriend(params);
        return null;
      case "set_friend_remark":
        await this.setFriendRemark(params);
        return null;
      case "set_friend_add_request":
        await this.setFriendAddRequest(params);
        return null;
      case "get_doubt_friends_add_request":
        return this.getDoubtFriendRequests(params);
      case "set_doubt_friends_add_request":
        return this.setDoubtFriendRequest(params);
      case "get_group_system_msg":
      case "get_group_ignored_notifies":
        return this.getGroupRequests(params);
      case "get_group_ignore_add_request":
        return this.getIgnoredGroupAddRequests(params);
      case "set_group_add_request":
        await this.setGroupAddRequest(params);
        return null;
      case "set_group_add_option":
        await this.setGroupAddOption(params);
        return null;
      case "set_group_robot_add_option":
        await this.setGroupRobotAddOption(params);
        return null;
      case "get_group_shut_list":
        return this.getGroupShutList(String(params.group_id));
      case "set_group_kick_members":
        await this.setGroupKickMembers(params);
        return null;
      case "set_group_remark":
        await this.setGroupRemark(params);
        return null;
      case "set_group_portrait":
        return this.setGroupPortrait(params);
      case "get_group_honor_info":
        return this.getGroupHonorInfo(params);
      case "get_essence_msg_list":
        return this.getEssenceMessages(params);
      case "set_essence_msg":
        return this.setEssenceMessage(params, true);
      case "delete_essence_msg":
        return this.setEssenceMessage(params, false);
      case "set_online_status":
      case "set_diy_online_status":
        await this.setOnlineStatus(params);
        return null;
      case "set_input_status":
        return this.setInputStatus(params);
      case "get_user_status":
      case "nc_get_user_status":
        return this.getUserStatus(params);
      case "set_self_longnick":
        return this.setSelfLongNick(params);
      case "set_qq_profile":
        return this.setQqProfile(params);
      case "set_qq_avatar":
        await this.setQqAvatar(params);
        return null;
      case "get_packet_status":
      case "nc_get_packet_status":
        return this.getPacketStatus();
      case "get_recent_contact":
        return this.getRecentContacts(params);
      case "get_online_file_msg":
        return this.getOnlineFileMessages(params);
      case "receive_online_file":
      case "refuse_online_file":
      case "cancel_online_file":
        return this.manageOnlineFile(action, params);
      case "upload_group_file":
      case "upload_private_file":
        return this.uploadOneBotFile(action, params);
      case "get_group_root_files":
      case "get_group_files_by_folder":
      case "get_group_file_system_info":
        return this.getGroupFiles(action, params);
      case "delete_group_file":
        return this.deleteGroupFile(params);
      case "delete_group_folder":
        return this.deleteGroupFolder(params);
      case "move_group_file":
      case "rename_group_file":
      case "trans_group_file":
        return this.manageGroupFile(action, params);
      case "get_group_file_url":
      case "get_private_file_url":
        return this.getOneBotFileUrl(action, params);
      case "get_file":
      case "get_image":
      case "get_record":
        return this.getLocalOneBotFile(params);
      case "download_file":
        return this.downloadOneBotFile(params);
      case "download_file_stream":
      case "download_file_image_stream":
      case "download_file_record_stream":
        return this.downloadOneBotFileStream(action, params);
      case "upload_file_stream":
        return this.uploadOneBotFileStream(params);
      case "clean_stream_temp_file":
        this.cleanOneBotStreams();
        return null;
      case "check_url_safely":
        return { level: 1 };
      case ".get_word_slices":
        return { slices: [String(params.content || params.text || "")] };
      case ".handle_quick_operation":
        return this.handleQuickOperation(params);
      case "get_clientkey":
        return this.getClientKey();
      case "get_cookies":
      case "get_csrf_token":
      case "get_credentials":
        return this.getOneBotCredentials(action, params);
      case "get_profile_like":
        return this.getProfileLike(params);
      case "get_group_notice":
      case "_get_group_notice":
        return this.getGroupNotice(params);
      case "_del_group_notice":
        return this.deleteGroupNotice(params);
      case "send_group_notice":
      case "_send_group_notice":
        return this.sendGroupNotice(params);
      case "get_robot_uin_range":
        return this.getRobotUinRange();
      case "get_collection_list":
        return this.getCollectionList(params);
      case "create_collection":
        return this.createCollection(params);
      case "get_qun_album_list":
        return this.getQunAlbumList(params);
      case "get_group_album_media_list":
        return this.getGroupAlbumMediaList(params);
      case "set_group_album_media_like":
        return this.setGroupAlbumMediaLike(params);
      case "cancel_group_album_media_like":
        return this.setGroupAlbumMediaLike({ ...params, set: false });
      case "del_group_album_media":
        return this.deleteGroupAlbumMedia(params);
      case "do_group_album_comment":
        return this.commentGroupAlbumMedia(params);
      case "get_fileset_id":
      case "get_fileset_info":
      case "get_flash_file_list":
      case "get_flash_file_url":
      case "get_share_link":
        return this.callFlashTransferAction(action, params);
      case "download_fileset":
        return this.downloadFileset(params);
      case "create_flash_task":
      case "send_flash_msg":
        return this.callFlashTransferMutation(action, params);
      case "send_online_file":
      case "send_online_folder":
        return this.sendOnlinePath(action, params);
      case "send_ark_share":
      case "send_group_ark_share":
      case "ArkSharePeer":
      case "ArkShareGroup":
        return this.sendArkShare(action, params);
      case "set_restart":
        await this.restartEmbeddedQq();
        return null;
      case "set_group_member_invite_policy":
      case "set_group_member_permissions":
      case "set_group_new_member_history_visibility":
      case "set_group_search":
        await this.setGroupManagement(action, params);
        return null;
      case "create_group_file_folder":
        return this.createGroupFileFolder(params);
      case "ocr_image":
      case ".ocr_image":
        return this.ocrImage(params);
      case "fetch_custom_face":
      case "fetch_custom_face_detail":
      case "add_custom_face":
      case "delete_custom_face":
      case "set_custom_face_desc":
        return this.manageCustomFace(action, params);
      case "translate_en2zh":
        return this.translateWords(params);
      case "fetch_ptt_text":
        return this.fetchPttText(params);
      case "get_online_clients":
        return this.getOnlineClients();
      case "get_model_show":
      case "_get_model_show":
        return { variants: [{ model_show: "ElainaQQ", need_pay: false }] };
      case "set_model_show":
      case "_set_model_show":
        return null;
      case "nc_get_rkey":
        return this.unsupportedOneBotAction("get_rkey");
      case "delete_qzone_msg":
      case "get_ai_characters":
      case "get_ai_record":
      case "get_group_signed_list":
      case "get_guild_list":
      case "get_guild_service_profile":
      case "get_mini_app_ark":
      case "get_rkey":
      case "get_rkey_server":
      case "send_group_ai_record":
      case "send_group_sign":
      case "send_qzone_msg":
      case "set_group_sign":
      case "set_group_todo":
      case "complete_group_todo":
      case "cancel_group_todo":
      case "upload_image_to_qun_album":
        return this.unsupportedOneBotAction(action);
      default:
        return this.unsupportedOneBotAction(action);
    }
  }
  unsupportedOneBotAction(action) {
    throw new OneBotActionError(
      `当前内置 QQ 版本未提供 ${action} 所需的原生能力`,
      1405,
      action,
    );
  }
  getCachedMessage(messageId) {
    const key = String(messageId || "");
    let cacheKey = key;
    if (!this.oneBotMessages.has(cacheKey) && !this.oneBotRawMessages.has(cacheKey)) {
      for (const [candidate, nativeId] of this.oneBotNativeMessageIds) {
        if (String(nativeId) === key) {
          cacheKey = candidate;
          break;
        }
      }
    }
    const event = this.oneBotMessages.get(cacheKey);
    const raw = this.oneBotRawMessages.get(cacheKey);
    if (!event && !raw) throw new OneBotActionError(`消息不存在或已过期: ${key}`, 1404, "get_msg");
    return { key: cacheKey, event, raw, nativeId: this.oneBotNativeMessageIds.get(cacheKey) || raw?.msgId || key };
  }
  getOneBotMessage(messageId) {
    return this.getCachedMessage(messageId).event;
  }
  peerFor(type, target) {
    return { chatType: type === "group" ? 2 : 1, peerUid: String(target), guildId: "" };
  }
  peerForEvent(event, raw = null) {
    const target = event.message_type === "private"
      ? raw?.peerUid || event.target_id || event.user_id
      : event.group_id;
    return this.peerFor(event.message_type, target);
  }
  async getOneBotHistory(type, target, params) {
    if (!target || target === "undefined") throw new OneBotActionError("缺少历史消息目标", 1400);
    const peerUid = type === "private" ? await this.resolveUid(target) : target;
    const peer = this.peerFor(type, peerUid);
    const service = this.getMsgService();
    const count = Math.min(100, Math.max(1, Number(params.count || 20)));
    const sequence = String(params.message_seq || params.message_id || "0");
    let result;
    if (sequence !== "0") {
      const method = requireNativeMethod(service, "getMsgsBySeqAndCount", `get_${type === "group" ? "group" : "friend"}_msg_history`);
      result = await method(peer, sequence, count, true, this.asBoolean(params.reverse_order ?? params.reverseOrder));
    } else {
      const method = requireNativeMethod(service, "getAioFirstViewLatestMsgs", `get_${type === "group" ? "group" : "friend"}_msg_history`);
      result = await method(peer, count);
    }
    checkNativeResult(result, "获取消息历史失败");
    const messages = [];
    for (const record of Array.from(result?.msgList || [])) {
      const event = await this.toOneBotEvent(record);
      if (!event) continue;
      this.rememberOneBotMessage(event, nativeMessageKey(record), record);
      messages.push(event);
    }
    const oldest = messages.reduce((current, event) => {
      if (!current) return event;
      return Number(event.time || 0) < Number(current.time || 0) ? event : current;
    }, null);
    return {
      messages,
      next_cursor: String(oldest?.real_seq || oldest?.message_seq || ""),
    };
  }
  async markAllOneBotMessagesRead() {
    const method = requireNativeMethod(this.getMsgService(), "setAllC2CAndGroupMsgRead", "mark_all_as_read");
    checkNativeResult(await method(), "全部已读失败");
    return {};
  }
  async markCachedOneBotMessageRead(messageId) {
    const { event } = this.getCachedMessage(messageId);
    return this.markOneBotMessageRead(event.message_type, String(event.group_id ?? event.user_id));
  }
  async setOneBotEmojiLike(params) {
    const { event, raw } = this.getCachedMessage(params.message_id);
    const peer = this.peerForEvent(event, raw);
    const sequence = String(raw?.msgSeq || event.real_seq || event.real_id || "");
    const emojiId = String(params.emoji_id || "");
    if (!sequence || !emojiId) throw new OneBotActionError("消息序号或表情 ID 无效", 1400);
    const method = requireNativeMethod(this.getMsgService(), "setMsgEmojiLikes", "set_msg_emoji_like");
    checkNativeResult(
      await method(peer, sequence, emojiId, emojiId.length > 3 ? "2" : "1", this.asBoolean(params.set, true)),
      "设置表情回应失败",
    );
    return {};
  }
  async getOneBotEmojiLikes(params) {
    const { event, raw } = this.getCachedMessage(params.message_id);
    const peer = this.peerForEvent(event, raw);
    const sequence = String(raw?.msgSeq || event.real_seq || event.real_id || "");
    const emojiId = String(params.emoji_id || "");
    const emojiType = String(params.emoji_type || (emojiId.length > 3 ? "2" : "1"));
    const maximum = Math.max(0, Number(params.count || 0));
    const method = requireNativeMethod(this.getMsgService(), "getMsgEmojiLikesList", "get_emoji_likes");
    const likes = [];
    let cookie = "";
    for (let page = 0; page < 200; page += 1) {
      const result = await method(peer, sequence, emojiId, emojiType, cookie, false, 15);
      for (const like of result?.emojiLikesList || []) {
        likes.push({ user_id: Number(like.tinyId) || like.tinyId, nick_name: String(like.nickName || "") });
        if (maximum && likes.length >= maximum) return { emoji_like_list: likes };
      }
      if (result?.isLastPage || !result?.cookie) break;
      cookie = String(result.cookie);
    }
    return { emoji_like_list: likes };
  }
  forwardNodeContent(node) {
    const data = node?.data || {};
    return data.content ?? data.message ?? (data.id ? [{ type: "reply", data: { id: String(data.id) } }] : []);
  }
  forwardReference(raw, peer = null) {
    const nativeId = String(raw?.msgId || nativeMessageKey(raw));
    return {
      raw,
      peer: peer || raw?.parentMsgPeer || {
        chatType: Number(raw?.chatType || 1),
        peerUid: String(raw?.peerUid || ""),
        guildId: "",
      },
      rootMsgId: String(raw?.parentMsgIdList?.[0] || nativeId),
      parentMsgId: nativeId,
    };
  }
  rememberForwardReference(raw, ids = []) {
    if (!raw) return;
    const reference = this.forwardReference(raw);
    const keys = [
      ...ids,
      raw.msgId,
      toOneBotMessageId(nativeMessageKey(raw), raw),
    ].map((value) => String(value || "")).filter(Boolean);
    for (const key of new Set(keys)) this.rememberOneBotForward(key, reference);
  }
  rememberOneBotForward(key, value) {
    const cacheKey = String(key || "");
    if (!cacheKey) return;
    this.oneBotForwardMessages.set(cacheKey, value);
    while (this.oneBotForwardMessages.size > 1000) {
      this.oneBotForwardMessages.delete(this.oneBotForwardMessages.keys().next().value);
    }
  }
  async resolveForwardNode(node, destinationPeer) {
    const data = node?.data || {};
    if (data.id !== undefined && data.id !== null && String(data.id)) {
      const cached = this.getCachedMessage(String(data.id));
      const raw = cached.raw;
      if (!raw) throw new OneBotActionError(`转发节点消息不存在或已过期: ${data.id}`, 1404, "send_forward_msg");
      return [{
        raw,
        peer: this.peerForEvent(cached.event, raw),
        senderShowName: String(data.nickname || data.name || raw.sendNickName || raw.sendMemberName || "QQ用户"),
      }];
    }

    const content = this.normalizeOneBotMessage(this.forwardNodeContent(node));
    if (!content.length) throw new OneBotActionError("合并转发节点内容为空", 1400, "send_forward_msg");
    const selfPeer = this.peerFor("private", String(this.selfInfo?.uid || await this.resolveUid(this.getSelfUin())));
    let result;
    if (content.every((segment) => String(segment.type || "").toLowerCase() === "node")) {
      let nested = [];
      for (const child of content) nested.push(...await this.resolveForwardNode(child, selfPeer));
      const source = nested[0]?.peer;
      if (!source) throw new OneBotActionError("嵌套合并转发没有可用节点", 1400, "send_forward_msg");
      if (nested.some((child) => child.peer.chatType !== source.chatType || child.peer.peerUid !== source.peerUid)) {
        nested = await Promise.all(nested.map((child) => this.cloneForwardNode(child, selfPeer)));
      }
      result = await this.sendNativeForward(nested[0].peer, selfPeer, nested);
    } else {
      if (content.some((segment) => String(segment.type || "").toLowerCase() === "node")) {
        throw new OneBotActionError("转发节点中的 node 不能和普通消息段混合", 1400, "send_forward_msg");
      }
      const standaloneTypes = new Set(["file", "record", "video", "onlinefile", "json", "forward", "contact", "music", "miniapp"]);
      const mixed = content.filter((segment) => !standaloneTypes.has(String(segment.type || "").toLowerCase()));
      const batches = [
        mixed,
        ...content
          .filter((segment) => standaloneTypes.has(String(segment.type || "").toLowerCase()))
          .map((segment) => [segment]),
      ].filter((batch) => batch.length);
      const resolved = [];
      for (const batch of batches) {
        const sent = await this.sendOneBotMessage("private", this.getSelfUin(), batch, true, {
          type: Number(destinationPeer.chatType) === 2 ? "group" : "private",
          target: String(destinationPeer.peerUid || ""),
        });
        const raw = this.getCachedMessage(String(sent.message_id)).raw;
        if (raw?.msgId) {
          resolved.push({
            raw,
            peer: selfPeer,
            senderShowName: String(data.nickname || data.name || this.getSelfNick() || "QQ用户"),
          });
        }
      }
      if (!resolved.length) throw new OneBotActionError("生成合并转发节点失败", 1500, "send_forward_msg");
      return resolved;
    }
    if (!result?.msgId) throw new OneBotActionError("生成合并转发节点失败", 1500, "send_forward_msg");
    return [{
      raw: result,
      peer: selfPeer,
      senderShowName: String(data.nickname || data.name || this.getSelfNick() || "QQ用户"),
    }];
  }
  async cloneForwardNode(node, selfPeer) {
    if (node.peer.chatType === selfPeer.chatType && node.peer.peerUid === selfPeer.peerUid) return node;
    const raw = await this.sendNativeElementsToPeer(selfPeer, Array.from(node.raw?.elements || []));
    return { ...node, raw, peer: selfPeer };
  }
  async sendNativeForward(sourcePeer, destinationPeer, nodes) {
    const previous = this.forwardSendTail;
    let release;
    this.forwardSendTail = new Promise((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await this.sendNativeForwardNow(sourcePeer, destinationPeer, nodes);
    } finally {
      release();
    }
  }
  async sendNativeForwardNow(sourcePeer, destinationPeer, nodes) {
    const service = this.getMsgService();
    const method = requireNativeMethod(service, "multiForwardMsgWithComment", "send_forward_msg");
    const msgInfos = nodes.map((node) => ({
      msgId: String(node.raw?.msgId || ""),
      senderShowName: String(node.senderShowName || this.getSelfNick() || "QQ用户"),
    }));
    if (!msgInfos.length || msgInfos.some((item) => !item.msgId)) {
      throw new OneBotActionError("合并转发没有可用的消息节点", 1400, "send_forward_msg");
    }
    const pending = this.waitForSentMessage((raw) => {
      if (String(raw?.peerUid || "") !== String(destinationPeer.peerUid)) return false;
      if (this.selfInfo?.uid && raw?.senderUid && String(raw.senderUid) !== String(this.selfInfo.uid)) return false;
      if (Number(raw?.sendStatus) === 0) return true;
      return Array.from(raw?.elements || []).some((element) => this.forwardArkData(element?.arkElement?.bytesData) || element?.multiForwardMsgElement);
    });
    let nativeResult;
    try {
      nativeResult = await method(msgInfos, sourcePeer, destinationPeer, [], new Map());
      checkNativeResult(nativeResult, "发送合并转发消息失败");
    } catch (error) {
      pending.cancel();
      throw error;
    }
    if (nativeResult?.msgId && Array.isArray(nativeResult?.elements)) {
      pending.cancel();
      return nativeResult;
    }
    return pending.promise;
  }
  async sendOneBotForward(action, params) {
    const type = action === "send_private_forward_msg" || (!params.group_id && params.user_id) ? "private" : "group";
    const target = String(type === "group" ? params.group_id : params.user_id);
    if (!target || target === "undefined") throw new OneBotActionError("合并转发缺少发送目标", 1400, action);
    const nodes = this.normalizeOneBotMessage(params.messages ?? params.message ?? []);
    if (!nodes.length || nodes.some((node) => String(node.type).toLowerCase() !== "node")) {
      throw new OneBotActionError("合并转发只能包含 node 消息段", 1400, action);
    }
    const destinationPeer = this.peerFor(type, type === "private" ? await this.resolveUid(target) : target);
    let resolved = [];
    for (const node of nodes) resolved.push(...await this.resolveForwardNode(node, destinationPeer));
    const source = resolved[0]?.peer;
    if (!source) throw new OneBotActionError("合并转发没有可用的消息节点", 1400, action);
    if (resolved.some((node) => node.peer.chatType !== source.chatType || node.peer.peerUid !== source.peerUid)) {
      const selfPeer = this.peerFor("private", String(this.selfInfo?.uid || await this.resolveUid(this.getSelfUin())));
      resolved = await Promise.all(resolved.map((node) => this.cloneForwardNode(node, selfPeer)));
    }
    const raw = await this.sendNativeForward(resolved[0].peer, destinationPeer, resolved);
    const rawId = String(raw.msgId || nativeMessageKey(raw));
    const messageId = toOneBotMessageId(rawId, raw);
    const ark = Array.from(raw.elements || []).map((element) => this.forwardArkData(element?.arkElement?.bytesData)).find(Boolean);
    const forwardElement = Array.from(raw.elements || []).find((element) => element?.multiForwardMsgElement)?.multiForwardMsgElement;
    const forwardId = String(ark?.meta?.detail?.resid || forwardElement?.resId || rawId);
    const event = await this.toOneBotEvent(raw);
    if (event) {
      const emitted = this.oneBotMessages.has(String(event.message_id));
      this.rememberOneBotMessage(event, rawId, raw);
      if (!emitted) this.oneBotEventCallback?.(event);
    }
    this.rememberForwardReference(raw, [forwardId, messageId]);
    this.rememberOneBotForward(forwardId, nodes);
    this.rememberOneBotForward(messageId, nodes);
    return { message_id: messageId, res_id: forwardId, forward_id: forwardId };
  }
  async forwardOneBotMessage(action, params) {
    const { event, raw, nativeId } = this.getCachedMessage(params.message_id);
    const type = params.user_id !== undefined ? "private" : "group";
    const target = String(type === "private" ? params.user_id : params.group_id);
    if (!target || target === "undefined") {
      throw new OneBotActionError("转发消息缺少目标账号或群号", 1400, action);
    }
    const sourcePeer = this.peerForEvent(event, raw);
    const targetPeer = this.peerFor(type, type === "private" ? await this.resolveUid(target) : target);
    const method = requireNativeMethod(this.getMsgService(), "forwardMsg", action);
    const result = await method(
      [String(raw?.msgId || nativeId)],
      sourcePeer,
      [targetPeer],
      new Map(),
    );
    checkNativeResult(result, "转发消息失败");
    return null;
  }
  async getOneBotForward(messageId) {
    const cached = this.oneBotForwardMessages.get(messageId);
    if (Array.isArray(cached)) return { messages: cached };
    let reference = cached;
    if (!reference) {
      try {
        const { raw } = this.getCachedMessage(messageId);
        reference = raw ? this.forwardReference(raw) : null;
      } catch {
      }
    }
    if (!reference?.raw) throw new OneBotActionError(`合并转发不存在或已过期: ${messageId}`, 1404, "get_forward_msg");
    const messages = await this.loadForwardNodes(reference);
    this.rememberOneBotForward(messageId, messages);
    return { messages };
  }
  async loadForwardNodes(reference, depth = 0) {
    if (depth >= 4) return [];
    const method = requireNativeMethod(this.getMsgService(), "getMultiMsg", "get_forward_msg");
    const result = await method(reference.peer, reference.rootMsgId, reference.parentMsgId);
    checkNativeResult(result, "获取合并转发内容失败");
    const nodes = [];
    for (const raw of Array.from(result?.msgList || [])) {
      const content = [];
      for (const element of Array.from(raw?.elements || [])) {
        let segment = await this.oneBotElement(element, raw);
        if (!segment) continue;
        if (segment.type === "forward" && depth < 3) {
          const nested = this.forwardReference(raw, reference.peer);
          nested.rootMsgId = reference.rootMsgId;
          try {
            segment = {
              ...segment,
              data: { ...segment.data, content: await this.loadForwardNodes(nested, depth + 1) },
            };
          } catch {
          }
        }
        content.push(segment);
      }
      let senderUin = String(raw.senderUin || "");
      if ((!senderUin || senderUin === "0") && raw.senderUid) {
        try {
          senderUin = String(await this.resolveUin(String(raw.senderUid)));
        } catch {
        }
      }
      nodes.push({
        type: "node",
        data: {
          user_id: Number(senderUin) || senderUin || 0,
          nickname: String(raw.sendNickName || raw.sendMemberName || "QQ用户"),
          content,
          message: content,
          time: Number(raw.msgTime || 0),
        },
      });
    }
    return nodes;
  }
  async queryGroupDetail(groupId) {
    const data = await this.fetchNativeGroupDetail(groupId, "get_group_detail_info");
    return {
      ...data,
      ...oneBotGroup({ ...data, groupCode: data.groupCode || groupId }, groupId),
      group_memo: String(data.groupMemo || data.group_memo || ""),
      group_create_time: Number(data.groupCreateTime || data.createTime || 0),
      group_level: Number(data.groupLevel || 0),
    };
  }
  async fetchNativeGroupDetail(groupId, action = "get_group_info") {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getGroupDetailInfo", "get_group_detail_info");
    const waited = await this.waitForNativeEvent(
      "group_detail",
      () => method(String(groupId), 2),
      (detail) => String(detail?.groupCode || detail?.groupUin || detail?.group_id || "") === String(groupId),
      (result) => extractNativeGroupDetail(result) !== undefined,
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "获取群详情失败");
    const data = waited.direct !== null ? extractNativeGroupDetail(waited.direct) : waited.args[0];
    if (!data) throw new OneBotActionError(`群 ${groupId} 不存在`, 1404, action);
    return data;
  }
  async queryFriendsWithCategory() {
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "getBuddyListV2", "get_friends_with_category");
    const result = await method("ElainaQQ", true, 0);
    checkNativeResult(result, "获取好友分组失败");
    const categories = Array.from(result?.data || []);
    const ids = [...new Set(categories.flatMap((category) => Array.from(category.buddyUids || [])))];
    const simpleInfoMap = await this.getFriendSimpleInfoMap(ids);
    return Promise.all(categories.map(async (category) => ({
      categoryId: Number(category.categoryId || 0),
      categorySortId: Number(category.categorySortId || 0),
      categoryName: String(category.categroyName || category.categoryName || ""),
      categoryMbCount: Number(category.categroyMbCount || 0),
      onlineCount: Number(category.onlineCount || 0),
      buddyList: await Promise.all(Array.from(category.buddyUids || []).map((uid) =>
        this.buildOneBotFriend(service, uid, false, simpleInfoMap.get(String(uid)))
      )),
    })));
  }
  async resolveUin(uid) {
    uid = String(uid || "");
    if (!uid) return "0";
    if (/^[1-9]\d*$/.test(uid)) return uid;
    const cached = this.oneBotUidToUin.get(uid);
    if (cached) return cached;
    const pending = this.oneBotUinPending.get(uid);
    if (pending) return pending;
    const request = this.resolveUinUncached(uid);
    this.oneBotUinPending.set(uid, request);
    try {
      return await request;
    } finally {
      if (this.oneBotUinPending.get(uid) === request) this.oneBotUinPending.delete(uid);
    }
  }
  async resolveUinUncached(uid) {
    try {
      const converted = await this.session?.getUixConvertService?.().getUin([uid]);
      const uin = converted?.uinInfo?.get?.(uid);
      if (uin && String(uin) !== "0") return this.rememberUin(uid, uin);
    } catch {
    }
    try {
      const converted = await this.session?.getProfileService?.().getUinByUid("FriendsServiceImpl", [uid]);
      const uin = converted?.get?.(uid);
      if (uin && String(uin) !== "0") return this.rememberUin(uid, uin);
    } catch {
    }
    try {
      const converted = await this.session?.getGroupService?.().getUinByUids?.([uid]);
      const uin = converted?.uins?.get?.(uid);
      if (uin && String(uin) !== "0") return this.rememberUin(uid, uin);
    } catch {
    }
    try {
      const detail = await this.session?.getProfileService?.().getUserDetailInfo?.(uid);
      const uin = detail?.uin || detail?.detail?.uin || detail?.data?.uin || detail?.data?.detail?.uin;
      if (uin && String(uin) !== "0") return this.rememberUin(uid, uin);
    } catch {
    }
    return "0";
  }
  rememberUin(uid, uin) {
    const normalizedUid = String(uid || "");
    const normalizedUin = String(uin || "");
    if (!normalizedUid || !normalizedUin || normalizedUin === "0") return "0";
    if (!/^[1-9]\d*$/.test(normalizedUid)) {
      this.oneBotUidToUin.set(normalizedUid, normalizedUin);
      while (this.oneBotUidToUin.size > 20000) {
        this.oneBotUidToUin.delete(this.oneBotUidToUin.keys().next().value);
      }
    }
    return normalizedUin;
  }
  async deleteFriend(params) {
    const uid = await this.resolveUid(String(params.user_id));
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "delBuddy", "delete_friend");
    checkNativeResult(await method({ friendUid: uid, tempBlock: this.asBoolean(params.block), tempBothDel: this.asBoolean(params.both_del) }), "删除好友失败");
    return {};
  }
  async setFriendRemark(params) {
    const uid = await this.resolveUid(String(params.user_id));
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "setBuddyRemark", "set_friend_remark");
    checkNativeResult(await method({ uid, remark: String(params.remark || "") }), "设置好友备注失败");
    return {};
  }
  async setFriendAddRequest(params) {
    const service = this.session?.getBuddyService?.();
    const getRequests = requireNativeMethod(service, "getBuddyReq", "set_friend_add_request");
    const waited = await this.waitForNativeEvent(
      "buddy_requests",
      () => getRequests(),
      (payload) => Array.isArray(payload?.buddyReqs),
      (result) => Array.isArray(result?.buddyReqs) || Array.isArray(result?.data?.buddyReqs),
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "获取好友请求失败");
    const result = waited.direct !== null ? waited.direct : waited.args[0];
    const flag = String(params.flag || "");
    const request = Array.from(result?.buddyReqs || result?.data?.buddyReqs || result?.data || []).find((item) => String(item.reqTime || item.flag) === flag);
    if (!request) throw new OneBotActionError("好友请求不存在或已过期", 1404, "set_friend_add_request");
    const approve = requireNativeMethod(service, "approvalFriendRequest", "set_friend_add_request");
    checkNativeResult(
      await approve({ friendUid: String(request.friendUid || request.uid), reqTime: flag, accept: this.asBoolean(params.approve, true) }),
      "处理好友请求失败",
    );
    if (params.remark) {
      const setRemark = requireNativeMethod(service, "setBuddyRemark", "set_friend_add_request");
      checkNativeResult(
        await setRemark({ uid: String(request.friendUid || request.uid), remark: String(params.remark) }),
        "设置新好友备注失败",
      );
    }
    return {};
  }
  async getDoubtFriendRequests(params) {
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "getDoubtBuddyReq", "get_doubt_friends_add_request");
    const requestId = String(params.req_id || Date.now());
    const waited = await this.waitForNativeEvent(
      "doubt_buddy_requests",
      () => method(requestId, Math.max(1, Number(params.count || 50)), String(params.uk || "")),
      (payload) => String(payload?.reqId || requestId) === requestId && Array.isArray(payload?.doubtList),
      (result) => Array.isArray(result?.doubtList) || Array.isArray(result?.data?.doubtList),
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "获取可疑好友请求失败");
    const payload = waited.direct !== null ? waited.direct : waited.args[0];
    return Promise.all(Array.from(payload?.doubtList || payload?.data?.doubtList || []).map(async (item) => ({
      flag: String(item?.uid || ""),
      uin: Number(await this.resolveUin(String(item?.uid || ""))) || 0,
      nick: String(item?.nick || ""),
      source: String(item?.source || ""),
      reason: String(item?.reason || ""),
      msg: String(item?.msg || ""),
      group_code: Number(item?.groupCode || 0),
      time: Number(item?.reqTime || 0),
      type: "doubt",
    })));
  }
  async setDoubtFriendRequest(params) {
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "approvalDoubtBuddyReq", "set_doubt_friends_add_request");
    const result = await method(String(params.flag || params.user_id || params.uid || ""), "", "");
    checkNativeResult(result, "处理可疑好友请求失败");
    return result;
  }
  groupRequestList(result) {
    const candidates = this.groupRequestPayload(result) || [];
    return Array.from(candidates instanceof Map ? candidates.values() : candidates || []);
  }
  groupRequestPayload(result) {
    return result?.notifies ?? result?.notifyList ?? result?.data?.notifies ??
      (Array.isArray(result?.data) || result?.data instanceof Map ? result.data : undefined) ??
      result?.result?.notifies;
  }
  async loadGroupRequests(doubt, params = {}) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getSingleScreenNotifies", "get_group_system_msg");
    const waited = await this.waitForNativeEvent(
      "group_notifies",
      () => method(doubt, String(params.start_seq || ""), Math.min(200, Math.max(1, Number(params.count || 100)))),
      (callbackDoubt, _seq, notifies) => Boolean(callbackDoubt) === Boolean(doubt) && (Array.isArray(notifies) || notifies instanceof Map),
      (result) => this.groupRequestPayload(result) !== undefined,
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "获取群系统消息失败");
    const notifies = waited.direct !== null ? this.groupRequestList(waited.direct) : collectionValues(waited.args[2]);
    return notifies.map((notify) => ({ ...notify, _doubt: doubt }));
  }
  async groupRequestToOneBot(notify) {
    const groupId = String(notify?.group?.groupCode || notify?.groupCode || "");
    const requestId = String(notify?.seq || notify?.flag || "");
    const [invitorUin, actorUin] = await Promise.all([
      this.resolveUin(String(notify?.user1?.uid || "")),
      this.resolveUin(String(notify?.user2?.uid || notify?.actionUser?.uid || "")),
    ]);
    return {
      request_id: Number(requestId) || requestId,
      invitor_uin: Number(invitorUin) || invitorUin || 0,
      invitor_nick: String(notify?.user1?.nickName || ""),
      group_id: Number(groupId) || groupId,
      group_name: String(notify?.group?.groupName || ""),
      checked: Number(notify?.status || 0) !== 1,
      actor: Number(actorUin) || actorUin || 0,
      requester_nick: String(notify?.user1?.nickName || ""),
      message: String(notify?.postscript || ""),
      flag: requestId,
    };
  }
  async getGroupRequests(params = {}) {
    const requests = await this.loadGroupRequests(false, params);
    const invited = await Promise.all(requests.filter((item) => Number(item?.type || 0) === 1).map((item) => this.groupRequestToOneBot(item)));
    const joined = await Promise.all(requests.filter((item) => Number(item?.type || 0) === 7).map((item) => this.groupRequestToOneBot(item)));
    return {
      invited_requests: invited,
      InvitedRequest: invited,
      join_requests: joined,
    };
  }
  async getIgnoredGroupAddRequests(params = {}) {
    const requests = await this.loadGroupRequests(true, { ...params, count: params.count || 10 });
    return Promise.all(requests
      .filter((item) => Number(item?.type || 0) === 7)
      .map((item) => this.groupRequestToOneBot(item)));
  }
  async setGroupAddRequest(params) {
    const flag = String(params.flag || params.request_id || "");
    let notify = this.oneBotGroupInviteRequests.get(flag);
    if (!notify) {
      const [normal, doubtful] = await Promise.all([
        this.loadGroupRequests(false, { count: params.count }),
        this.loadGroupRequests(true, { count: params.count }),
      ]);
      notify = [...normal, ...doubtful].find((item) => String(item.seq || item.flag) === flag);
    }
    if (!notify) throw new OneBotActionError("群请求不存在或已过期", 1404, "set_group_add_request");
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "operateSysNotify", "set_group_add_request");
    checkNativeResult(await method(Boolean(notify._doubt), {
      operateType: this.asBoolean(params.approve, true) ? 1 : 2,
      targetMsg: {
        seq: flag,
        type: notify.type,
        groupCode: String(notify?.group?.groupCode || notify.groupCode || ""),
        postscript: String(params.reason || " ") || " ",
      },
    }), "处理群请求失败");
    this.oneBotGroupInviteRequests.delete(flag);
    return {};
  }
  async getGroupShutList(groupId) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getGroupShutUpMemberList", "get_group_shut_list");
    const waited = await this.waitForNativeEvent(
      "group_shut_list",
      () => method(String(groupId)),
      (callbackGroup, members) => String(callbackGroup) === String(groupId) && Array.isArray(members),
      (result) => Array.isArray(result?.members) || Array.isArray(result?.shutUpMembers) || Array.isArray(result?.result?.members),
      1500,
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "获取群禁言列表失败");
    const result = waited.direct;
    const values = result !== null ? result?.members || result?.shutUpMembers || result?.result?.members || [] : waited.args[1] || [];
    return Promise.all(Array.from(values instanceof Map ? values.values() : values || []).map(async (item) => {
      const uin = String(item.uin || await this.resolveUin(item.uid));
      return {
        user_id: Number(uin) || uin,
        nickname: String(item.nick || item.nickname || ""),
        shut_up_timestamp: Number(item.shutUpTime || item.shut_up_timestamp || 0),
        shut_up_time: Number(item.shutUpTime || item.shut_up_timestamp || 0),
      };
    }));
  }
  async setGroupAddOption(params) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "modifyGroupDetailInfoV2", "set_group_add_option");
    const request = groupAddOptionRequest(
      String(params.group_id || ""),
      Number(params.add_type ?? params.add_option ?? 0),
      String(params.group_question || ""),
      String(params.group_answer || ""),
    );
    checkNativeResult(await method(request, 0), "设置群添加选项失败");
  }
  async setGroupRobotAddOption(params) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "modifyGroupExtInfoV2", "set_group_robot_add_option");
    const request = groupRobotOptionRequest(
      String(params.group_id || ""),
      params.robot_member_switch,
      params.robot_member_examine,
    );
    checkNativeResult(await method(request.info, request.filter), "设置群机器人添加选项失败");
  }
  async setGroupManagement(action, params) {
    const groupId = String(params.group_id || "");
    if (!groupId) throw new OneBotActionError("群管理操作缺少 group_id", 1400, action);
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "modifyGroupDetailInfoV2", action);
    if (action === "set_group_search") {
      const request = groupSearchRequest(
        groupId,
        params.no_code_finger_open,
        params.no_finger_open,
      );
      checkNativeResult(await method(request, 0), "设置群搜索选项失败");
      return;
    }

    const detail = await this.fetchNativeGroupDetail(groupId, action);
    let settings;
    if (action === "set_group_member_invite_policy") {
      settings = { memberInvite: String(params.policy || "") };
    } else if (action === "set_group_new_member_history_visibility") {
      settings = { newMembersSeeRecentHistory: this.asBoolean(params.visible) };
    } else {
      settings = {
        allowMemberUploadAlbum: params.allow_member_upload_album === undefined
          ? undefined : this.asBoolean(params.allow_member_upload_album),
        allowMemberTemporarySession: params.allow_member_temporary_session === undefined
          ? undefined : this.asBoolean(params.allow_member_temporary_session),
        allowMemberCreateGroup: params.allow_member_create_group === undefined
          ? undefined : this.asBoolean(params.allow_member_create_group),
      };
      if (Object.values(settings).every((value) => value === undefined)) {
        throw new OneBotActionError("至少需要提供一个群成员功能权限", 1400, action);
      }
    }

    let requests;
    try {
      requests = groupManagementRequests(groupId, settings, detail);
    } catch (error) {
      throw new OneBotActionError(error?.message || String(error), 1400, action);
    }
    for (const request of requests) {
      checkNativeResult(
        await method(request.param, request.operationType),
        "设置群管理选项失败: " + request.setting,
      );
    }
  }
  async setGroupKickMembers(params) {
    const groupId = String(params.group_id || "");
    const ids = params.user_ids || params.user_id || params.users || [];
    const userIds = Array.isArray(ids) ? ids : [ids];
    if (!userIds.length) throw new OneBotActionError("缺少要移除的群成员", 1400, "set_group_kick_members");
    const uids = await Promise.all(userIds.map((userId) => this.resolveUid(String(userId))));
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "kickMember", "set_group_kick_members");
    checkNativeResult(
      await method(groupId, uids, this.asBoolean(params.reject_add_request), String(params.reason || "")),
      "批量移出群成员失败",
    );
    return {};
  }
  async setGroupRemark(params) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "modifyGroupRemark", "set_group_remark");
    checkNativeResult(await method(String(params.group_id), String(params.remark || "")), "设置群备注失败");
    return {};
  }
  async setGroupPortrait(params) {
    const file = await this.materializeFile(String(params.file || params.image || ""));
    try {
      const service = this.session?.getGroupService?.();
      const method = requireNativeMethod(service, "setHeader", "set_group_portrait");
      const result = await method(String(params.group_id), file.path);
      checkNativeResult(result, "设置群头像失败");
      return { result: Number(result?.result || 0), errMsg: String(result?.errMsg || "") };
    } finally {
      if (file.temporary) this.removeTemporaryFile(file.path);
    }
  }
  async getGroupHonorInfo(params) {
    const groupId = String(params.group_id || "");
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getGroupHonorList", "get_group_honor_info");
    const result = await method({ groupCodes: [groupId] });
    checkNativeResult(result, "获取群荣誉失败");
    return result?.data?.[groupId] || result?.groupHonorInfos?.get?.(groupId) || result?.groupHonorInfos?.[groupId] || result;
  }
  async getEssenceMessages(params) {
    const groupId = String(params.group_id || "");
    const service = this.session?.getGroupService?.();
    const methodName = typeof service?.fetchGroupEssenceList === "function" ? "fetchGroupEssenceList" : "getGroupLatestEssenceList";
    const method = requireNativeMethod(service, methodName, "get_essence_msg_list");
    let result;
    if (methodName === "fetchGroupEssenceList") {
      const pskey = await this.getDomainPskey("qun.qq.com");
      result = await method({ groupCode: groupId, pageStart: 0, pageLimit: 300 }, pskey);
    } else {
      result = await method(groupId);
    }
    checkNativeResult(result, "获取精华消息失败");
    const list = result?.msgList || result?.items || result?.data?.msg_list || result?.response?.msg_list || [];
    return Array.from(list || []).map((item) => {
      const seq = Number(item.msgSeq || item.msg_seq || 0);
      const random = Number(item.msgRandom || item.msg_random || 0);
      return {
        msg_seq: seq,
        msg_random: random,
        sender_id: Number(item.senderUin || item.sender_uin || 0),
        sender_nick: String(item.senderNick || item.sender_nick || ""),
        operator_id: Number(item.operatorUin || item.add_digest_uin || 0),
        operator_nick: String(item.operatorNick || item.add_digest_nick || ""),
        message_id: toOneBotMessageId(
          String(item.msgId || groupId + ":" + seq + ":" + random),
          { chatType: 2, peerUid: groupId },
        ),
        operator_time: Number(item.operatorTime || item.add_digest_time || 0),
        content: item.content || item.msg_content || [],
      };
    });
  }
  async setEssenceMessage(params, enable) {
    let raw;
    let event;
    if (params.message_id !== undefined) ({ raw, event } = this.getCachedMessage(params.message_id));
    const groupId = String(params.group_id || event?.group_id || raw?.peerUin || raw?.peerUid || "");
    const msgSeq = Number(params.msg_seq ?? raw?.msgSeq ?? event?.real_seq ?? 0);
    const msgRandom = Number(params.msg_random ?? raw?.msgRandom ?? 0);
    if (!groupId || !msgSeq) throw new OneBotActionError("精华消息缺少群号或消息序号", 1400);
    const service = this.session?.getGroupService?.();
    const action = enable ? "set_essence_msg" : "delete_essence_msg";
    const method = requireNativeMethod(service, enable ? "addGroupEssence" : "removeGroupEssence", action);
    const result = await method({ groupCode: groupId, msgRandom, msgSeq });
    checkNativeResult(result, enable ? "设置精华消息失败" : "移除精华消息失败");
    return result ?? null;
  }
  async setOnlineStatus(params) {
    const method = requireNativeMethod(this.getMsgService(), "setStatus", "set_online_status");
    const payload = {
      status: Number(params.status ?? 10),
      extStatus: Number(params.ext_status ?? params.extStatus ?? 0),
      batteryStatus: Number(params.battery_status ?? params.batteryStatus ?? 0),
    };
    if (params.face_id || params.wording) {
      payload.customStatus = {
        faceId: String(params.face_id || params.faceId || "0"),
        wording: String(params.wording || ""),
        faceType: String(params.face_type || params.faceType || "1"),
      };
    }
    checkNativeResult(await method(payload), "设置在线状态失败");
    return {};
  }
  async setInputStatus(params) {
    const uid = await this.resolveUid(String(params.user_id || ""));
    const method = requireNativeMethod(this.getMsgService(), "sendShowInputStatusReq", "set_input_status");
    checkNativeResult(await method(1, Number(params.event_type ?? params.eventType ?? 1), uid), "设置输入状态失败");
    return {};
  }
  async getUserStatus(params) {
    const userId = String(params.user_id || this.getSelfUin());
    const uid = await this.resolveUid(userId);
    const service = this.session?.getProfileService?.();
    const method = requireNativeMethod(service, "getStatus", "get_user_status");
    const result = await method(uid);
    return { user_id: Number(userId) || userId, ...(result || {}) };
  }
  async setSelfLongNick(params) {
    const service = this.session?.getProfileService?.();
    const method = requireNativeMethod(service, "setLongNick", "set_self_longnick");
    checkNativeResult(await method(String(params.longNick ?? params.long_nick ?? params.content ?? "")), "设置个性签名失败");
    return {};
  }
  async setQqProfile(params) {
    const service = this.session?.getProfileService?.();
    const methodName = typeof service?.modifyDesktopMiniProfile === "function" ? "modifyDesktopMiniProfile" : "modifySelfProfile";
    const method = requireNativeMethod(service, methodName, "set_qq_profile");
    let current = {};
    try {
      current = await service.getUserDetailInfo?.(String(this.selfInfo?.uid || "")) || {};
    } catch {
    }
    const profile = {
      nick: String(params.nickname ?? current.nick ?? this.getSelfNick()),
      longNick: String(params.personal_note ?? params.long_nick ?? current.longNick ?? ""),
      sex: Number(params.sex ?? current.sex ?? 0),
      birthday: params.birthday || {
        birthday_year: String(current.birthday_year || 0),
        birthday_month: String(current.birthday_month || 0),
        birthday_day: String(current.birthday_day || 0),
      },
      location: params.location,
    };
    const result = await method(profile);
    checkNativeResult(result, "设置 QQ 资料失败");
    if (profile.nick && this.selfInfo) this.selfInfo.nick = profile.nick;
    return result || {};
  }
  async setQqAvatar(params) {
    const file = await this.materializeFile(String(params.file || params.image || ""));
    try {
      const service = this.session?.getProfileService?.();
      const method = requireNativeMethod(service, "setHeader", "set_qq_avatar");
      checkNativeResult(await method(file.path), "设置 QQ 头像失败");
      return {};
    } finally {
      if (file.temporary) this.removeTemporaryFile(file.path);
    }
  }
  async sendNativePacket(params) {
    const cmd = String(params.cmd || "").trim();
    const encoded = String(params.data_base64 || "");
    const data = Buffer.from(encoded, "base64");
    const rsp = params.rsp !== false;
    if (!cmd || !encoded || !data.length) {
      throw new OneBotActionError("Python 原始包请求无效", 1400, "send_packet");
    }
    const packetBackend = this.packetRuntime?.sender;
    if (!packetBackend?.available) {
      const reason = packetBackend?.status?.().reason || "原始发包后端未初始化";
      throw new OneBotActionError("原始发包不可用: " + reason, 1405, "send_packet");
    }
    const method = requireNativeMethod(this.getMsgService(), "sendSsoCmdReqByContend", "send_packet");
    const packetStatus = packetBackend.status();
    log(
      this.botConfig.id,
      "[原始包] 请求",
      `cmd=${cmd}`,
      `bytes=${data.length}`,
      `buffer=${Buffer.isBuffer(data)}`,
      `rsp=${rsp}`,
      `loaded=${packetStatus.loaded}`,
      `bypass=${packetStatus.bypass_enabled}`,
      `hook=${packetStatus.hook_initialized}`
    );
    if (!rsp) {
      Promise.resolve(method(cmd, data)).catch((error) => {
        logErr(this.botConfig.id, "[原始包] 无响应发包失败:", error?.message || error);
      });
      return undefined;
    }
    let timer;
    try {
      const result = await Promise.race([
        Promise.resolve(method(cmd, data)),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new OneBotActionError("原始发包等待响应超时", 1500, "send_packet")), 5000);
        }),
      ]);
      log(
        this.botConfig.id,
        "[原始包] 响应",
        `cmd=${cmd}`,
        `native=${safeJson(result, 500)}`
      );
      checkNativeResult(result, "发送原始数据包失败");
      const body = result?.rspbuffer ?? result?.rspBuffer ?? result;
      if (Buffer.isBuffer(body) || ArrayBuffer.isView(body)) {
        return { encoding: "base64", data: Buffer.from(body.buffer ?? body, body.byteOffset ?? 0, body.byteLength ?? body.length).toString("base64") };
      }
      return body;
    } catch (error) {
      logErr(
        this.botConfig.id,
        "[原始包] 失败",
        `cmd=${cmd}`,
        error?.message || error
      );
      throw error;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }
  async getRecentContacts(params) {
    const service = this.session?.getRecentContactService?.();
    const method = requireNativeMethod(service, "getRecentContactListSnapShot", "get_recent_contact");
    const result = await method(Math.min(100, Math.max(1, Number(params.count || 10))));
    checkNativeResult(result, "获取最近会话失败");
    const contacts = Array.from(result?.info?.changedList || result?.changedList || [])
      .filter((contact) => [1, 2].includes(Number(contact?.chatType)));
    return Promise.all(contacts.map(async (contact) => {
      const chatType = Number(contact.chatType || 0);
      const guildId = String(contact.guildId || contact.channelId || "");
      const peer = { chatType, peerUid: String(contact.peerUid || ""), guildId };
      let latestMsg;
      try {
        const messageResult = await this.getMsgService()?.getMsgsByMsgId?.(peer, [String(contact.msgId || "")]);
        const raw = messageResult?.msgList?.[0];
        if (raw) latestMsg = await this.toOneBotEvent(raw);
      } catch {
      }
      return {
        lastestMsg: latestMsg,
        peerUin: String(contact.peerUin || await this.resolveUin(contact.peerUid)),
        peerUid: String(contact.peerUid || ""),
        guildId,
        remark: this.displayText(contact.remark),
        msgTime: String(contact.msgTime || ""),
        chatType,
        msgId: String(contact.msgId || ""),
        sendNickName: this.displayText(contact.sendNickName),
        sendMemberName: this.displayText(contact.sendMemberName),
        peerName: this.displayText(contact.peerName),
      };
    }));
  }
  displayText(value, seen = new Set()) {
    if (value === undefined || value === null) return "";
    if (["string", "number", "bigint"].includes(typeof value)) {
      const text = String(value).trim();
      return ["[object Map]", "[object Object]", "undefined", "null"].includes(text) ? "" : text;
    }
    if (typeof value !== "object" || seen.has(value)) return "";
    seen.add(value);
    const entries = value instanceof Map ? Array.from(value.entries()) : Object.entries(value);
    const preferred = ["remark", "name", "nickname", "nick", "card", "text", "value"];
    for (const key of preferred) {
      const item = entries.find(([entryKey]) => String(entryKey) === key);
      const display = item ? this.displayText(item[1], seen) : "";
      if (display) return display;
    }
    for (const [, item] of entries) {
      const display = this.displayText(item, seen);
      if (display) return display;
    }
    return "";
  }
  async getOnlineFileMessages(params) {
    const uid = await this.resolveUid(String(params.user_id || ""));
    const method = requireNativeMethod(this.getMsgService(), "getOnlineFileMsgs", "get_online_file_msg");
    const result = await method(this.peerFor("private", uid));
    checkNativeResult(result, "获取在线文件消息失败");
    return result?.msgList || [];
  }
  async manageOnlineFile(action, params) {
    const userId = String(params.user_id || "");
    const messageId = String(params.msg_id || params.message_id || "");
    const elementId = String(params.element_id || "");
    if (!userId || !messageId) {
      throw new OneBotActionError("在线文件操作缺少 user_id 或 msg_id", 1400, action);
    }
    const peer = this.peerFor("private", await this.resolveUid(userId));
    const service = this.getMsgService();
    if (action === "cancel_online_file") {
      const method = requireNativeMethod(service, "cancelSendMsg", action);
      checkNativeResult(await method(peer, messageId), "取消在线文件失败");
      return null;
    }
    if (!elementId) {
      throw new OneBotActionError("在线文件操作缺少 element_id", 1400, action);
    }
    const request = {
      msgId: messageId,
      peerUid: peer.peerUid,
      chatType: 1,
      elementId,
      downloadType: 1,
      downSourceType: 1,
    };
    const methodName = action === "receive_online_file"
      ? "getRichMediaElement"
      : "refuseGetRichMediaElement";
    const method = requireNativeMethod(service, methodName, action);
    const result = await method(request);
    checkNativeResult(result, action === "receive_online_file" ? "接收在线文件失败" : "拒绝在线文件失败");
    return result ?? null;
  }
  async sendOnlinePath(action, params) {
    const userId = String(params.user_id || "");
    if (!userId) throw new OneBotActionError("在线文件缺少 user_id", 1400, action);
    const source = String(params.file_path || params.folder_path || params.file || params.path || "").trim();
    if (!source) throw new OneBotActionError("在线文件缺少本地路径", 1400, action);
    const isFolder = action === "send_online_folder";
    let localPath;
    let temporary = false;
    if (isFolder) {
      localPath = source.startsWith("file://") ? decodeURIComponent(source.slice(7)) : source;
      if (os.platform() === "win32" && /^\/[A-Za-z]:/.test(localPath)) localPath = localPath.slice(1);
      localPath = path.resolve(localPath);
      if (!fs.existsSync(localPath) || !fs.statSync(localPath).isDirectory()) {
        throw new OneBotActionError("在线文件夹不存在: " + localPath, 1404, action);
      }
    } else {
      const materialized = await this.materializeFile(source, path.extname(String(params.file_name || source)));
      localPath = materialized.path;
      temporary = materialized.temporary;
    }
    try {
      const stat = fs.statSync(localPath);
      const fileName = String(
        params.file_name || params.folder_name || params.name || path.basename(localPath),
      );
      const result = await this.sendNativeElements("private", userId, [{
        elementType: isFolder ? 30 : 23,
        elementId: "",
        fileElement: {
          fileName,
          filePath: localPath,
          fileSize: isFolder ? "" : String(stat.size),
        },
      }]);
      checkNativeResult(result, isFolder ? "发送在线文件夹失败" : "发送在线文件失败");
      const rawId = String(result?.msgId || result?.messageId || result?.msg_id || Date.now());
      const privatePeerUid = String(result?.peerUid || await this.resolveUid(userId));
      const messageId = toOneBotMessageId(rawId, result, 1, privatePeerUid);
      this.oneBotNativeMessageIds.set(String(messageId), rawId);
      return { message_id: messageId, element_id: String(result?.elementId || "") };
    } finally {
      if (temporary) this.removeTemporaryFile(localPath);
    }
  }
  async sendArkShare(action, params) {
    const type = action === "send_group_ark_share" || params.group_id !== undefined ? "group" : "private";
    const target = String(type === "group" ? params.group_id : params.user_id);
    const value = params.json ?? params.data ?? params.payload ?? params.content;
    if (value === undefined || value === null || value === "") {
      throw new OneBotActionError("Ark 分享缺少 json/data/content", 1400, action);
    }
    return this.sendOneBotMessage(type, target, [{ type: "json", data: { data: value } }], true);
  }
  async restartEmbeddedQq() {
    setTimeout(() => process.exit(75), 150);
    return {};
  }
  async uploadOneBotFile(action, params) {
    const type = action === "upload_group_file" ? "group" : "private";
    const target = String(type === "group" ? params.group_id : params.user_id);
    const materialized = await this.materializeFile(String(params.file || ""), path.extname(String(params.name || params.file || "")));
    try {
      const stat = fs.statSync(materialized.path);
      const element = {
        elementType: 3,
        elementId: "",
        fileElement: {
          fileName: String(params.name || path.basename(materialized.path)),
          folderId: String(params.folder || params.folder_id || ""),
          filePath: materialized.path,
          fileSize: String(stat.size),
        },
      };
      const result = await this.sendNativeElements(type, target, [element]);
      checkNativeResult(result, "上传文件失败");
      const fileId = String(result?.fileUuid || result?.file_id || result?.elementId || result?.msgId || "");
      return { file_id: fileId || null };
    } finally {
      if (materialized.temporary) this.removeTemporaryFile(materialized.path);
    }
  }
  groupFileItems(result) {
    const items = result?.items || result?.item || result?.fileList || result?.groupFileListResult?.item || [];
    return Array.from(items instanceof Map ? items.values() : items || []);
  }
  oneBotGroupFileItem(groupId, item) {
    const file = item?.fileInfo || item?.file || item;
    return {
      group_id: Number(groupId) || groupId,
      file_id: String(file.fileId || file.fileUuid || file.id || ""),
      file_name: String(file.fileName || file.name || ""),
      busid: Number(file.busId || file.busid || 0),
      size: Number(file.fileSize || file.size || 0),
      file_size: Number(file.fileSize || file.size || 0),
      upload_time: Number(file.uploadTime || file.modifyTime || 0),
      dead_time: Number(file.deadTime || file.expireTime || 0),
      modify_time: Number(file.modifyTime || 0),
      download_times: Number(file.downloadTimes || 0),
      uploader: Number(file.uploaderUin || file.uploader || 0),
      uploader_name: String(file.uploaderName || ""),
    };
  }
  oneBotGroupFolderItem(groupId, item) {
    const folder = item?.folderInfo || item?.folder || item;
    return {
      group_id: Number(groupId) || groupId,
      folder_id: String(folder.folderId || folder.id || ""),
      folder: String(folder.folderId || folder.id || ""),
      folder_name: String(folder.folderName || folder.name || ""),
      create_time: Number(folder.createTime || 0),
      creator: Number(folder.createUin || folder.creatorUin || folder.creator || 0),
      creator_name: String(folder.creatorName || ""),
      total_file_count: Number(folder.totalFileCount || folder.fileCount || 0),
    };
  }
  async getGroupFiles(action, params) {
    const groupId = String(params.group_id || "");
    const service = this.session?.getRichMediaService?.();
    if (action === "get_group_file_system_info") {
      const countMethod = requireNativeMethod(service, "batchGetGroupFileCount", action);
      const [countResult, listResult] = await Promise.all([
        countMethod([groupId]),
        this.fetchGroupFilePage(groupId, { sortType: 1, fileCount: 1, startIndex: 0, sortOrder: 1, showOnlinedocFolder: 0 }, action),
      ]);
      checkNativeResult(countResult, "获取群文件数量失败");
      const space = listResult?.groupSpaceResult || listResult?.groupFileListResult?.groupSpaceResult || {};
      return {
        file_count: Number(countResult?.groupFileCounts?.[0] || 0),
        limit_count: 10000,
        used_space: Number(space.usedSpace || 0),
        total_space: Number(space.totalSpace || 0),
      };
    }
    const request = {
      sortType: 1,
      fileCount: Math.min(200, Math.max(1, Number(params.file_count || 50))),
      startIndex: Number(params.start_index || 0),
      sortOrder: 2,
      showOnlinedocFolder: 0,
      folderId: action === "get_group_files_by_folder" ? String(params.folder || params.folder_id || "") : "",
    };
    const items = [];
    for (let page = 0; page < 200 && items.length < request.fileCount; page += 1) {
      const result = await this.fetchGroupFilePage(groupId, request, action);
      const pageItems = this.groupFileItems(result);
      if (!pageItems.length) break;
      items.push(...pageItems);
      if (result?.isEnd || result?.groupFileListResult?.isEnd || items.length >= request.fileCount) break;
      const nextIndex = result?.nextIndex ?? result?.groupFileListResult?.nextIndex;
      if (nextIndex === undefined || Number(nextIndex) === Number(request.startIndex)) break;
      request.startIndex = Number(nextIndex);
    }
    return {
      files: items.filter((item) => item?.fileInfo || item?.file || item?.fileId || item?.fileUuid).map((item) => this.oneBotGroupFileItem(groupId, item)),
      folders: items.filter((item) => item?.folderInfo || item?.folder).map((item) => this.oneBotGroupFolderItem(groupId, item)),
    };
  }
  groupFilePayload(result) {
    if (!result || typeof result !== "object") return undefined;
    if (result.item !== undefined || result.items !== undefined || result.groupSpaceResult !== undefined) return result;
    if (result.groupFileListResult !== undefined) return result.groupFileListResult;
    return undefined;
  }
  async fetchGroupFilePage(groupId, request, action) {
    const service = this.session?.getRichMediaService?.();
    const method = requireNativeMethod(service, "getGroupFileList", action);
    const waited = await this.waitForNativeEvent(
      "group_file_info",
      () => method(String(groupId), { ...request }),
      (...args) => args.some((value) => this.groupFilePayload(value) !== undefined),
      (result) => this.groupFilePayload(result) !== undefined,
    );
    if (waited.direct !== null) {
      checkNativeResult(waited.direct, "获取群文件列表失败");
      return this.groupFilePayload(waited.direct);
    }
    return waited.args.map((value) => this.groupFilePayload(value)).find(Boolean) || {};
  }
  async deleteGroupFile(params) {
    const service = this.session?.getRichMediaService?.();
    const method = requireNativeMethod(service, "deleteGroupFile", "delete_group_file");
    const result = await method(String(params.group_id), [Number(params.busid || params.bus_id || 0)], [String(params.file_id || "")]);
    checkNativeResult(result, "删除群文件失败");
    return result || {};
  }
  async deleteGroupFolder(params) {
    const service = this.session?.getRichMediaService?.();
    const method = requireNativeMethod(service, "deleteGroupFolder", "delete_group_folder");
    const result = await method(String(params.group_id), String(params.folder || params.folder_id || ""));
    checkNativeResult(result?.groupFileCommonResult || result, "删除群文件夹失败");
    return result?.groupFileCommonResult || result || {};
  }
  async manageGroupFile(action, params) {
    const groupId = String(params.group_id || "");
    const fileId = String(params.file_id || "");
    if (!groupId || !fileId) {
      throw new OneBotActionError("群文件操作缺少 group_id 或 file_id", 1400, action);
    }
    const service = this.session?.getRichMediaService?.();
    let result;
    if (action === "move_group_file") {
      const method = requireNativeMethod(service, "moveGroupFile", action);
      result = await method(
        groupId,
        [Number(params.busid || params.bus_id || 102)],
        [fileId],
        String(params.current_parent_directory || params.current_folder || "/"),
        String(params.target_parent_directory || params.target_folder || "/"),
      );
      checkNativeResult(result?.moveGroupFileResult?.result || result, "移动群文件失败");
    } else if (action === "rename_group_file") {
      const newName = String(params.new_name || params.name || "");
      if (!newName) throw new OneBotActionError("重命名群文件缺少 new_name", 1400, action);
      const method = requireNativeMethod(service, "renameGroupFile", action);
      result = await method(
        groupId,
        Number(params.busid || params.bus_id || 102),
        fileId,
        String(params.current_parent_directory || params.current_folder || "/"),
        newName,
      );
      checkNativeResult(result?.renameGroupFileResult?.result || result, "重命名群文件失败");
    } else {
      const method = requireNativeMethod(service, "transGroupFile", action);
      result = await method(groupId, fileId);
      checkNativeResult(result?.transGroupFileResult?.result || result, "转存群文件失败");
    }
    return { ok: true, result: result || {} };
  }
  removeTemporaryFile(filePath) {
    try {
      fs.unlinkSync(filePath);
    } catch {
    }
  }
  async getOneBotFileUrl(action, params) {
    const fileId = String(params.file_id || params.file || "");
    const cached = this.oneBotFiles.get(fileId);
    if (cached?.url) return { url: cached.url };
    const service = this.session?.getRichMediaService?.();
    const methodName = action === "get_group_file_url" ? "getGroupFileUrl" : "getPrivateFileUrl";
    if (typeof service?.[methodName] === "function") {
      const result = await service[methodName](params);
      return { url: String(result?.url || result || "") };
    }
    throw new OneBotActionError("当前 QQ 版本无法直接生成该文件下载地址", 1405, action);
  }
  async getLocalOneBotFile(params) {
    const key = String(params.file || params.file_id || "");
    const cached = this.oneBotFiles.get(key);
    const candidate = String(cached?.path || cached?.url || key);
    if (!candidate) throw new OneBotActionError("缺少文件标识", 1400, "get_file");
    if (/^https?:\/\//i.test(candidate)) return { file: "", url: candidate, file_name: path.basename(new URL(candidate).pathname) };
    const materialized = await this.materializeFile(candidate, path.extname(candidate));
    const stat = fs.statSync(materialized.path);
    return {
      file: materialized.path,
      url: materialized.path,
      file_size: String(stat.size),
      file_name: path.basename(materialized.path),
      base64: this.asBoolean(params.base64) ? fs.readFileSync(materialized.path).toString("base64") : undefined,
    };
  }
  async downloadOneBotFile(params) {
    const source = params.base64
      ? "base64://" + String(params.base64)
      : String(params.url || params.file || params.file_id || "");
    if (!source) throw new OneBotActionError("下载文件缺少 url 或 base64", 1400, "download_file");
    const materialized = await this.materializeFile(
      source,
      path.extname(String(params.name || source)),
      this.parseOneBotHeaders(params.headers),
    );
    let filePath = materialized.path;
    if (materialized.temporary && params.name) {
      const safeName = path.basename(String(params.name)).replace(/[^A-Za-z0-9._-]/g, "_") || "download.bin";
      const renamed = path.join(os.tmpdir(), "elaina_" + process.pid + "_" + Date.now() + "_" + safeName);
      fs.renameSync(filePath, renamed);
      filePath = renamed;
    }
    if (materialized.temporary) this.oneBotStreamFiles.add(filePath);
    return { file: filePath };
  }
  async resolveOneBotStreamFile(params, action) {
    const key = String(params.file || params.file_id || params.url || "");
    const cached = this.oneBotFiles.get(key);
    const candidate = String(cached?.path || cached?.url || key);
    if (!candidate) throw new OneBotActionError("文件流缺少 file 或 file_id", 1400, action);
    const materialized = await this.materializeFile(candidate, path.extname(candidate));
    if (materialized.temporary) this.oneBotStreamFiles.add(materialized.path);
    return materialized.path;
  }
  async downloadOneBotFileStream(action, params) {
    const filePath = await this.resolveOneBotStreamFile(params, action);
    const stat = fs.statSync(filePath);
    if (stat.size > 5 * 1024 * 1024) {
      throw new OneBotActionError("内置连接单次文件流最大支持 5 MB", 1400, action);
    }
    const chunkSize = Math.min(1024 * 1024, Math.max(4096, Number(params.chunk_size || 64 * 1024)));
    const buffer = fs.readFileSync(filePath);
    const packets = [{
      type: "stream",
      data_type: "file_info",
      file_name: path.basename(filePath),
      file_size: stat.size,
      chunk_size: chunkSize,
    }];
    for (let offset = 0, index = 0; offset < buffer.length; offset += chunkSize, index += 1) {
      packets.push({
        type: "stream",
        data_type: "file_chunk",
        index,
        data: buffer.subarray(offset, offset + chunkSize).toString("base64"),
      });
    }
    return {
      type: "response",
      data_type: "file_complete",
      total_chunks: Math.ceil(buffer.length / chunkSize),
      total_bytes: buffer.length,
      packets,
    };
  }
  oneBotStreamStatus(stream, status = "file_created") {
    return {
      type: "stream",
      stream_id: stream.id,
      status,
      received_chunks: stream.chunks.size,
      total_chunks: stream.totalChunks,
    };
  }
  cleanupOneBotStream(streamId) {
    const stream = this.oneBotFileStreams.get(streamId);
    if (!stream) return;
    clearTimeout(stream.timeoutId);
    stream.chunks.clear();
    this.oneBotFileStreams.delete(streamId);
  }
  cleanOneBotStreams() {
    for (const streamId of this.oneBotFileStreams.keys()) this.cleanupOneBotStream(streamId);
    for (const filePath of this.oneBotStreamFiles) this.removeTemporaryFile(filePath);
    this.oneBotStreamFiles.clear();
  }
  async uploadOneBotFileStream(params) {
    const streamId = String(params.stream_id || "");
    if (!streamId) throw new OneBotActionError("文件流缺少 stream_id", 1400, "upload_file_stream");
    if (this.asBoolean(params.reset)) {
      this.cleanupOneBotStream(streamId);
      return { type: "response", stream_id: streamId, status: "stream_reset" };
    }
    let stream = this.oneBotFileStreams.get(streamId);
    if (!stream) {
      const totalChunks = Number(params.total_chunks || 0);
      if (!Number.isInteger(totalChunks) || totalChunks < 1 || totalChunks > 10000) {
        throw new OneBotActionError("新文件流需要 1 到 10000 的 total_chunks", 1400, "upload_file_stream");
      }
      stream = {
        id: streamId,
        filename: path.basename(String(params.filename || "upload_" + streamId + ".bin")),
        totalChunks,
        fileSize: Number(params.file_size || 0),
        expectedSha256: String(params.expected_sha256 || "").toLowerCase(),
        fileRetention: Math.max(0, Number(params.file_retention ?? 5 * 60 * 1000)),
        chunks: new Map(),
        timeoutId: setTimeout(() => this.cleanupOneBotStream(streamId), 10 * 60 * 1000),
      };
      this.oneBotFileStreams.set(streamId, stream);
    }
    if (this.asBoolean(params.verify_only)) return this.oneBotStreamStatus(stream);
    if (params.chunk_data !== undefined && params.chunk_index !== undefined) {
      const chunkIndex = Number(params.chunk_index);
      if (!Number.isInteger(chunkIndex) || chunkIndex < 0 || chunkIndex >= stream.totalChunks) {
        throw new OneBotActionError("文件流分块序号无效", 1400, "upload_file_stream");
      }
      const chunk = Buffer.from(String(params.chunk_data), "base64");
      if (chunk.length > 10 * 1024 * 1024) {
        throw new OneBotActionError("单个文件流分块最大支持 10 MB", 1400, "upload_file_stream");
      }
      stream.chunks.set(chunkIndex, chunk);
    }
    const shouldComplete = this.asBoolean(params.is_complete) || stream.chunks.size === stream.totalChunks;
    if (!shouldComplete) return this.oneBotStreamStatus(stream, "chunk_received");
    if (stream.chunks.size !== stream.totalChunks) {
      throw new OneBotActionError("文件流仍有缺失分块", 1400, "upload_file_stream");
    }
    const ordered = [];
    for (let index = 0; index < stream.totalChunks; index += 1) {
      const chunk = stream.chunks.get(index);
      if (!chunk) throw new OneBotActionError("文件流缺少第 " + index + " 个分块", 1400, "upload_file_stream");
      ordered.push(chunk);
    }
    const buffer = Buffer.concat(ordered);
    if (stream.fileSize && buffer.length !== stream.fileSize) {
      throw new OneBotActionError("文件流大小与 file_size 不一致", 1400, "upload_file_stream");
    }
    const sha256 = createHash("sha256").update(buffer).digest("hex");
    if (stream.expectedSha256 && sha256 !== stream.expectedSha256) {
      throw new OneBotActionError("文件流 SHA256 校验失败", 1400, "upload_file_stream");
    }
    const safeName = stream.filename.replace(/[^A-Za-z0-9._-]/g, "_") || "upload.bin";
    const filePath = path.join(os.tmpdir(), "elaina_" + process.pid + "_" + Date.now() + "_" + safeName);
    fs.writeFileSync(filePath, buffer);
    const result = {
      type: "response",
      stream_id: streamId,
      status: "file_complete",
      received_chunks: stream.chunks.size,
      total_chunks: stream.totalChunks,
      file_path: filePath,
      file_size: buffer.length,
      sha256,
    };
    const retention = stream.fileRetention;
    this.cleanupOneBotStream(streamId);
    this.oneBotStreamFiles.add(filePath);
    if (retention > 0) {
      setTimeout(() => {
        this.removeTemporaryFile(filePath);
        this.oneBotStreamFiles.delete(filePath);
      }, retention);
    }
    return result;
  }
  async getClientKey() {
    const service = this.session?.getTicketService?.();
    const method = requireNativeMethod(service, "forceFetchClientKey", "get_clientkey");
    const result = await method("");
    checkNativeResult(result, "获取 ClientKey 失败");
    return { clientkey: String(result?.clientKey || result?.clientkey || "") };
  }
  async getDomainPskey(domain) {
    const service = this.session?.getTipOffService?.();
    const method = requireNativeMethod(service, "getPskey", "get_cookies");
    const result = await method([domain], true);
    checkNativeResult(result, "获取 p_skey 失败");
    return String(result?.domainPskeyMap?.get?.(domain) || result?.domainPskeyMap?.[domain] || "");
  }
  normalizeCredentialDomain(value) {
    const raw = String(value || "qun.qq.com").trim();
    try {
      const parsed = new URL(raw.includes("://") ? raw : "https://" + raw);
      if (!parsed.hostname || !/^[a-z0-9.-]+$/i.test(parsed.hostname)) throw new Error("无效的主机名");
      return parsed.hostname;
    } catch {
      throw new OneBotActionError("domain 不是有效的域名", 1400, "get_cookies");
    }
  }
  async fetchHttpCookies(requestUrl, redirects = 5) {
    const client = requestUrl.startsWith("https:") ? https : http;
    return new Promise((resolve, reject) => {
      const request = client.get(requestUrl, (response) => {
        const cookies = {};
        for (const header of response.headers["set-cookie"] || []) {
          const pair = String(header).split(";", 1)[0] || "";
          const separator = pair.indexOf("=");
          if (separator <= 0) continue;
          const key = pair.slice(0, separator);
          const value = pair.slice(separator + 1);
          if (key && value) cookies[key] = value;
        }
        response.resume();
        response.on("end", async () => {
          try {
            if ([301, 302, 307, 308].includes(Number(response.statusCode)) && response.headers.location) {
              if (redirects <= 0) throw new Error("获取 Cookie 时重定向次数过多");
              const redirectUrl = new URL(response.headers.location, requestUrl).href;
              resolve({ ...cookies, ...await this.fetchHttpCookies(redirectUrl, redirects - 1) });
              return;
            }
            if (Number(response.statusCode || 0) >= 400) {
              throw new Error("获取 Cookie 失败: HTTP " + response.statusCode);
            }
            resolve(cookies);
          } catch (error) {
            reject(error);
          }
        });
      });
      request.setTimeout(10_000, () => request.destroy(new Error("获取 Cookie 超时")));
      request.on("error", reject);
    });
  }
  async fetchOneBotCookies(domain) {
    const normalizedDomain = this.normalizeCredentialDomain(domain);
    const { clientkey } = await this.getClientKey();
    if (!clientkey) throw new OneBotActionError("QQNT 未返回 ClientKey", 1500, "get_cookies");
    const selfUin = String(this.getSelfUin());
    const target = "https://" + normalizedDomain + "/" + selfUin + "/infocenter";
    const requestUrl = "https://ssl.ptlogin2.qq.com/jump?ptlang=1033&clientuin=" + encodeURIComponent(selfUin)
      + "&clientkey=" + encodeURIComponent(clientkey)
      + "&u1=" + encodeURIComponent(target) + "&keyindex=19%27";
    const cookies = await this.fetchHttpCookies(requestUrl);
    if (!cookies.p_skey) {
      try {
        cookies.p_skey = await this.getDomainPskey(normalizedDomain);
      } catch {
      }
    }
    return { domain: normalizedDomain, cookies };
  }
  bknFromSkey(skey) {
    let hash = 5381;
    for (const char of String(skey || "")) hash += (hash << 5) + char.charCodeAt(0);
    return hash & 2147483647;
  }
  async getOneBotCredentials(action, params = {}) {
    const { domain, cookies: cookieMap } = await this.fetchOneBotCookies(params.domain || "qun.qq.com");
    const cookies = Object.entries(cookieMap).map(([key, value]) => key + "=" + value).join("; ");
    const skey = String(cookieMap.skey || "");
    if (action === "get_cookies") {
      const source = domain.includes("qzone.qq.com") && cookieMap.p_skey ? cookieMap.p_skey : skey;
      return { cookies, bkn: source ? String(this.bknFromSkey(source)) : "" };
    }
    if (!skey) throw new OneBotActionError("QQ 登录 Cookie 中缺少 skey", 1500, action);
    const token = this.bknFromSkey(skey);
    if (action === "get_csrf_token") return { token };
    return { cookies, token };
  }
  async getProfileLike(params) {
    const userId = String(params.user_id || this.getSelfUin());
    const uid = userId === String(this.getSelfUin()) ? String(this.selfInfo?.uid || "") : await this.resolveUid(userId);
    const service = this.session?.getProfileLikeService?.();
    const method = requireNativeMethod(service, "getBuddyProfileLike", "get_profile_like");
    const result = await method({
      friendUid: uid,
      start: Number(params.start || 0),
      count: Number(params.count || 10),
      type: userId === String(this.getSelfUin()) ? 2 : 1,
    });
    checkNativeResult(result, "获取资料点赞失败");
    return result?.info?.userLikeInfos?.[0] || result?.info || result;
  }
  async getGroupNotice(params) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getGroupBulletin", "get_group_notice");
    const result = await method(String(params.group_id));
    const feeds = result?.feeds || result?.data?.feeds || result?.bulletins || result || [];
    const values = Array.isArray(feeds) ? feeds : Object.values(feeds || {});
    return values.filter(Boolean).map((notice) => ({
      notice_id: String(notice.fid || notice.noticeId || notice.id || ""),
      sender_id: Number(notice.u || notice.senderUin || 0),
      publish_time: Number(notice.pubt || notice.publishTime || 0),
      message: {
        text: String(notice?.msg?.text || notice.text || ""),
        image: Array.from(notice?.msg?.pics || notice.images || []),
        images: Array.from(notice?.msg?.pics || notice.images || []),
      },
      settings: notice.settings,
      read_num: Number(notice.read_num || notice.readNum || 0),
    }));
  }
  async deleteGroupNotice(params) {
    const groupId = String(params.group_id || "");
    const noticeId = String(params.notice_id || params.fid || "");
    if (!groupId || !noticeId) {
      throw new OneBotActionError("删除群公告缺少 group_id 或 notice_id", 1400, "_del_group_notice");
    }
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "deleteGroupBulletin", "_del_group_notice");
    const pskey = await this.getDomainPskey("qun.qq.com");
    const result = await method(groupId, pskey, noticeId);
    checkNativeResult(result, "删除群公告失败");
    return result || {};
  }
  async sendGroupNotice(params) {
    const groupId = String(params.group_id || "");
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "publishGroupBulletin", "send_group_notice");
    const pskey = await this.getDomainPskey("qun.qq.com");
    const result = await method(groupId, pskey, {
      text: encodeURI(String(params.content || "")),
      picInfo: undefined,
      oldFeedsId: "",
      pinned: Number(params.pinned || 0),
      confirmRequired: Number(params.confirm_required || 0),
    });
    checkNativeResult(result, "发布群公告失败");
    return {};
  }
  async getRobotUinRange() {
    const service = this.session?.getRobotService?.();
    const method = requireNativeMethod(service, "getRobotUinRange", "get_robot_uin_range");
    const result = await method({ justFetchMsgConfig: "1", type: 1, version: 0, aioKeywordVersion: 0 });
    return result?.response?.robotUinRanges || [];
  }
  async getCollectionList(params) {
    const service = this.session?.getCollectionService?.();
    const method = requireNativeMethod(service, "getCollectionItemList", "get_collection_list");
    const result = await method({
      category: Number(params.category || 0),
      groupId: -1,
      forceSync: true,
      forceFromDb: false,
      timeStamp: String(params.time_stamp || "0"),
      count: Math.min(100, Math.max(1, Number(params.count || 50))),
      searchDown: true,
    });
    checkNativeResult(result, "获取收藏列表失败");
    return result;
  }
  async createCollection(params) {
    const service = this.session?.getCollectionService?.();
    const method = requireNativeMethod(service, "createNewCollectionItem", "create_collection");
    const now = String(Date.now());
    const result = await method({
      commInfo: {
        bid: 1,
        category: 2,
        author: {
          type: 1,
          numId: String(this.getSelfUin()),
          strId: String(this.getSelfNick()),
          groupId: "0",
          groupName: "",
          uid: String(this.selfInfo?.uid || ""),
        },
        customGroupId: "0",
        createTime: now,
        sequence: now,
      },
      richMediaSummary: {
        originalUri: "",
        publisher: "",
        richMediaVersion: 0,
        subTitle: "",
        title: "",
        brief: String(params.brief || ""),
        picList: [],
        contentType: 1,
      },
      richMediaContent: {
        rawData: String(params.rawData ?? params.raw_data ?? ""),
        bizDataList: [],
        picList: [],
        fileList: [],
      },
      need_share_url: false,
    });
    checkNativeResult(result, "创建收藏失败");
    return result || {};
  }
  async getQunAlbumList(params) {
    const service = this.session?.getAlbumService?.();
    const method = requireNativeMethod(service, "getAlbumList", "get_qun_album_list");
    const result = await method({
      qun_id: String(params.group_id || ""),
      attach_info: String(params.attach_info || ""),
      seq: Date.now(),
      request_time_line: { request_invoke_time: String(Date.now()) },
    });
    const response = result?.response || result || {};
    if (Number(response.result || 0) !== 0) throw new OneBotActionError(response.errMs || "获取群相册失败", Number(response.result || 1400));
    return {
      album_list: response.album_list || [],
      attach_info: String(response.attach_info || ""),
      has_more: Boolean(response.has_more),
    };
  }
  async getGroupAlbumMediaList(params) {
    const service = this.session?.getAlbumService?.();
    const method = requireNativeMethod(service, "getMediaList", "get_group_album_media_list");
    const result = await method({
      qun_id: String(params.group_id || ""),
      album_id: String(params.album_id || ""),
      attach_info: String(params.attach_info || ""),
      seq: Date.now(),
      request_time_line: { request_invoke_time: String(Date.now()) },
    });
    const response = result?.response || result || {};
    if (Number(response.result || 0) !== 0) throw new OneBotActionError(response.errMs || "获取群相册媒体失败", Number(response.result || 1400));
    return response;
  }
  async setGroupAlbumMediaLike(params) {
    const service = this.session?.getAlbumService?.();
    const method = requireNativeMethod(service, "doQunLike", "set_group_album_media_like");
    const like = this.asBoolean(params.set ?? params.like, true);
    const groupId = String(params.group_id || "");
    const albumId = String(params.album_id || "");
    const batchId = String(params.batch_id || "");
    const lloc = String(params.lloc || "");
    const uin = String(this.getSelfUin());
    const id = lloc
      ? "421_1_0_" + groupId + "|" + albumId + "|" + batchId + "^||^421_1_0_" + groupId + "|" + albumId + "|" + lloc + "^||^0"
      : "421_1_0_" + groupId + "|" + albumId + "|" + batchId;
    return await method(
      Date.now(),
      { map_info: [], map_bytes_info: [], map_user_account: [] },
      like ? 2 : 1,
      { id, status: like ? 0 : 1 },
      {
        cell_common: { time: Date.now(), feed_id: "422_0_" + batchId },
        cell_user_info: { user: { uin } },
        cell_media: { album_id: albumId, batch_id: batchId },
        cell_qun_info: { qun_id: groupId },
      },
    );
  }
  async deleteGroupAlbumMedia(params) {
    const groupId = String(params.group_id || "");
    const albumId = String(params.album_id || "");
    const mediaId = String(params.lloc || params.media_id || "");
    if (!groupId || !albumId || !mediaId) {
      throw new OneBotActionError("删除群相册媒体缺少必要参数", 1400, "del_group_album_media");
    }
    const service = this.session?.getAlbumService?.();
    const method = requireNativeMethod(service, "deleteMedias", "del_group_album_media");
    const result = await method(Date.now(), groupId, albumId, [mediaId], []);
    checkNativeResult(result?.response || result, "删除群相册媒体失败");
    return result || {};
  }
  async commentGroupAlbumMedia(params) {
    const groupId = String(params.group_id || "");
    const albumId = String(params.album_id || "");
    const mediaId = String(params.lloc || params.media_id || "");
    const content = String(params.content || "");
    if (!groupId || !albumId || !mediaId || !content) {
      throw new OneBotActionError("群相册评论缺少必要参数", 1400, "do_group_album_comment");
    }
    const service = this.session?.getAlbumService?.();
    const method = requireNativeMethod(service, "doQunComment", "do_group_album_comment");
    const uin = String(this.getSelfUin());
    const result = await method(
      Date.now(),
      { map_info: [], map_bytes_info: [], map_user_account: [] },
      groupId,
      2,
      {
        cell_common: { time: "" },
        cell_user_info: { user: { uin } },
        cell_media: {
          album_id: albumId,
          batch_id: "",
          media_items: [{ image: { lloc: mediaId } }],
        },
      },
      {
        client_key: Date.now() * 1000,
        content: [{ type: 0, content, who: 0, uid: "", name: "", url: "" }],
        user: { uin },
      },
    );
    checkNativeResult(result?.response || result, "发表群相册评论失败");
    return result || {};
  }
  async callFlashTransferAction(action, params) {
    const service = this.session?.getFlashTransferService?.();
    const fileSetId = String(params.fileset_id || params.fileSetId || "");
    if (action === "get_fileset_id") {
      const method = requireNativeMethod(service, "getFileSetIdByCode", action);
      const code = String(params.share_code || "").split("=").pop() || "";
      const result = await method(code);
      checkNativeResult(result, "获取文件集 ID 失败");
      return { fileset_id: String(result?.fileSetId || "") };
    }
    if (action === "get_fileset_info") {
      const method = requireNativeMethod(service, "getFileSet", action);
      const result = await method({ fileSetId });
      checkNativeResult(result, "获取文件集信息失败");
      return result;
    }
    if (action === "get_share_link") {
      const method = requireNativeMethod(service, "getShareLinkReq", action);
      const result = await method(fileSetId);
      checkNativeResult(result, "获取分享链接失败");
      return result;
    }
    const listMethod = requireNativeMethod(service, "getFileList", action);
    const listResult = await listMethod({
      seq: 0,
      fileSetId,
      isUseCache: false,
      sceneType: 1,
      reqInfos: [{
        count: 100,
        paginationInfo: {},
        parentId: "",
        reqIndexPath: "",
        reqDepth: 3,
        filterCondition: { fileCategory: 0, filterType: 0 },
        sortConditions: [{ sortField: 0, sortOrder: 0 }],
        isNeedPhysicalInfoReady: false,
      }],
    });
    const response = listResult?.rsp || listResult || {};
    if (Number(response.result || 0) !== 0) throw new OneBotActionError(response.errMs || "获取闪传文件失败", Number(response.result || 1400));
    if (action === "get_flash_file_list") return response;
    const files = Array.from(response.fileLists || []).flatMap((folder) => folder?.fileList || []);
    const file = params.file_name
      ? files.find((item) => String(item.name) === String(params.file_name))
      : files[Number(params.file_index || 0)];
    if (!file) throw new OneBotActionError("闪传文件不存在", 1404, action);
    const urlMethod = requireNativeMethod(service, "startFileTransferUrl", action);
    const result = await urlMethod(file);
    return { url: String(result?.url || ""), expire_timestamp: String(result?.expireTimestampSeconds || "") };
  }
  async downloadFileset(params) {
    const fileSetId = String(params.fileset_id || params.fileSetId || "");
    if (!fileSetId) throw new OneBotActionError("下载文件集缺少 fileset_id", 1400, "download_fileset");
    const service = this.session?.getFlashTransferService?.();
    const method = requireNativeMethod(service, "startFileSetDownload", "download_fileset");
    const result = await method(fileSetId, 1, { isIncludeCompressInnerFiles: false });
    checkNativeResult(result, "下载文件集失败");
    return result || {};
  }
  async callFlashTransferMutation(action, params) {
    const service = this.session?.getFlashTransferService?.();
    if (action === "send_flash_msg") {
      const fileSetId = String(params.fileset_id || params.fileSetId || "");
      if (!fileSetId) throw new OneBotActionError("闪传消息缺少 fileset_id", 1400, action);
      const type = params.group_id !== undefined ? "group" : "private";
      const target = String(type === "group" ? params.group_id : params.user_id);
      if (!target) throw new OneBotActionError("闪传消息缺少发送目标", 1400, action);
      const peerUid = type === "private" ? await this.resolveUid(target) : target;
      const method = requireNativeMethod(service, "sendFlashTransferMsg", action);
      const result = await method({
        fileSetId,
        targets: [{ destUid: peerUid, destType: type === "group" ? 2 : 1 }],
      });
      const code = Number(result?.errCode ?? 0);
      if (code !== 0) throw new OneBotActionError(String(result?.errMsg || "发送闪传消息失败"), code, action);
      return result?.rsp || result || {};
    }

    const values = Array.isArray(params.files) ? params.files : [params.files ?? params.file];
    const sources = values.map((value) => String(value || "").trim()).filter(Boolean);
    if (!sources.length) throw new OneBotActionError("闪传任务缺少 files", 1400, action);
    const paths = [];
    for (const source of sources) {
      if (!/^(?:https?:|data:|base64:|file:)/i.test(source)) {
        const localPath = path.resolve(source);
        if (fs.existsSync(localPath) && fs.statSync(localPath).isDirectory()) {
          paths.push(localPath);
          continue;
        }
      }
      paths.push((await this.materializeFile(source, path.extname(source))).path);
    }
    let coverPath = "";
    if (params.thumb_path) {
      coverPath = (await this.materializeFile(String(params.thumb_path), path.extname(String(params.thumb_path)))).path;
    }
    const method = requireNativeMethod(service, "createFlashTransferUploadTask", action);
    const timestamp = Date.now();
    const result = await method(timestamp, {
      screen: 1,
      name: String(params.name || ""),
      uploaders: [{
        uin: String(this.getSelfUin()),
        uid: String(this.selfInfo?.uid || ""),
        sendEntrance: "",
        nickname: String(this.getSelfNick()),
      }],
      coverPath,
      paths,
      excludePaths: [],
      expireLeftTime: 0,
      isNeedDelDeviceInfo: false,
      isNeedDelLocation: false,
      coverOriginalInfos: [{ path: paths[0] || "", thumbnailPath: coverPath }],
      uploadSceneType: 10,
      detectPrivacyInfoResult: { exists: false, allDetectResults: new Map() },
    });
    checkNativeResult(result, "创建闪传任务失败");
    return result || {};
  }
  async createGroupFileFolder(params) {
    const service = this.session?.getRichMediaService?.();
    const method = requireNativeMethod(service, "createGroupFolder", "create_group_file_folder");
    const result = await method(String(params.group_id || ""), String(params.name || params.folder_name || ""));
    checkNativeResult(result, "创建群文件夹失败");
    return result?.resultWithGroupItem || result || {};
  }
  async ocrImage(params) {
    const input = typeof params.image === "object" ? params.image?.file || params.image?.url : params.image;
    const file = await this.materializeFile(String(input || params.file || ""));
    try {
      const service = this.session?.getRichMediaService?.();
      const method = requireNativeMethod(service, "getScreenOCR", "ocr_image");
      return await method(file.path);
    } finally {
      if (file.temporary) this.removeTemporaryFile(file.path);
    }
  }
  async manageCustomFace(action, params) {
    const service = this.getMsgService();
    if (action === "fetch_custom_face" || action === "fetch_custom_face_detail") {
      const method = requireNativeMethod(service, "fetchFavEmojiList", action);
      const result = await method("", Math.min(200, Math.max(1, Number(params.count || 48))), true, true);
      checkNativeResult(result, "获取自定义表情失败");
      const list = Array.from(result?.emojiInfoList || []);
      return action === "fetch_custom_face" ? list.map((item) => String(item.url || "")) : list;
    }
    if (action === "add_custom_face") {
      const materialized = await this.materializeFile(String(params.file || ""));
      try {
        const file = fs.readFileSync(materialized.path);
        const stat = fs.statSync(materialized.path);
        const method = requireNativeMethod(service, "addFavEmoji", action);
        const result = await method({
          emojiId: String(params.emoji_id || ""),
          packageId: Number(params.package_id || 0),
          emojiPath: materialized.path,
          fileSize: String(params.file_size || stat.size),
          fileName: String(params.file_name || path.basename(materialized.path)),
          md5: String(params.md5 || createHash("md5").update(file).digest("hex")),
          isMarkFace: this.asBoolean(params.is_mark_face),
          isOrigin: this.asBoolean(params.is_origin, true),
        });
        checkNativeResult(result, "添加自定义表情失败");
        return result || {};
      } finally {
        if (materialized.temporary) this.removeTemporaryFile(materialized.path);
      }
    }
    if (action === "delete_custom_face") {
      const source = params.ids ?? params.res_id ?? params.id;
      const ids = (Array.isArray(source) ? source : [source]).map(String).filter(Boolean);
      if (!ids.length) throw new OneBotActionError("删除自定义表情缺少 res_id 或 ids", 1400, action);
      const method = requireNativeMethod(service, "deleteFavEmoji", action);
      const result = await method(ids);
      checkNativeResult(result, "删除自定义表情失败");
      return result || {};
    }
    const method = requireNativeMethod(service, "modifyFavEmojiDesc", action);
    const result = await method([{
      emojiId: Number(params.emoji_id || 0),
      resId: String(params.res_id || ""),
      md5: String(params.md5 || ""),
      desc: String(params.desc || ""),
    }]);
    checkNativeResult(result, "修改自定义表情描述失败");
    return result || {};
  }
  async translateWords(params) {
    const words = Array.isArray(params.words) ? params.words.map(String) : [];
    if (!words.length) throw new OneBotActionError("翻译接口缺少 words", 1400, "translate_en2zh");
    const service = this.session?.getRichMediaService?.();
    const method = requireNativeMethod(service, "translateEnWordToZn", "translate_en2zh");
    const result = await method(words);
    checkNativeResult(result, "翻译失败");
    return { words: Array.from(result?.words || []) };
  }
  async fetchPttText(params) {
    const { event, raw, nativeId } = this.getCachedMessage(params.message_id);
    const ptt = Array.from(raw?.elements || []).find((element) => Number(element?.elementType) === 4);
    if (!ptt) throw new OneBotActionError("消息中不包含语音", 1400, "fetch_ptt_text");
    const peer = this.peerForEvent(event, raw);
    const service = this.getMsgService();
    const translate = requireNativeMethod(service, "translatePtt2Text", "fetch_ptt_text");
    checkNativeResult(await translate(String(raw?.msgId || nativeId), peer, ptt), "语音转文字失败");
    const getMessages = requireNativeMethod(service, "getMsgsByMsgId", "fetch_ptt_text");
    const result = await getMessages(peer, [String(raw?.msgId || nativeId)]);
    checkNativeResult(result, "读取语音转文字结果失败");
    const message = result?.msgList?.[0];
    const translated = Array.from(message?.elements || []).find((element) => Number(element?.elementType) === 4);
    const text = String(translated?.pttElement?.text || "");
    if (!text) throw new OneBotActionError("语音转文字结果为空", 1404, "fetch_ptt_text");
    return { text };
  }
  async getOnlineClients() {
    const method = requireNativeMethod(this.getMsgService(), "getOnLineDev", "get_online_clients");
    this.oneBotOnlineClients = [];
    await method();
    await new Promise((resolve) => setTimeout(resolve, 500));
    return this.oneBotOnlineClients;
  }
  redPacketBillNo(wallet) {
    let billNo = wallet?.billNo || wallet?.grabedMsg?.billNo || wallet?.redBag?.billNo || "";
    if (!billNo && typeof wallet?.receiver?.nativeAndroid === "string") {
      const match = wallet.receiver.nativeAndroid.match(/(?:^|[?&])id=(\d+)/);
      if (match) billNo = match[1];
    }
    return String(billNo || "");
  }
  redPacketExclusiveIdentity(wallet) {
    const redBag = wallet?.redBag || {};
    const receiver = wallet?.receiver || {};
    const uinValue = redBag.receiveUin ?? redBag.receiverUin ?? receiver.uin ?? wallet?.exclusiveUin ?? "";
    const uidValue = redBag.receiveUid ?? redBag.receiverUid ?? receiver.uid ?? wallet?.exclusiveUid ?? "";
    const uinText = String(uinValue || "").trim();
    return {
      uin: /^\d+$/.test(uinText) && uinText !== "0" ? uinText : "",
      uid: String(uidValue || (!/^\d+$/.test(uinText) ? uinText : "") || "").trim()
    };
  }
  redPacketChannel(wallet) {
    const value = wallet?.redChannel ?? wallet?.redBag?.redChannel ?? wallet?.grabedMsg?.redChannel ?? wallet?.receiver?.redChannel ?? 0;
    const channel = Number(value);
    return Number.isFinite(channel) ? channel : 0;
  }
  redPacketType(wallet) {
    const candidates = [
      wallet?.redBag?.redBagType,
      wallet?.redBagType,
      wallet?.grabedMsg?.redBagType,
      wallet?.receiver?.redBagType,
      wallet?.redBag?.redType,
      wallet?.grabedMsg?.redType,
    ];
    for (const value of candidates) {
      const type = Number(value);
      if (Number.isFinite(type) && type >= 0) return Math.trunc(type);
    }
    const exclusive = this.redPacketExclusiveIdentity(wallet);
    return exclusive.uin || exclusive.uid ? 3 : 0;
  }
  redPacketPassword(wallet) {
    return String(
      wallet?.receiver?.title
      || wallet?.receiver?.notice
      || wallet?.redBag?.wording
      || wallet?.redBag?.authKey
      || wallet?.grabedMsg?.wording
      || ""
    ).trim();
  }
  rememberRedPacket(msg, wallet, event = null) {
    const billNo = this.redPacketBillNo(wallet);
    if (!billNo) return null;
    const existing = this.redPackets.get(billNo);
    if (existing) return null;
    const chatType = Number(msg?.chatType ?? 2);
    const peerUin = String(msg?.peerUin || "");
    const exclusive = this.redPacketExclusiveIdentity(wallet);
    const eventReceivedAtMs = Date.now();
    const rawSenderId = String(msg?.senderUin || "").trim();
    const eventSenderId = String(event?.user_id || "").trim();
    const senderId = rawSenderId && rawSenderId !== "0" ? rawSenderId : eventSenderId;
    const packet = {
      createdAt: eventReceivedAtMs,
      eventReceivedAtMs,
      billNo,
      wallet,
      peerUid: String(msg?.peerUid || ""),
      peerUin,
      groupId: chatType === 2 ? peerUin : "",
      groupName: String(msg?.peerName || ""),
      senderId,
      senderName: String(msg?.sendMemberName || msg?.sendNickName || ""),
      chatType,
      msgSeq: String(msg?.msgSeq || ""),
      redBagType: this.redPacketType(wallet),
      senderRole: Number(msg?.roleType ?? 4),
      wishing: String(wallet?.receiver?.title || wallet?.receiver?.notice || ""),
      password: this.redPacketPassword(wallet),
      redChannel: this.redPacketChannel(wallet),
      exclusiveUin: exclusive.uin,
      exclusiveUid: exclusive.uid
    };
    this.redPackets.set(billNo, packet);
    if (eventReceivedAtMs >= this.redPacketCleanupAt) {
      const cutoff = eventReceivedAtMs - 10 * 60 * 1e3;
      for (const [key, value] of this.redPackets) {
        if (value.createdAt < cutoff) this.redPackets.delete(key);
      }
      this.redPacketCleanupAt = eventReceivedAtMs + 60_000;
    }
    while (this.redPackets.size > 5e3) {
      this.redPackets.delete(this.redPackets.keys().next().value);
    }
    return packet;
  }
  emitRedPackets(msg, elements) {
    for (const element of elements) {
      if (!element?.walletElement) continue;
      const packet = this.rememberRedPacket(msg, element.walletElement);
      if (!packet) continue;
      this.redPacketCallback?.(this.redPacketPayload(packet));
    }
  }
  redPacketPayload(packet) {
    return {
      bill_no: packet.billNo,
      event_received_at_ms: packet.eventReceivedAtMs,
      peer_uid: packet.peerUid,
      peer_uin: packet.peerUin,
      group_id: packet.groupId,
      group_name: packet.groupName,
      sender_id: packet.senderId,
      sender_name: packet.senderName,
      chat_type: packet.chatType,
      msg_seq: packet.msgSeq,
      red_packet_type: packet.redBagType,
      sender_role: packet.senderRole,
      wishing: packet.wishing,
      password: packet.password,
      red_channel: packet.redChannel,
      exclusive_uin: packet.exclusiveUin
    };
  }
  async getRedPacketDetails(params = {}) {
    const billNo = String(params.bill_no || params.billNo || "");
    const packet = this.redPackets.get(billNo);
    if (!packet) {
      return { ok: false, err_code: -2, err_msg: "红包上下文不存在或已过期" };
    }
    const exclusive = this.redPacketExclusiveIdentity(packet.wallet);
    let exclusiveUin = exclusive.uin || String(packet.exclusiveUin || "");
    const exclusiveUid = exclusive.uid || String(packet.exclusiveUid || "");
    if (!exclusiveUin && exclusiveUid) {
      const resolved = String(await this.resolveUin(exclusiveUid) || "");
      if (/^\d+$/.test(resolved) && resolved !== "0") exclusiveUin = resolved;
    }
    packet.exclusiveUin = exclusiveUin;
    packet.exclusiveUid = exclusiveUid;
    return {
      ok: true,
      bill_no: packet.billNo,
      red_packet_type: packet.redBagType,
      red_channel: packet.redChannel,
      password_required: packet.redChannel === 32,
      password: packet.password,
      exclusive_uin: exclusiveUin,
      exclusive_uid: exclusiveUid
    };
  }
  async grabRedPacket(params = {}) {
    const billNo = String(params.bill_no || params.billNo || "");
    const packet = this.redPackets.get(billNo);
    if (!packet) {
      return { ok: false, amount: 0, err_code: -2, err_msg: "红包上下文不存在或已过期" };
    }
    const service = this.getMsgService();
    if (!service || typeof service.grabRedBag !== "function") {
      return { ok: false, amount: 0, err_code: -3, err_msg: "当前 QQ 协议不支持 grabRedBag" };
    }
    const selfUin = String(this.getSelfUin() || "");
    const request = {
      recvUin: packet.chatType === 1 ? selfUin : packet.groupId,
      recvType: packet.chatType,
      peerUid: packet.peerUid,
      name: String(this.getSelfNick() || selfUin),
      pcBody: packet.wallet?.pcBody,
      wishing: packet.wishing,
      msgSeq: packet.msgSeq,
      index: packet.wallet?.stringIndex
    };
    let timer;
    const nativeCallAtMs = Date.now();
    const timing = () => ({
      dispatch_delay_ms: Math.max(0, nativeCallAtMs - Number(packet.eventReceivedAtMs || nativeCallAtMs)),
      native_elapsed_ms: Math.max(0, Date.now() - nativeCallAtMs),
    });
    try {
      const timeout = Symbol("red-packet-timeout");
      const grabPromise = Promise.resolve(service.grabRedBag(request));
      if (params.send_password_after === true && packet.redChannel === 32
        && packet.groupId && packet.password) {
        // Native grab is invoked first. Password delivery is best-effort and never blocks it.
        void Promise.resolve()
          .then(() => this.sendGroupMsg(packet.groupId, packet.password))
          .catch(() => {});
      }
      const nativeResult = await Promise.race([
        grabPromise,
        new Promise((resolve) => {
          timer = setTimeout(() => resolve(timeout), 1800);
        })
      ]);
      if (nativeResult === timeout) {
        return { ok: false, amount: 0, err_code: -1, err_msg: "领取超时", ...timing() };
      }
      const response = nativeResult?.grabRedBagRsp || nativeResult || {};
      const amountFen = Number.parseInt(String(response?.recvdOrder?.amount || 0), 10) || 0;
      const errCode = Number(response?.retCode ?? response?.result ?? nativeResult?.result ?? 0);
      const errMsg = String(response?.retMsg || response?.errMsg || nativeResult?.errMsg || (errCode ? `错误码${errCode}` : ""));
      return {
        ok: errCode === 0, amount: amountFen / 100, err_code: errCode, err_msg: errMsg,
        ...timing(),
      };
    } catch (error) {
      return {
        ok: false, amount: 0, err_code: -4, err_msg: String(error?.message || error),
        ...timing(),
      };
    } finally {
      clearTimeout(timer);
    }
  }
  async clickInlineKeyboardButton(params = {}) {
    const service = this.getMsgService();
    if (!service || typeof service.clickInlineKeyboardButton !== "function") {
      throw new Error("当前 QQ 协议不支持 clickInlineKeyboardButton");
    }
    const result = await service.clickInlineKeyboardButton({
      buttonId: String(params.button_id || "1"),
      peerId: String(params.group_id || ""),
      botAppid: String(params.bot_appid || ""),
      msgSeq: String(params.msg_seq || Math.floor(Math.random() * 1e6)),
      callback_data: String(params.callback_data || ""),
      dmFlag: 0,
      chatType: 2
    });
    const resultCode = Number(result?.result ?? result?.retcode ?? 0);
    return {
      ok: Number.isFinite(resultCode) ? resultCode === 0 : true,
      result: Number.isFinite(resultCode) ? resultCode : 0,
      status: Number(result?.status ?? 0),
      prompt_text: String(result?.promptText || result?.errMsg || "")
    };
  }
  async sendOneBotMessage(type, target, message, autoEscape = false, elementContext = null) {
    if (!target || target === "undefined") throw new OneBotActionError("缺少消息目标", 1400);
    const segments = this.normalizeOneBotMessage(message, autoEscape);
    const nodeCount = segments.filter((segment) => String(segment?.type || "").toLowerCase() === "node").length;
    if (nodeCount) {
      if (nodeCount !== segments.length) {
        throw new OneBotActionError("合并转发 node 不能和普通消息段混合发送", 1400, "send_msg");
      }
      return this.sendOneBotForward(
        type === "group" ? "send_group_forward_msg" : "send_private_forward_msg",
        type === "group"
          ? { group_id: target, messages: segments }
          : { user_id: target, messages: segments },
      );
    }
    const elements = [];
    const temporaryFiles = [];
    try {
      for (const segment of segments) {
        const segmentType = String(segment.type || "").toLowerCase();
        const data = segment.data || {};
        if (segmentType === "text") {
          if (data.text !== void 0 && String(data.text)) elements.push(this.textElement(String(data.text)));
        } else if (segmentType === "at") {
          const contextType = String(elementContext?.type || type);
          const contextTarget = String(elementContext?.target || target);
          if (contextType !== "group") continue;
          elements.push(await this.atElement(contextTarget, String(data.qq || data.user_id || "")));
        } else if (segmentType === "reply") {
          elements.push(this.replyElement(data));
        } else if (segmentType === "face") {
          const faceIndex = Number(data.id);
          if (!Number.isInteger(faceIndex) || faceIndex < 0) throw new Error(`无效的表情 ID: ${data.id}`);
          elements.push({
            elementType: 6,
            elementId: "",
            faceElement: {
              faceIndex,
              faceType: faceIndex >= 222 ? 2 : 1,
              sourceType: 1,
              resultId: data.resultId === undefined ? undefined : String(data.resultId),
              chainCount: data.chainCount === undefined ? undefined : Number(data.chainCount),
            },
          });
        } else if (segmentType === "dice" || segmentType === "rps") {
          elements.push({
            elementType: 6,
            elementId: "",
            faceElement: {
              faceIndex: segmentType === "dice" ? 358 : 359,
              faceType: 3,
              faceText: segmentType === "dice" ? "[骰子]" : "[猜拳]",
              packId: "1",
              stickerId: segmentType === "dice" ? "33" : "34",
              stickerType: 2,
              sourceType: 1,
              resultId: data.result === undefined ? undefined : String(data.result),
            },
          });
        } else if (segmentType === "mface") {
          elements.push({
            elementType: 11,
            elementId: "",
            marketFaceElement: {
              emojiPackageId: Number(data.emoji_package_id || 0),
              emojiId: String(data.emoji_id || ""),
              key: String(data.key || ""),
              faceName: String(data.summary || "[商城表情]"),
            },
          });
        } else if (segmentType === "image") {
          const file = String(data.file || data.url || "");
          if (!file) throw new Error("图片消息缺少 file/url");
          const prepared = await this.imageElement(file, String(data.summary || ""), Number(data.sub_type || 0));
          elements.push(prepared.element);
          if (prepared.temporary) temporaryFiles.push(prepared.path);
        } else if (["file", "record", "video", "onlinefile"].includes(segmentType)) {
          const prepared = await this.fileLikeElement(segmentType, data);
          elements.push(prepared.element);
          if (prepared.temporary) temporaryFiles.push(prepared.path);
        } else if (segmentType === "json") {
          const content = typeof data.data === "string" ? data.data : JSON.stringify(data.data ?? data);
          elements.push(this.arkElement(content));
        } else if (segmentType === "forward") {
          const resId = String(data.res_id || data.resid || data.id || "");
          if (!resId) throw new OneBotActionError("forward 消息段缺少 id", 1400, "send_msg");
          elements.push(this.arkElement(JSON.stringify(this.forwardArkJson(resId, data))));
        } else if (segmentType === "contact") {
          elements.push(await this.contactElement(data));
        } else if (segmentType === "music") {
          elements.push(await this.musicElement(data));
        } else if (segmentType === "miniapp") {
          const content = typeof data.data === "string" ? data.data : JSON.stringify(data.data ?? data);
          if (!content) throw new OneBotActionError("miniapp 消息段缺少 data", 1400, "send_msg");
          elements.push(this.arkElement(content));
        } else if (segmentType === "xml") {
          elements.push({
            elementType: 13,
            elementId: "",
            structLongMsgElement: { xmlContent: String(data.data || data.xml || ""), resId: String(data.resid || "") },
          });
        } else if (segmentType === "markdown") {
          elements.push({
            elementType: 14,
            elementId: "",
            markdownElement: { content: String(data.content || data.data || "") },
          });
        } else if (segmentType === "location") {
          elements.push({
            elementType: 28,
            elementId: "",
            shareLocationElement: {
              text: String(data.title || data.content || data.address || "位置"),
              ext: JSON.stringify({
                lat: Number(data.lat || data.latitude || 0),
                lon: Number(data.lon || data.lng || data.longitude || 0),
                title: String(data.title || ""),
                content: String(data.content || data.address || ""),
              }),
            },
          });
        } else if (segmentType === "flashtransfer") {
          const fileSetId = String(data.fileset_id || data.fileSetId || "");
          if (!fileSetId) throw new OneBotActionError("闪传消息段缺少 fileset_id", 1400);
          elements.push({
            elementType: 14,
            elementId: "",
            markdownElement: {
              content: String(data.content || "[QQ闪传]"),
              mdExtInfo: { flashTransferInfo: { filesetId: fileSetId } },
            },
          });
        } else {
          throw new OneBotActionError(`内置 QQ 暂不支持消息段: ${segmentType || "unknown"}`, 1405);
        }
      }
      if (!elements.length) throw new Error("消息内容为空");
      const result = await this.sendNativeElements(type, target, elements);
      const rawId = String(result?.msgId || result?.messageId || result?.msg_id || Date.now());
      const fallbackPeerUid = type === "private" ? await this.resolveUid(target) : target;
      const messageId = toOneBotMessageId(rawId, result, type === "group" ? 2 : 1, fallbackPeerUid);
      this.oneBotNativeMessageIds.set(String(messageId), rawId);
      const event = createOneBotEvent(this.getSelfUin(), "message_sent", {
        time: Date.now(),
        message_type: type,
        sub_type: type === "group" ? "normal" : "friend",
        message_id: messageId,
        message_seq: messageId,
        real_id: messageId,
        real_seq: String(result?.msgSeq || ""),
        user_id: Number(this.getSelfUin()) || this.getSelfUin(),
        message: segments,
        raw_message: this.toOneBotRawMessage(segments).trim(),
        message_format: "array",
        message_sent_type: "self",
        font: 14,
        sender: {
          user_id: Number(this.getSelfUin()) || this.getSelfUin(),
          nickname: this.getSelfNick(),
          card: this.getSelfNick(),
        },
      });
      if (type === "group") event.group_id = Number(target) || target;
      else event.target_id = Number(target) || target;
      if (type === "group") event.target_id = Number(target) || target;
      const emitted = this.oneBotMessages.has(String(messageId));
      this.rememberOneBotMessage(event, rawId, result?.msgId ? result : result?.msg || result?.message || null);
      if (!emitted) this.oneBotEventCallback?.(event);
      return { message_id: messageId };
    } finally {
      for (const file of temporaryFiles) {
        try {
          fs.unlinkSync(file);
        } catch {
        }
      }
    }
  }
  normalizeOneBotMessage(message, autoEscape = false) {
    return normalizeOneBotMessage(message, autoEscape);
  }
  decodeCq(value) {
    return value.replace(/&#44;/g, ",").replace(/&#91;/g, "[").replace(/&#93;/g, "]").replace(/&amp;/g, "&");
  }
  textElement(content) {
    return {
      elementType: 1,
      elementId: "",
      textElement: { content, atType: 0, atUid: "", atTinyId: "", atNtUid: "" }
    };
  }
  arkElement(content) {
    return {
      elementType: 10,
      elementId: "",
      arkElement: { bytesData: String(content || ""), linkInfo: null, subElementType: null },
    };
  }
  forwardArkJson(resId, data = {}) {
    const id = String(data.uniseq || data.filename || randomUUID());
    const news = Array.isArray(data.news) && data.news.length
      ? data.news
      : [{ text: String(data.preview || "聊天记录") }];
    return {
      app: "com.tencent.multimsg",
      config: { autosize: 1, forward: 1, round: 1, type: "normal", width: 300 },
      desc: String(data.prompt || "[聊天记录]"),
      extra: { filename: id, tsum: Number(data.count || data.tsum || 0) },
      meta: {
        detail: {
          news,
          resid: String(resId),
          source: String(data.source || "聊天记录"),
          summary: String(data.summary || "查看转发消息"),
          uniseq: id,
        },
      },
      prompt: String(data.prompt || "[聊天记录]"),
      ver: "0.0.0.5",
      view: "contact",
    };
  }
  forwardArkData(value) {
    if (!value) return null;
    try {
      const data = typeof value === "string" ? JSON.parse(value) : value;
      return data?.app === "com.tencent.multimsg" && data?.meta?.detail?.resid ? data : null;
    } catch {
      return null;
    }
  }
  async contactElement(data) {
    const contactType = String(data.type || "qq").toLowerCase();
    const id = String(data.id || data.user_id || data.group_id || "");
    if (!id) throw new OneBotActionError("contact 消息段缺少 id", 1400, "send_msg");
    let result;
    if (contactType === "group") {
      const method = requireNativeMethod(this.session?.getGroupService?.(), "getGroupRecommendContactArkJson", "send_msg");
      result = await method(id);
    } else if (contactType === "qq" || contactType === "private") {
      const method = requireNativeMethod(this.session?.getBuddyService?.(), "getBuddyRecommendContactArkJson", "send_msg");
      result = await method(id, String(data.phone_number || ""));
    } else {
      throw new OneBotActionError(`不支持的 contact 类型: ${contactType}`, 1400, "send_msg");
    }
    checkNativeResult(result, "生成联系人卡片失败");
    const content = String(result?.arkMsg || result?.arkJson || result?.data?.arkMsg || result?.data?.arkJson || "");
    if (!content) throw new OneBotActionError("生成联系人卡片失败: Ark 内容为空", 1500, "send_msg");
    return this.arkElement(content);
  }
  async musicElement(data) {
    const supported = new Set(["qq", "163", "kugou", "kuwo", "migu", "custom"]);
    const musicType = String(data.type || "").toLowerCase();
    if (!supported.has(musicType)) {
      throw new OneBotActionError(`不支持的音乐平台: ${musicType || "empty"}`, 1400, "send_msg");
    }
    if (data.id === undefined && (!data.url || !data.image)) {
      throw new OneBotActionError("自定义音乐卡片必须提供 url 和 image", 1400, "send_msg");
    }
    const payload = data.id === undefined && data.content
      ? { ...data, singer: data.content, content: undefined }
      : data;
    const endpoint = String(process.env["ELAINAQQ_MUSIC_SIGN_URL"] || "https://ss.xingzhige.com/music_card/card");
    const response = await this.postJson(endpoint, payload);
    const content = typeof response === "string"
      ? response
      : response?.data && typeof response.data === "string"
        ? response.data
        : JSON.stringify(response?.data ?? response);
    if (!content) throw new OneBotActionError("音乐卡片签名服务返回空内容", 1500, "send_msg");
    return this.arkElement(content);
  }
  async postJson(url, data, timeout = 15000) {
    const payload = JSON.stringify(data ?? {});
    const client = url.startsWith("https:") ? (await import('https')).default : (await import('http')).default;
    return new Promise((resolve, reject) => {
      const request = client.request(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        },
      }, (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
          if (body.length > 8 * 1024 * 1024) request.destroy(new Error("响应内容过大"));
        });
        response.on("end", () => {
          const status = Number(response.statusCode || 0);
          if (status < 200 || status >= 300) {
            reject(new OneBotActionError(`音乐卡片签名失败: HTTP ${status}`, 1500, "send_msg"));
            return;
          }
          try {
            resolve(body ? JSON.parse(body) : "");
          } catch {
            resolve(body);
          }
        });
      });
      request.setTimeout(timeout, () => request.destroy(new Error("音乐卡片签名超时")));
      request.on("error", reject);
      request.write(payload);
      request.end();
    });
  }
  replyElement(data) {
    let cached;
    if (data.id !== undefined && data.id !== null && data.id !== "") {
      cached = this.getCachedMessage(String(data.id));
    } else if (data.seq !== undefined && data.seq !== null) {
      const sequence = String(data.seq);
      for (const [key, event] of this.oneBotMessages) {
        if (String(event.real_seq || event.real_id || "") === sequence) {
          cached = this.getCachedMessage(key);
          break;
        }
      }
    }
    if (!cached) throw new OneBotActionError("回复消息不存在或已过期", 1404, "send_msg");
    const event = cached.event || {};
    const raw = cached.raw || {};
    const sequence = String(raw.msgSeq || event.real_seq || event.real_id || data.seq || "");
    const senderUin = String(raw.senderUin || event.user_id || "");
    return {
      elementType: 7,
      elementId: "",
      replyElement: {
        sourceMsgIdInRecords: String(cached.nativeId || ""),
        replayMsgSeq: sequence,
        replayMsgId: String(cached.nativeId || ""),
        senderUin,
        senderUidStr: String(raw.senderUid || ""),
        replyMsgTime: String(raw.msgTime || event.time || ""),
        replyMsgClientSeq: String(raw.clientSeq || sequence),
        _replyMsgPeer: this.peerForEvent(event, raw),
      },
    };
  }
  async atElement(groupId, userId) {
    if (!userId) throw new Error("@ 消息缺少 qq");
    if (userId === "all") {
      return {
        elementType: 1,
        elementId: "",
        textElement: { content: "@全体成员", atType: 1, atUid: "all", atTinyId: "", atNtUid: "all" }
      };
    }
    const uid = await this.resolveUid(userId);
    let name = userId;
    try {
      const member = await this.queryGroupMemberInfo(groupId, userId);
      name = member.card || member.nickname || userId;
    } catch {
    }
    return {
      elementType: 1,
      elementId: "",
      textElement: { content: `@${name}`, atType: 2, atUid: userId, atTinyId: "", atNtUid: uid }
    };
  }
  async sendNativeElements(type, target, elements) {
    if (!this.session) throw new Error("QQ 会话尚未初始化");
    const peerUid = type === "private" ? await this.resolveUid(target) : target;
    return this.sendNativeElementsToPeer(
      { chatType: type === "group" ? 2 : 1, peerUid, guildId: "" },
      elements,
      type,
    );
  }
  waitForSentMessage(match, timeout = 30000) {
    let settled = false;
    let pending;
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        this.pendingSentMessages.delete(pending);
        reject(new OneBotActionError("等待 QQ 消息发送回执超时", 1500, "send_msg"));
      }, timeout);
      pending = {
        match,
        resolve: (raw) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          this.pendingSentMessages.delete(pending);
          resolve(raw);
        },
        reject: (error) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          this.pendingSentMessages.delete(pending);
          reject(error);
        },
        timer,
      };
      this.pendingSentMessages.add(pending);
    });
    return {
      promise,
      cancel: () => {
        if (settled) return;
        settled = true;
        clearTimeout(pending?.timer);
        this.pendingSentMessages.delete(pending);
      },
    };
  }
  handleSentMessageUpdates(messages) {
    const completed = [];
    for (const raw of Array.from(messages || [])) {
      const status = Number(raw?.sendStatus);
      for (const pending of Array.from(this.pendingSentMessages)) {
        let matched = false;
        try {
          matched = pending.match(raw);
        } catch (error) {
          pending.reject(error);
          continue;
        }
        if (!matched) continue;
        if (status === 0) {
          pending.reject(new OneBotActionError(String(raw?.sendRemark || raw?.errMsg || "QQ 消息发送失败"), 1500, "send_msg"));
        } else if (!Number.isFinite(status) || status === 2 || status === 3) {
          pending.resolve(raw);
        }
      }
      if (status === 2 && Array.isArray(raw?.elements) && raw.elements.length) completed.push(raw);
    }
    if (completed.length) {
      for (const raw of completed) {
        this.enqueueMessageWork(raw, () => this.handleMessage(raw, true), "[消息] 已发送消息转换失败:");
      }
    }
  }
  messageWorkKey(msg) {
    const chatType = Number(msg?.chatType || 0);
    const peer = String(msg?.peerUid || msg?.peerUin || msg?.senderUid || msg?.senderUin || nativeMessageKey(msg));
    return `${chatType}:${peer}`;
  }
  enqueueMessageWork(msg, work, label = "[消息] 消息处理失败:") {
    const key = this.messageWorkKey(msg);
    const previous = this.incomingMessageTails.get(key) || Promise.resolve();
    const current = previous
      .catch(() => {})
      .then(work)
      .catch((error) => {
        logErr(this.botConfig.id, label, error?.message || error);
      });
    this.incomingMessageTails.set(key, current);
    const cleanup = () => {
      if (this.incomingMessageTails.get(key) === current) this.incomingMessageTails.delete(key);
    };
    current.then(cleanup, cleanup);
    return current;
  }
  async sendNativeElementsToPeer(peer, elements, logType = "private") {
    if (!this.session) throw new Error("QQ 会话尚未初始化");
    const service = this.getMsgService();
    const send = requireNativeMethod(service, "sendMsg", "send_msg");
    let uniqueId = "";
    if (typeof service?.generateMsgUniqueId === "function") {
      const serverTime = this.session?.getMSFService?.()?.getServerTime?.() || Math.floor(Date.now() / 1000);
      uniqueId = String(await service.generateMsgUniqueId(Number(peer.chatType), serverTime));
    }
    const sendPeer = { ...peer, guildId: uniqueId || String(peer.guildId || "") };
    const pending = this.waitForSentMessage((raw) => {
      if (String(raw?.peerUid || "") !== String(sendPeer.peerUid)) return false;
      if (uniqueId && String(raw?.guildId || "") !== uniqueId) return false;
      return true;
    });
    try {
      const result = await send(
        "0",
        sendPeer,
        elements,
        /* @__PURE__ */ new Map()
      );
      const resultCode = Number(result?.result ?? result?.retcode ?? 0);
      if (Number.isFinite(resultCode) && resultCode !== 0) {
        throw new Error(result?.errMsg || result?.message || `发送失败 (${resultCode})`);
      }
      if (result?.msgId && Array.isArray(result?.elements)) {
        pending.cancel();
        return result;
      }
      return await pending.promise;
    } catch (error) {
      pending.cancel();
      logErr(this.botConfig.id, `${logType === "group" ? "群" : "私聊"}消息发送失败:`, error);
      throw error;
    }
  }
  async imageElement(input, summary = "", subType = 0) {
    const materialized = await this.materializeFile(input, ".png");
    const stat = fs.statSync(materialized.path);
    return {
      ...materialized,
      element: {
        elementType: 2,
        elementId: "",
        picElement: {
          fileSize: String(stat.size),
          picWidth: 0,
          picHeight: 0,
          fileName: path.basename(materialized.path),
          sourcePath: materialized.path,
          original: true,
          picType: 1e3,
          picSubType: subType,
          fileUuid: "",
          fileSubId: "",
          thumbFileSize: 0,
          summary,
          thumbPath: /* @__PURE__ */ new Map()
        }
      }
    };
  }
  async fileLikeElement(segmentType, data) {
    const input = String(data.file || data.url || data.path || "");
    if (!input) throw new OneBotActionError(`${segmentType} 消息缺少 file/url`, 1400);
    const extension = segmentType === "record" ? ".silk" : segmentType === "video" ? ".mp4" : path.extname(String(data.name || input));
    const materialized = await this.materializeFile(input, extension);
    const stat = fs.statSync(materialized.path);
    const fileName = String(data.name || data.file_name || path.basename(materialized.path));
    let element;
    if (segmentType === "record") {
      element = {
        elementType: 4,
        elementId: "",
        pttElement: {
          fileName,
          filePath: materialized.path,
          md5HexStr: "",
          fileSize: String(stat.size),
          duration: Number(data.duration || 1),
          formatType: 1,
          voiceType: 1,
          voiceChangeType: 0,
          canConvert2Text: true,
          waveAmplitudes: [0, 18, 9, 23, 16, 17, 16, 15],
          fileSubId: "",
          playState: 1,
          autoConvertText: 0,
          storeID: 0,
          otherBusinessInfo: { aiVoiceType: 0 },
        },
      };
    } else if (segmentType === "video") {
      element = {
        elementType: 5,
        elementId: "",
        videoElement: {
          fileName,
          filePath: materialized.path,
          fileSize: String(stat.size),
          fileTime: Number(data.duration || 0),
          fileWidth: Number(data.width || 0),
          fileHeight: Number(data.height || 0),
          thumbPath: new Map(),
        },
      };
    } else {
      const online = segmentType === "onlinefile";
      element = {
        elementType: online ? (this.asBoolean(data.is_dir ?? data.isDir) ? 30 : 23) : 3,
        elementId: "",
        fileElement: {
          fileName,
          filePath: materialized.path,
          fileSize: String(stat.size),
          folderId: String(data.folder_id || data.folder || ""),
        },
      };
    }
    return { ...materialized, element };
  }
  inferFileExtension(value, preferred = "") {
    let extension = String(preferred || "").toLowerCase();
    if (!extension && value.startsWith("data:")) {
      const mime = value.slice(5, value.indexOf(";"));
      extension = ({ "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "audio/mpeg": ".mp3", "video/mp4": ".mp4" })[mime] || "";
    }
    if (!extension && /^https?:\/\//i.test(value)) {
      try {
        extension = path.extname(new URL(value).pathname);
      } catch {
      }
    }
    if (!extension && !/^(?:base64:|data:)/i.test(value)) extension = path.extname(value);
    if (extension && !extension.startsWith(".")) extension = "." + extension;
    return /^\.[A-Za-z0-9]{1,10}$/.test(extension) ? extension : ".bin";
  }
  parseOneBotHeaders(headers) {
    const result = {};
    const values = Array.isArray(headers)
      ? headers
      : typeof headers === "string"
        ? headers.split(/\\r?\\n|\\[\\r\\n\\]/)
        : [];
    for (const value of values) {
      const entry = String(value || "").trim();
      if (!entry) continue;
      const colon = entry.indexOf(":");
      const equal = entry.indexOf("=");
      const separator = colon >= 0 ? colon : equal;
      if (separator < 1) continue;
      result[entry.slice(0, separator).trim()] = entry.slice(separator + 1).trim();
    }
    return result;
  }
  async materializeFile(input, preferredExtension = "", headers = {}) {
    const value = input.trim();
    if (!value) throw new Error("文件地址为空");
    const extension = this.inferFileExtension(value, preferredExtension);
    const tempPath = path.join(os.tmpdir(), `elaina_${process.pid}_${Date.now()}_${Math.random().toString(16).slice(2)}${extension}`);
    if (value.startsWith("base64://") || value.startsWith("data:")) {
      const encoded = value.startsWith("base64://") ? value.slice(9) : value.slice(value.indexOf(",") + 1);
      const data = Buffer.from(encoded, "base64");
      if (!data.length) throw new Error("base64 文件内容为空");
      fs.writeFileSync(tempPath, data);
      return { path: tempPath, temporary: true };
    }
    if (/^https?:\/\//i.test(value)) {
      await this.downloadFile(value, tempPath, 0, headers);
      return { path: tempPath, temporary: true };
    }
    let localPath = value;
    if (value.startsWith("file://")) {
      localPath = decodeURIComponent(value.slice(7));
      if (os.platform() === "win32" && /^\/[A-Za-z]:/.test(localPath)) localPath = localPath.slice(1);
    }
    localPath = path.resolve(localPath);
    if (!fs.existsSync(localPath) || !fs.statSync(localPath).isFile()) throw new Error(`文件不存在: ${localPath}`);
    return { path: localPath, temporary: false };
  }
  async downloadFile(url, destination, redirects = 0, headers = {}) {
    if (redirects > 5) throw new Error("下载图片重定向次数过多");
    const client = url.startsWith("https:") ? (await import('https')).default : (await import('http')).default;
    await new Promise((resolve, reject) => {
      const request = client.get(url, { headers }, (response) => {
        const status = Number(response.statusCode || 0);
        if (status >= 300 && status < 400 && response.headers.location) {
          response.resume();
          const next = new URL(response.headers.location, url).toString();
          this.downloadFile(next, destination, redirects + 1, headers).then(resolve, reject);
          return;
        }
        if (status < 200 || status >= 300) {
          response.resume();
          reject(new Error(`下载图片失败: HTTP ${status}`));
          return;
        }
        const output = fs.createWriteStream(destination);
        response.pipe(output);
        output.on("finish", () => output.close(() => resolve()));
        output.on("error", reject);
      });
      request.setTimeout(3e4, () => request.destroy(new Error("下载图片超时")));
      request.on("error", reject);
    });
  }
  async queryGroupList(params = {}) {
    const service = this.session?.getGroupService?.();
    if (!service?.getGroupList) return [];
    const forced = this.asBoolean(params.no_cache, false);
    const waited = await this.waitForNativeEvent(
      "group_list",
      () => service.getGroupList(forced),
      (_updateType, groups) => Array.isArray(groups) || groups instanceof Map || (groups && typeof groups === "object"),
      (result) => extractNativeGroupList(result) !== undefined,
    );
    if (waited.direct !== null) {
      checkNativeResult(waited.direct, "获取群列表失败");
    }
    const rawGroups = waited.direct !== null ? extractNativeGroupList(waited.direct) : waited.args[1];
    return collectionValues(rawGroups)
      .filter((group) => group && typeof group === "object")
      .map((group) => oneBotGroup(group))
      .filter((group) => group.group_id);
  }
  async queryGroupInfo(groupId, params = {}) {
    const data = await this.fetchNativeGroupDetail(groupId, "get_group_info");
    return oneBotGroup({ ...data, groupCode: data.groupCode || groupId }, groupId);
  }
  async queryGroupMemberList(groupId, params = {}) {
    const service = this.session?.getGroupService?.();
    if (!service?.getAllMemberList) return [];
    const forced = this.asBoolean(params.no_cache, false);
    const waited = await this.waitForNativeEvent(
      "member_list",
      () => service.getAllMemberList(String(groupId), forced),
      (...args) => {
        const callback = normalizeNativeMemberListCallback(args, groupId);
        return callback.groupId === String(groupId) && extractNativeMemberMap({ infos: callback.infos }) !== undefined;
      },
      (result) => extractNativeMemberMap(result) !== undefined,
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "获取群成员列表失败");
    const infos = waited.direct !== null
      ? extractNativeMemberMap(waited.direct)
      : normalizeNativeMemberListCallback(waited.args, groupId).infos;
    const members = collectionValues(infos).filter((member) => member && typeof member === "object");
    this.rememberGroupMemberSnapshot(groupId, members);
    return members
      .map((member) => oneBotGroupMember(groupId, member))
      .filter((member) => member.user_id);
  }
  async initializeGroupMemberSnapshots() {
    const groups = await this.queryGroupList({ no_cache: true });
    const pending = Array.from(groups || []);
    const workers = Array.from({ length: Math.min(4, pending.length) }, async () => {
      while (pending.length) {
        const group = pending.shift();
        if (!group?.group_id) continue;
        try {
          await this.queryGroupMemberList(String(group.group_id), { no_cache: true });
        } catch (error) {
          logErr(this.botConfig.id, "[事件] 预热群成员快照失败: group=" + group.group_id, error?.message || error);
        }
      }
    });
    await Promise.all(workers);
  }
  async queryGroupMemberInfo(groupId, userId, params = {}) {
    const forced = this.asBoolean(params.no_cache, true);
    const service = this.session?.getGroupService?.();
    if (service?.getMemberInfo) {
      const uid = await this.resolveUid(userId);
      const waited = await this.waitForNativeEvent(
        "member_info",
        () => service.getMemberInfo(String(groupId), [uid], forced),
        (callbackGroup, _source, members) => String(callbackGroup) === String(groupId) && collectionValues(members).some((member) => String(member?.uid || member?.uin || "") === uid),
        (result) => collectionValues(extractNativeMemberMap(result)).some((member) => String(member?.uid || member?.uin || "") === uid),
      );
      if (waited.direct !== null) checkNativeResult(waited.direct, "获取群成员信息失败");
      const infos = waited.direct !== null ? extractNativeMemberMap(waited.direct) : waited.args[2] || waited.args[1];
      const member = collectionValues(infos).find((item) => String(item?.uid || item?.uin || item?.user_id || "") === uid || String(item?.uin || item?.user_id || "") === String(userId));
      if (member) {
        let profile = {};
        try {
          const profileService = this.session?.getProfileService?.();
          const detail = await profileService?.getUserDetailInfo?.(uid, forced);
          profile = detail?.data || detail?.detail || detail || {};
        } catch {
        }
        return oneBotGroupMember(groupId, { ...profile, ...profile?.coreInfo, ...profile?.baseInfo, ...member });
      }
    }
    const members = await this.queryGroupMemberList(groupId, { no_cache: forced });
    const member = members.find((item) => String(item.user_id) === String(userId));
    if (!member) throw new OneBotActionError(`群 ${groupId} 中不存在成员 ${userId}`, 1404, "get_group_member_info");
    return member;
  }
  async getFriendSimpleInfoMap(uids) {
    const normalized = [...new Set(Array.from(uids || []).map(String).filter(Boolean))];
    if (!normalized.length) return new Map();
    const service = this.session?.getProfileService?.();
    if (!service?.getCoreAndBaseInfo) return new Map();
    try {
      const result = await service.getCoreAndBaseInfo("nodeStore", normalized);
      if (result instanceof Map) {
        return new Map(Array.from(result, ([key, value]) => [String(key), value]));
      }
      return new Map(Object.entries(result || {}).map(([key, value]) => [String(key), value]));
    } catch {
      return new Map();
    }
  }
  async buildOneBotFriend(service, uid, forced = false, simpleInfo = undefined) {
    const uin = await this.resolveUin(uid);
    let detail = {};
    try {
      const profileService = this.session?.getProfileService?.();
      const value = await profileService?.getUserDetailInfo?.(String(uid), forced);
      detail = value?.data || value?.detail || value || {};
    } catch {
    }
    const coreInfo = {
      ...(simpleInfo?.coreInfo || {}),
      ...(detail.coreInfo || {}),
      uin: detail.uin || uin,
      nick: detail.coreInfo?.nick || detail.nick || detail.nickname || this.displayText(service.getBuddyNick?.(uid)),
      remark: detail.coreInfo?.remark || detail.remark || this.displayText(service.getBuddyRemark?.(uid)),
    };
    const baseInfo = { ...(simpleInfo?.baseInfo || {}), ...(detail.baseInfo || {}) };
    return oneBotFriend({
      ...simpleInfo,
      ...detail,
      coreInfo,
      baseInfo,
      qqLevel: detail.qqLevel || simpleInfo?.qqLevel,
    }, uin);
  }
  async queryFriendList(params = {}) {
    const service = this.session?.getBuddyService?.();
    if (!service?.getBuddyListV2) return [];
    const forced = this.asBoolean(params.no_cache, false);
    const result = await service.getBuddyListV2("0", true, 0);
    checkNativeResult(result, "获取好友列表失败");
    const categories = result?.data || result?.result?.data || result?.categories || result?.result || result || [];
    const ids = [...new Set(collectionValues(categories).flatMap((item) => item?.buddyUids || item?.buddy_uids || []))];
    const simpleInfoMap = await this.getFriendSimpleInfoMap(ids);
    const friends = await Promise.all(ids.map((uid) =>
      this.buildOneBotFriend(service, uid, forced, simpleInfoMap.get(String(uid)))
    ));
    return friends.filter((friend) => friend.user_id);
  }
  qqLevelValue(level) {
    if (typeof level === "number") return level;
    if (!level || typeof level !== "object") return 0;
    return Number(level.crownNum || 0) * 64
      + Number(level.sunNum || 0) * 16
      + Number(level.moonNum || 0) * 4
      + Number(level.starNum || 0);
  }
  oneBotSex(value) {
    if (value === 1 || String(value).toLowerCase() === "male") return "male";
    if (value === 2 || String(value).toLowerCase() === "female") return "female";
    return "unknown";
  }
  async queryStrangerInfo(params) {
    const userId = String(params.user_id || "");
    if (!/^\d+$/.test(userId)) {
      throw new OneBotActionError("用户 QQ 号无效", 1400, "get_stranger_info");
    }
    const service = this.session?.getProfileService?.();
    const getByUin = requireNativeMethod(service, "getUserDetailInfoByUin", "get_stranger_info");
    const extended = await getByUin(userId);
    checkNativeResult(extended, "获取陌生人资料失败");
    const detail = extended?.detail || extended?.data?.detail || extended?.data || {};
    const simple = detail.simpleInfo || {};
    const core = simple.coreInfo || {};
    const base = simple.baseInfo || {};
    const common = detail.commonExt || {};
    const status = simple.status || {};
    const vas = simple.vasInfo || {};
    const relation = simple.relationFlags || {};
    const uid = String(detail.uid || (await this.resolveUid(userId)));
    let info = {};
    if (typeof service?.getUserDetailInfo === "function") {
      info = await service.getUserDetailInfo(uid, this.asBoolean(params.no_cache));
      checkNativeResult(info, "获取用户详细资料失败");
      info = info?.data || info?.detail || info || {};
    }
    return {
      ...core,
      ...base,
      ...relation,
      ...status,
      user_id: Number(detail.uin || userId) || userId,
      uid: String(info.uid || uid),
      nickname: String(core.nick || info.nick || info.nickname || ""),
      age: Number(base.age ?? info.age ?? 0),
      qid: String(base.qid || info.qid || ""),
      qqLevel: this.qqLevelValue(common.qqLevel || simple.qqLevel || info.qqLevel),
      sex: this.oneBotSex(base.sex ?? info.sex),
      long_nick: String(base.longNick || info.longNick || ""),
      reg_time: Number(common.regTime ?? info.regTime ?? 0),
      is_vip: vas.svipFlag === true || vas.vipFlag === true || Number(vas.svipFlag || vas.vipFlag || 0) > 0,
      is_years_vip: vas.yearVipFlag === true || Number(vas.yearVipFlag || 0) > 0,
      vip_level: Number(vas.vipLevel || 0),
      remark: String(core.remark || info.remark || ""),
      status: Number(status.status ?? info.status ?? 0),
      login_days: 0,
    };
  }
  async deleteOneBotMessage(messageId) {
    const { event, raw, nativeId } = this.getCachedMessage(messageId);
    const peer = this.peerForEvent(event, raw);
    const method = requireNativeMethod(this.getMsgService(), "recallMsg", "delete_msg");
    const matchesRecall = (messages) => collectionValues(messages?.msgList || messages).some((message) =>
      String(message?.msgId || message?.messageId || "") === String(nativeId)
        && String(message?.recallTime ?? "0") !== "0"
    );
    const waited = await this.waitForNativeEvent(
      "message_update",
      () => method(peer, [nativeId]),
      matchesRecall,
      (result) => matchesRecall(result?.updatedList || result?.data),
      1500,
    );
    if (waited.direct !== null) checkNativeResult(waited.direct, "撤回消息失败");
    return {};
  }
  async handleQuickOperation(params) {
    const context = params?.context;
    const operation = params?.operation;
    if (!context || typeof context !== "object" || !operation || typeof operation !== "object") {
      throw new OneBotActionError("快速操作缺少事件上下文或操作参数", 1400, ".handle_quick_operation");
    }
    if (context.post_type === "message" || context.post_type === "message_sent") {
      const isGroup = context.message_type === "group";
      if (operation.reply !== undefined && operation.reply !== null) {
        const message = [];
        if (isGroup) {
          message.push({ type: "reply", data: { id: String(context.message_id) } });
          if (this.asBoolean(operation.at_sender)) {
            message.push({ type: "at", data: { qq: String(context.user_id) } });
          }
        }
        message.push(...this.normalizeOneBotMessage(operation.reply, this.asBoolean(operation.auto_escape)));
        const target = String(isGroup ? context.group_id : context.user_id);
        await this.sendOneBotMessage(isGroup ? "group" : "private", target, message, false);
      }
      if (this.asBoolean(operation.delete) && context.message_id !== undefined) {
        await this.deleteOneBotMessage(String(context.message_id));
      }
      if (isGroup && this.asBoolean(operation.kick)) {
        await this.setGroupKick(String(context.group_id), String(context.user_id), false);
      }
      if (isGroup && this.asBoolean(operation.ban)) {
        await this.setGroupBan(
          String(context.group_id),
          String(context.user_id),
          Math.max(0, Number(operation.ban_duration ?? 1800)),
        );
      }
      return null;
    }
    if (context.post_type === "request" && operation.approve !== undefined) {
      if (context.request_type === "friend") {
        await this.setFriendAddRequest({
          flag: context.flag,
          approve: operation.approve,
          remark: operation.remark,
        });
      } else if (context.request_type === "group") {
        await this.setGroupAddRequest({
          flag: context.flag,
          sub_type: context.sub_type,
          approve: operation.approve,
          reason: operation.reason,
        });
      }
    }
    return null;
  }
  asBoolean(value, fallback = false) {
    return asOneBotBoolean(value, fallback);
  }
  async resolveUid(uin) {
    if (!uin) throw new Error("缺少 QQ 号");
    try {
      const converted = await this.session?.getUixConvertService?.().getUid([uin]);
      const uid = converted?.uidInfo?.get?.(uin);
      if (uid) return String(uid);
    } catch {
    }
    try {
      const uid = this.session?.getProfileService?.().getUidByUin("FriendsServiceImpl", [uin])?.get?.(uin);
      if (uid) return String(uid);
    } catch {
    }
    try {
      const converted = await this.session?.getGroupService?.().getUidByUins([uin]);
      const uid = converted?.uids?.get?.(uin);
      if (uid) return String(uid);
    } catch {
    }
    throw new Error(`无法将 QQ ${uin} 转换为 UID`);
  }
  async markOneBotMessageRead(type, target) {
    const peerUid = type === "private" ? await this.resolveUid(target) : target;
    const result = await this.session?.getMsgService?.().setMsgRead({ chatType: type === "group" ? 2 : 1, peerUid, guildId: "" });
    if (result?.result && result.result !== 0) throw new Error(result.errMsg || "设置已读失败");
    return {};
  }
  async setGroupKick(groupId, userId, rejectAdd) {
    const uid = await this.resolveUid(userId);
    const method = requireNativeMethod(this.session?.getGroupService?.(), "kickMember", "set_group_kick");
    checkNativeResult(await method(groupId, [uid], rejectAdd, ""), "移出群成员失败");
    return {};
  }
  async setGroupBan(groupId, userId, duration) {
    const uid = await this.resolveUid(userId);
    const method = requireNativeMethod(this.session?.getGroupService?.(), "setMemberShutUp", "set_group_ban");
    checkNativeResult(await method(groupId, [{ uid, timeStamp: duration }]), "群禁言失败");
    return {};
  }
  async setGroupWholeBan(groupId, enable) {
    const method = requireNativeMethod(this.session?.getGroupService?.(), "setGroupShutUp", "set_group_whole_ban");
    checkNativeResult(await method(groupId, enable), "全员禁言失败");
    return {};
  }
  async setGroupAdmin(groupId, userId, enable) {
    const uid = await this.resolveUid(userId);
    const method = requireNativeMethod(this.session?.getGroupService?.(), "modifyMemberRole", "set_group_admin");
    checkNativeResult(await method(groupId, uid, enable ? 3 : 2), "设置群管理员失败");
    return {};
  }
  async setGroupCard(groupId, userId, card) {
    const uid = await this.resolveUid(userId);
    const method = requireNativeMethod(this.session?.getGroupService?.(), "modifyMemberCardName", "set_group_card");
    checkNativeResult(await method(groupId, uid, card), "修改群名片失败");
    return {};
  }
  async setGroupName(groupId, groupName) {
    const method = requireNativeMethod(this.session?.getGroupService?.(), "modifyGroupName", "set_group_name");
    checkNativeResult(await method(groupId, groupName, false), "修改群名称失败");
    return {};
  }
  async setGroupLeave(groupId) {
    const method = requireNativeMethod(this.session?.getGroupService?.(), "quitGroup", "set_group_leave");
    checkNativeResult(await method(groupId), "退出群聊失败");
    return {};
  }
  async sendLike(userId, times) {
    const friendUid = await this.resolveUid(userId);
    const result = await this.session?.getProfileLikeService?.().setBuddyProfileLike({
      friendUid,
      sourceId: 71,
      doLikeCount: Math.max(1, times),
      doLikeTollCount: 0
    });
    if (result?.result && result.result !== 0) throw new Error(result.errMsg || "点赞失败");
    return {};
  }
  async getGroupAtAllRemain(groupId) {
    const result = await this.session?.getGroupService?.().getGroupRemainAtTimes(groupId);
    const info = result?.atInfo || {};
    return {
      can_at_all: Boolean(info.canAtAll),
      remain_at_all_count_for_group: Number(info.RemainAtAllCountForGroup || 0),
      remain_at_all_count_for_uin: Number(info.RemainAtAllCountForUin || 0)
    };
  }
  async sendGroupImage(groupId, file) {
    await this.sendOneBotMessage("group", groupId, [{ type: "image", data: { file } }]);
  }
  async sendPrivateImage(userId, file) {
    await this.sendOneBotMessage("private", userId, [{ type: "image", data: { file } }]);
  }
  getPlatformType() {
    return { win32: 3, darwin: 4, linux: 5 }[os.platform()] || 3;
  }
  /** QQNT 登录流程 */
  doLogin() {
    const id = this.botConfig.id;
    return new Promise((resolve, reject) => {
      let isLogined = false;
      let quickLoginInProgress = false;
      let pendingLogin = null;
      let quickFallbackTimer = null;
      let qrScanFallbackTimer = null;
      let qrRequestTimer = null;
      let qrRequestAttempts = 0;
      let qrAvailable = false;
      const clearQuickFallback = () => {
        if (quickFallbackTimer) clearTimeout(quickFallbackTimer);
        quickFallbackTimer = null;
      };
      const clearQrScanFallback = () => {
        if (qrScanFallbackTimer) clearTimeout(qrScanFallbackTimer);
        qrScanFallbackTimer = null;
      };
      const clearQrRequest = () => {
        if (qrRequestTimer) clearTimeout(qrRequestTimer);
        qrRequestTimer = null;
      };
      const requestQrCode = (reason, attempt = 0) => {
        if (isLogined) return;
        clearQuickFallback();
        quickLoginInProgress = false;
        if (attempt === 0) {
          qrRequestAttempts = 0;
          qrAvailable = false;
          clearQrRequest();
          log(id, "[LOGIN]", reason + "，切换二维码登录");
          this.setStatus("logging_in", { qrcodeUrl: "", qrcodeBase64: "", qrcode: "", error: "" });
        }
        const delay = attempt === 0 ? 300 : 1200;
        qrRequestTimer = setTimeout(() => {
          if (isLogined) return;
          qrRequestAttempts = attempt + 1;
          let started = false;
          try {
            started = this.loginService.getQRCodePicture();
            log(id, `[LOGIN] 请求二维码 (${qrRequestAttempts}/4), native返回:`, String(started));
          } catch (error) {
            logErr(id, "[LOGIN] 请求二维码异常:", error.message);
          }
          if (started === false && qrRequestAttempts >= 4) {
            const message = "QQ 无法生成登录二维码，请检查 QQ 版本与登录服务状态";
            logErr(id, "[LOGIN]", message);
            this.setStatus("logging_in", { error: message });
            return;
          }
          if (!qrAvailable && qrRequestAttempts < 4) {
            qrRequestTimer = setTimeout(() => requestQrCode("二维码回调超时", qrRequestAttempts), 3000);
          }
        }, delay);
      };
      const completeLogin = (loginResult) => {
        if (isLogined) return;
        const result = loginResult && typeof loginResult === "object"
          ? (loginResult.data && typeof loginResult.data === "object"
            ? loginResult.data
            : loginResult.loginResult && typeof loginResult.loginResult === "object"
              ? loginResult.loginResult
              : loginResult)
          : {};
        const uid = String(result.uid || result.userUid || result.accountUid || pendingLogin?.uid || "");
        const uin = String(result.uin || result.account || result.mainAccount || result.accountUin || pendingLogin?.uin || this.botConfig.uin || "");
        if (!uid || !uin) {
          logErr(id, "[LOGIN] 登录回调缺少 uid/uin:", safeJson(loginResult));
          requestQrCode("登录信息不完整");
          return;
        }
        isLogined = true;
        clearQuickFallback();
        clearQrScanFallback();
        clearQrRequest();
        const nick = String(result.nickName || result.nickname || result.nick || pendingLogin?.nickName || "");
        log(id, "[LOGIN] 登录成功，账号:", uin, "uid:", uid);
        this.setStatus("authorizing", {
          loginUin: uin,
          qrcodeUrl: "",
          qrcodeBase64: "",
          qrcode: "",
          error: ""
        });
        resolve({ uid, uin, nick, online: true });
      };
      const loginListener = new LoginListener();
      loginListener.onUserLoggedIn = (userid) => {
        const message = "当前账号(" + userid + ")已登录,无法重复登录";
        logErr(id, "[LOGIN] onUserLoggedIn:", message);
        this.setStatus("logging_in", { error: message });
      };
      loginListener.onQRCodeLoginSucceed = (loginResult) => {
        log(id, "[LOGIN] onQRCodeLoginSucceed:", safeJson(loginResult, 500));
        completeLogin(loginResult);
      };
      loginListener.onLoginConnected = () => {
        log(id, "[LOGIN] onLoginConnected 触发");
        const waitAndLogin = async () => {
          let tryCount = 0;
          while (tryCount < 60) {
            const status = this.loginService.getMsfStatus();
            log(id, "[LOGIN] 等待网络连接... getMsfStatus:", status);
            if (status !== 3) break;
            await new Promise((r) => setTimeout(r, 500));
            tryCount++;
          }
          if (this.loginService.getMsfStatus() === 3) throw new Error("QQ 登录网络连接超时");
          log(id, "[LOGIN] 网络已连接");
          const uin = this.botConfig.uin;
          if (uin) {
            const historyList = await this.loginService.getLoginList();
            const list = historyList?.LocalLoginInfoList || [];
            const loginInfo = list.find((item) => String(item.uin) === String(uin));
            if (loginInfo && loginInfo.isQuickLogin !== false) {
              log(id, "[LOGIN] 快速登录:", uin);
              pendingLogin = loginInfo;
              quickLoginInProgress = true;
              try {
                const res = await this.loginService.quickLoginWithUin(uin);
                const quickLoginSuccess = String(res?.result ?? "") === "0" && !res?.loginErrorInfo?.errMsg;
                if (!quickLoginSuccess) {
                  const message = res?.loginErrorInfo?.errMsg || "快速登录失败，错误码: " + String(res?.result ?? "unknown");
                  log(id, "[LOGIN] 快速登录失败:", message);
                  requestQrCode("快速登录失败");
                } else if (!isLogined) {
                  completeLogin({ ...loginInfo, ...res, uin: res?.uin || uin });
                  if (!isLogined) quickFallbackTimer = setTimeout(() => requestQrCode("快速登录等待超时"), 15e3);
                }
              } catch (e) {
                logErr(id, "[LOGIN] 快速登录异常:", e.message);
                requestQrCode("快速登录异常");
              }
            } else {
              requestQrCode(loginInfo ? "该账号不可快速登录" : "未找到历史登录记录");
            }
          } else {
            requestQrCode("未保存账号");
          }
        };
        waitAndLogin().catch((error) => {
          logErr(id, "[LOGIN] 登录初始化异常:", error.message);
          if (!isLogined) reject(error);
        });
        loginListener.onLoginConnected = () => {
        };
      };
      loginListener.onQRCodeGetPicture = (data) => {
        const { qrcodeUrl, qrcodeBase64 } = normalizeQrData(data);
        qrAvailable = Boolean(qrcodeUrl || qrcodeBase64);
        clearQrRequest();
        log(id, "[LOGIN] onQRCodeGetPicture, qrcodeUrl:", qrcodeUrl ? "有" : "无", "base64长度:", qrcodeBase64.length);
        log(id, "[LOGIN] 二维码已生成，状态切换为 waiting_qr");
        this.setStatus("waiting_qr", {
          qrcodeUrl,
          qrcodeBase64,
          qrcode: qrcodeBase64,
          error: ""
        });
      };
      loginListener.onQRCodeSessionFailed = (errType, errCode) => {
        log(id, "[LOGIN] onQRCodeSessionFailed:", errType, errCode);
        if (!isLogined) {
          if (errType === 1 && errCode === 3) {
            log(id, "[LOGIN] 二维码过期，刷新");
          }
          try {
            requestQrCode("二维码已过期");
          } catch (error) {
            logErr(id, "[LOGIN] 刷新二维码失败:", error.message);
          }
        }
      };
      loginListener.onLoginFailed = (...args) => {
        const errorText = safeJson(args, 800);
        logErr(id, "[LOGIN] onLoginFailed:", errorText);
        if (quickLoginInProgress) requestQrCode("快速登录回调失败");
        else if (!isLogined) this.setStatus("logging_in", { error: "登录失败: " + errorText });
      };
      loginListener.onQRCodeSessionQuickLoginFailed = (...args) => {
        logErr(id, "[LOGIN] onQRCodeSessionQuickLoginFailed:", safeJson(args, 800));
        requestQrCode("快速登录会话失效");
      };
      loginListener.onLoginConnecting = () => {
        log(id, "[LOGIN] onLoginConnecting");
      };
      loginListener.onLoginDisConnected = () => {
        log(id, "[LOGIN] onLoginDisConnected");
      };
      loginListener.onLoginState = (...args) => {
        log(id, "[LOGIN] onLoginState:", safeJson(args, 400));
      };
      loginListener.onQRCodeSessionUserScaned = (...args) => {
        log(id, "[LOGIN] 用户已扫码");
        log(id, "[LOGIN] 扫码回调参数:", safeJson(args, 300));
        this.setStatus("logging_in", { error: "" });
        clearQrScanFallback();
        qrScanFallbackTimer = setTimeout(async () => {
          if (isLogined) return;
          try {
            const history = await this.loginService.getLoginList();
            const list = Array.isArray(history?.LocalLoginInfoList) ? history.LocalLoginInfoList : [];
            const expectedUin = String(this.botConfig.uin || pendingLogin?.uin || "");
            const candidate = expectedUin
              ? list.find((item) => String(item?.uin || "") === expectedUin)
              : list.find((item) => item?.uin && item?.uid);
            if (candidate?.uin && candidate?.uid && this.loginService.getMsfStatus() !== 3) {
              log(id, "[LOGIN] 未收到标准成功回调，使用扫码后的登录记录完成登录:", String(candidate.uin));
              completeLogin(candidate);
            }
          } catch (error) {
            logErr(id, "[LOGIN] 扫码登录兜底检查失败:", error.message);
          }
        // 等待真实的扫码登录回调后再初始化会话。部分旧版 QQ 回调较慢，
        // 若过早结束等待，会在鉴权尚未完成时启动原生会话。
        }, 15000);
      };
      loginListener.onQRCodeLoginPollingStarted = () => {
        log(id, "[LOGIN] 轮询已开始");
      };
      log(id, "[LOGIN] 添加监听器...");
      this.loginListener = proxied(loginListener);
      this.loginService.addKernelLoginListener(this.loginListener);
      log(id, "[LOGIN] 调用 connect...");
      this.loginService.connect();
      log(id, "[LOGIN] connect 完成，等待回调...");
    });
  }
  /** QQNT session 初始化 */
  async initSession(dataPath) {
    const id = this.botConfig.id;
    if (!this.selfInfo) throw new Error("未登录");
    let guid = this.loginService.getMachineGuid();
    if (guid && guid.length >= 32 && !guid.includes("-")) {
      guid = guid.slice(0, 8) + "-" + guid.slice(8, 12) + "-" + guid.slice(12, 16) + "-" + guid.slice(16, 20) + "-" + guid.slice(20);
    }
    log(id, "[会话] GUID:", guid);
    const platformType = this.getPlatformType();
    const downloadPath = path.join(dataPath, "ElainaQQ", "temp");
    fs.mkdirSync(downloadPath, { recursive: true });
    const sessionConfig = {
      selfUin: this.selfInfo.uin,
      selfUid: this.selfInfo.uid,
      desktopPathConfig: { account_path: dataPath },
      clientVer: this.qqInfo.version,
      a2: "",
      d2: "",
      d2Key: "",
      machineId: "",
      platform: platformType,
      platVer: os.release(),
      appid: this.qqInfo.appid,
      rdeliveryConfig: {
        appKey: "",
        systemId: 0,
        appId: "",
        logicEnvironment: "",
        platform: platformType,
        language: "",
        sdkVersion: "",
        userId: "",
        appVersion: "",
        osVersion: "",
        bundleId: "",
        serverUrl: "",
        fixedAfterHitKeys: [""]
      },
      defaultFileDownloadPath: downloadPath,
      deviceInfo: {
        guid,
        buildVer: this.qqInfo.version,
        localId: 2052,
        devName: os.hostname(),
        devType: os.type(),
        vendorName: "",
        osVer: os.release(),
        vendorOsName: os.type(),
        setMute: false,
        vendorType: 0
      },
      deviceConfig: '{"appearance":{"isSplitViewMode":true},"msg":{}}'
    };
    this.sessionDependsAdapter = new SessionDependsAdapter();
    this.sessionDispatcherAdapter = new SessionDispatcherAdapter();
    this.sessionListener = new SessionListener();
    const sessionListener = this.sessionListener;
    await new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error("QQ Session 初始化超时（未收到 onOpentelemetryInit）"));
      }, 30000);
      const finish = (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error);
        else resolve();
      };
      sessionListener.onSessionInitComplete = (...args) => {
        log(id, "[会话] 初始化完成回调:", safeJson(args, 300));
      };
      sessionListener.onOpentelemetryInit = (info) => {
        log(id, "[会话] 遥测初始化回调:", safeJson(info, 500));
        if (info?.is_init) finish();
        else finish(new Error("session opentelemetry init failed"));
      };
      log(id, "[会话] 正在初始化...");
      try {
        this.session.init(
          sessionConfig,
          this.sessionDependsAdapter,
          this.sessionDispatcherAdapter,
          sessionListener
        );
        log(id, "[会话] 正在启动 QQNT 会话");
        if (this.startupSession && typeof this.startupSession.start === "function") {
          log(id, "[会话] 正在启动引导会话");
          this.startupSession.start();
        } else {
          try {
            this.session.startNT(0);
          } catch {
            this.session.startNT();
          }
        }
     } catch (error) {
       finish(error);
     }
    });
  }
  registerMsgListener() {
    const id = this.botConfig.id;
    if (!this.session) {
      log(id, "[消息] 会话为空，跳过");
      return;
    }
    const self = this;
    this.incomingMessageGate = new IncomingMessageGate();
    const listenerImpl = new MessageListener();
    listenerImpl.onLineDev = (clients) => {
      self.oneBotOnlineClients = Array.from(clients || []);
    };
    listenerImpl.onMsgRecall = async (chatType, uid, msgSeq) => {
      try {
        const service = self.getMsgService();
        if (typeof service?.queryMsgsWithFilterEx !== "function") {
          log(id, `[事件] 撤回回调暂无法查询灰条，等待消息更新: ${chatType}/${uid}/${msgSeq}`);
          return;
        }
        const peer = { chatType: Number(chatType), peerUid: String(uid || ""), guildId: "" };
        const result = await service.queryMsgsWithFilterEx("0", "0", String(msgSeq || "0"), {
          chatInfo: peer,
          filterMsgType: [],
          filterSendersUid: [],
          filterMsgToTime: "0",
          filterMsgFromTime: "0",
          isReverseOrder: false,
          isIncludeCurrent: true,
          pageLimit: 1,
        });
        const recalled = collectionValues(result?.msgList || result)
          .find((message) => self.getRecallElement(message));
        if (recalled) await self.emitRecallNotice(recalled);
        else log(id, `[事件] 撤回回调暂未查询到灰条，等待消息更新: ${chatType}/${uid}/${msgSeq}`);
      } catch (error) {
        logErr(id, "[事件] 查询撤回消息失败:", error?.message || error);
      }
    };
    listenerImpl.onMsgInfoListUpdate = (messages) => {
      self.emitNativeEvent("message_update", messages);
      self.handleSentMessageUpdates(messages);
      for (const message of Array.from(messages || [])) {
        if (self.isCurrentRecallUpdate(message)) {
          self.enqueueMessageWork(message, () => self.emitRecallNotice(message), "[事件] 撤回事件转换失败:");
        }
      }
    };
    listenerImpl.onAddSendMsg = (message) => {
      self.handleSentMessageUpdates([message]);
    };
    listenerImpl.onRecvMsg = (msgs) => {
      void self.handleIncomingMessages(msgs, true);
    };
    listenerImpl.onRecvOnlineFileMsg = (msgs) => {
      void self.handleIncomingMessages(msgs);
    };
    listenerImpl.onGroupFileInfoUpdate = (...args) => {
      self.emitNativeEvent("group_file_info", ...args);
    };
    listenerImpl.onInputStatusPush = async (data) => {
      try {
        const userId = await self.resolveUin(String(data?.fromUin || ""));
        self.emitOneBotEvent({
          post_type: "notice",
          notice_type: "notify",
          sub_type: "input_status",
          user_id: Number(userId) || userId || 0,
          group_id: 0,
          event_type: Number(data?.eventType || 0),
          status_text: String(data?.statusText || ""),
        });
      } catch (error) {
        logErr(id, "[事件] 输入状态事件转换失败:", error?.message || error);
      }
    };
    listenerImpl.onKickedOffLine = (kick) => {
      const reason = String(kick?.tipsDesc || kick?.message || "QQ 已离线");
      self.emitOneBotEvent({
        post_type: "notice",
        notice_type: "bot_offline",
        user_id: Number(self.getSelfUin()) || self.getSelfUin(),
        tag: String(kick?.tipsTitle || kick?.title || "BotOfflineEvent"),
        message: reason,
      });
      self.setStatus("offline", { error: reason });
    };
    listenerImpl.onSendMsgError = (...args) => {
      const raw = args.find((value) => value && typeof value === "object") || {};
      self.handleSentMessageUpdates([{ ...raw, sendStatus: 0 }]);
    };
    listenerImpl.onMsgDelete = (contact, messages) => self.emitNativeEvent("message_delete", contact, messages);
    listenerImpl.onMsgEventListUpdate = (events) => self.emitNativeEvent("message_event", events);
    listenerImpl.onSysMsgNotification = (payload) => self.emitNativeEvent("system_message", payload);
    listenerImpl.onRecvSysMsg = (payload) => {
      self.emitNativeEvent("system_message", payload);
      void self.handleSystemNotice(payload).catch((error) => {
        logErr(id, "[事件] 系统事件转换失败:", error?.message || error);
      });
    };
    this.msgListener = proxied(listenerImpl);
    try {
      this.session.getMsgService().addKernelMsgListener(this.msgListener);
      log(id, `[消息] 消息监听注册成功，仅接收 ${this.incomingMessageGate.startedAt} 之后的实时消息`);
    } catch (e) {
      logErr(id, "[消息] 注册消息监听失败:", e.message);
    }
  }
  async handleIncomingMessages(msgs, rememberInvites = false) {
    const id = this.botConfig.id;
    const gate = this.incomingMessageGate;
    if (!gate) return;
    const ignored = { history: 0, invalid_time: 0, duplicate: 0 };
    const jobs = [];
    for (const msg of Array.from(msgs || [])) {
      if (rememberInvites) this.rememberGroupInviteArk(msg);
      const decision = gate.inspect(msg);
      if (!decision.accept) {
        ignored[decision.reason] += 1;
        continue;
      }
      const elements = msg.elements || [];
      if (Number(msg?.msgType || 0) !== 1 && elements.length) {
        // 红包绕过同会话消息转换队列，避免被图片、回复等慢消息阻塞。
        this.emitRedPackets(msg, elements);
      }
      jobs.push(this.enqueueMessageWork(msg, () => this.handleMessage(msg), "[消息] 消息转换失败:"));
    }
    const ignoredCount = ignored.history + ignored.invalid_time + ignored.duplicate;
    if (ignoredCount) {
      log(
        id,
        "[消息] 已忽略 " + ignoredCount + " 条非实时消息" +
        " (登录前=" + ignored.history + ", 时间无效=" + ignored.invalid_time + ", 重复=" + ignored.duplicate + ")"
      );
    }
    await Promise.allSettled(jobs);
  }
  registerEventListeners() {
    const id = this.botConfig.id;
    const emit = (event) => this.emitOneBotEvent(event);

    try {
      const buddy = new BuddyListener();
      buddy.onBuddyReqChange = async (payload) => {
        this.emitNativeEvent("buddy_requests", payload);
        try {
          await this.session?.getBuddyService?.().clearBuddyReqUnreadCnt?.();
        } catch (error) {
          logErr(id, "[事件] 清除好友请求未读数失败:", error?.message || error);
        }
        for (const request of Array.from(payload?.buddyReqs || []).slice(0, Number(payload?.unreadNums || 0))) {
          if (request?.isInitiator || (request?.isDecide && Number(request?.reqType) !== 13) || !request?.isUnread) continue;
          const userId = await this.resolveUin(String(request.friendUid || ""));
          if (!userId || userId === "0") {
            logErr(id, "[事件] 好友请求 UID 无法转换为 QQ: " + String(request.friendUid || ""));
            continue;
          }
          const flag = String(request.reqTime || request.flag || "");
          if (!this.rememberNotice("request:friend:" + flag)) continue;
          emit({
            post_type: "request",
            request_type: "friend",
            user_id: Number(userId) || userId,
            comment: String(request.extWords || ""),
            flag,
          });
        }
      };
      buddy.onDoubtBuddyReqChange = async (payload) => {
        this.emitNativeEvent("doubt_buddy_requests", payload);
      };
      this.buddyListener = proxied(buddy);
      this.buddyListenerHandle = this.session?.getBuddyService?.().addKernelBuddyListener?.(this.buddyListener);
    } catch (error) {
      logErr(id, "[事件] 好友事件监听注册失败:", error?.message || error);
    }

    try {
      const group = new GroupListener();
      const handleGroupNotifies = async (_doubt, notifies) => {
        for (const notify of Array.from(notifies || [])) {
          const groupId = String(notify?.group?.groupCode || notify?.groupCode || "");
          const type = Number(notify?.type || 0);
          const status = Number(notify?.status || 0);
          const notifyTime = Number(notify?.seq || 0) / 1e6;
          if (Number.isFinite(notifyTime) && notifyTime > 0 && notifyTime < Number(this.incomingMessageGate?.startedAt || 0)) continue;
          const increaseCandidate = groupIncreaseCandidateFromNotify(notify);
          if (increaseCandidate) this.rememberGroupIncreaseCandidate(increaseCandidate);
          const requestUid = type === 1 ? notify?.user2?.uid : notify?.user1?.uid;
          const affectedUid = String(requestUid || notify?.actionUser?.uid || "");
          const directUin = type === 1 ? notify?.user2?.uin : notify?.user1?.uin;
          const affectedUin = String(directUin || (affectedUid
            ? await this.resolveGroupMemberUin(groupId, affectedUid)
            : ""));
          const operatorUid = String(notify?.actionUser?.uid || notify?.user2?.uid || "");
          if (groupId && affectedUid && operatorUid) {
            this.oneBotGroupOperators.set(groupId + ":" + affectedUid, operatorUid);
            while (this.oneBotGroupOperators.size > 1000) {
              this.oneBotGroupOperators.delete(this.oneBotGroupOperators.keys().next().value);
            }
          }
          const flag = String(notify?.seq || notify?.flag || "");
          if (status === 1 && [1, 5, 7].includes(type)) {
            if (!affectedUin || affectedUin === "0") {
              logErr(id, `[事件] 群请求成员 UID 无法转换为 QQ: group=${groupId}, uid=${affectedUid}`);
              continue;
            }
            if (!this.rememberNotice("request:group:" + flag)) continue;
            emit({
              post_type: "request",
              request_type: "group",
              sub_type: type === 1 ? "invite" : "add",
              group_id: Number(groupId) || groupId,
              user_id: Number(affectedUin) || affectedUin || 0,
              comment: String(notify?.postscript || ""),
              flag,
            });
          }
        }
      };
      group.onGroupListUpdate = (updateType, groups) => {
        this.emitNativeEvent("group_list", updateType, groups);
      };
      group.onGroupNotifiesUpdated = async (doubt, notifies) => {
        try {
          await this.session?.getGroupService?.().clearGroupNotifiesUnreadCount?.(false);
        } catch (error) {
          logErr(id, "[事件] 清除群请求未读数失败:", error?.message || error);
        }
        await handleGroupNotifies(doubt, notifies);
      };
      group.onGroupSingleScreenNotifies = (doubt, seq, notifies) => {
        this.emitNativeEvent("group_notifies", doubt, seq, notifies);
      };
      group.onGroupDetailInfoChange = (detail) => {
        this.emitNativeEvent("group_detail", detail);
      };
      group.onMemberInfoChange = async (groupCode, _source, members) => {
        this.emitNativeEvent("member_info", groupCode, _source, members);
        for (const member of collectionValues(members)) this.rememberGroupCard(groupCode, member);
      };
      group.onMemberListChange = (...args) => {
        const { groupId: groupCode, infos: members, payload } = normalizeNativeMemberListCallback(args);
        this.emitNativeEvent("member_list", groupCode, members, payload);
        if (!payload || (!payload.hasPrev && !payload.hasNext)) {
          this.rememberGroupMemberSnapshot(groupCode, collectionValues(members));
        }
        for (const member of collectionValues(members)) this.rememberGroupCard(groupCode, member);
      };
      group.onShutUpMemberListChanged = (groupCode, members) => {
        this.emitNativeEvent("group_shut_list", groupCode, members);
      };
      this.groupListener = proxied(group);
      this.groupListenerHandle = this.session?.getGroupService?.().addKernelGroupListener?.(this.groupListener);
    } catch (error) {
      logErr(id, "[事件] 群事件监听注册失败:", error?.message || error);
    }
  }
  emitOneBotEvent(event) {
    if (!event?.post_type) return;
    const { post_type, ...fields } = event;
    this.oneBotEventCallback?.(createOneBotEvent(this.getSelfUin(), post_type, fields));
  }
  async handleSystemNotice(payload) {
    try {
      const event = decodeSystemNotice(payload);
      if (!event) return false;
      let memberUid = String(event.member_uid || "");
      const groupId = String(event.group_id || "");
      let operatorUid = String(event.operator_uid || "");
      if (event.post_type === "request" && event.request_type === "group" && event.sub_type === "invite") {
        const inviterUid = String(event.inviter_uid || "");
        const invite = await this.takeGroupInviteArk(groupId, inviterUid);
        if (!invite) {
          logErr(this.botConfig.id, "[事件] 群邀请未关联到 Ark 请求序号: group=" + groupId + ", inviter=" + inviterUid);
          return false;
        }
        const inviterUin = await this.resolveUin(inviterUid);
        if (!inviterUin || inviterUin === "0") {
          logErr(this.botConfig.id, "[事件] 群邀请者 UID 无法转换为 QQ: " + inviterUid);
          return false;
        }
        event.user_id = Number(inviterUin) || inviterUin || 0;
        event.comment = "";
        event.flag = String(invite.flag);
        delete event.inviter_uid;
        this.oneBotGroupInviteRequests.set(String(invite.flag), {
          seq: String(invite.flag),
          type: 1,
          group: { groupCode: groupId, groupName: "" },
          user1: { uid: inviterUid, nickName: "" },
          user2: { uid: String(this.selfInfo?.uid || ""), nickName: "" },
          actionUser: { uid: inviterUid, nickName: "" },
          actionTime: String(Date.now()),
          postscript: "",
          repeatSeqs: [],
          warningTips: "",
          invitationExt: { srcType: 1, groupCode: groupId, waitStatus: 1 },
          status: 1,
          _doubt: false,
        });
        while (this.oneBotGroupInviteRequests.size > 50) {
          this.oneBotGroupInviteRequests.delete(this.oneBotGroupInviteRequests.keys().next().value);
        }
      }
      if (event.notice_type === "group_increase" && !memberUid && groupId) {
        const candidate = await this.takeGroupIncreaseCandidate(groupId, operatorUid);
        if (candidate) {
          memberUid = String(candidate.memberUid || "");
          operatorUid ||= String(candidate.operatorUid || "");
        } else {
          logErr(this.botConfig.id, `[事件] 入群通知缺少成员 UID，且未找到唯一的群通知关联: group=${groupId}`);
          return false;
        }
      }
      if (!operatorUid && groupId && memberUid) {
        operatorUid = String(this.oneBotGroupOperators.get(groupId + ":" + memberUid) || "");
      }
      if (memberUid) {
        const userId = await this.resolveGroupMemberUin(groupId, memberUid);
        if (event.notice_type === "group_increase" && (!userId || userId === "0")) {
          logErr(this.botConfig.id, `[事件] 入群成员 UID 无法转换为 QQ: group=${groupId}, uid=${memberUid}`);
          return false;
        }
        event.user_id = Number(userId) || userId || 0;
      }
      if (operatorUid) {
        const operatorId = await this.resolveGroupMemberUin(groupId, operatorUid);
        event.operator_id = Number(operatorId) || operatorId || 0;
      } else if (["group_increase", "group_decrease"].includes(event.notice_type)) {
        event.operator_id = 0;
      }
      delete event.member_uid;
      delete event.operator_uid;
      const rawPayload = Buffer.isBuffer(payload) || payload instanceof Uint8Array || Array.isArray(payload)
        ? Buffer.from(payload)
        : Buffer.from(stringifyJson(payload) || "");
      const key = "system:" + createHash("sha1").update(rawPayload).digest("hex");
      if (!this.rememberNotice(key)) return true;
      this.emitOneBotEvent(event);
      return true;
    } catch (error) {
      logErr(this.botConfig.id, "[事件] 系统消息转换失败:", error?.message || error);
      return false;
    }
  }
  rememberGroupInviteArk(message) {
    const invite = parseGroupInviteArk(message, this.getSelfUin());
    if (!invite) return false;
    const value = { ...invite, observedAt: Date.now() };
    const key = String(invite.groupId) + ":" + String(invite.inviterUid);
    this.oneBotGroupInviteArks.set(key, value);
    while (this.oneBotGroupInviteArks.size > 50) {
      this.oneBotGroupInviteArks.delete(this.oneBotGroupInviteArks.keys().next().value);
    }
    this.emitNativeEvent("group_invite_ark", value);
    return true;
  }
  async takeGroupInviteArk(groupId, inviterUid) {
    const key = String(groupId) + ":" + String(inviterUid);
    const now = Date.now();
    for (const [cacheKey, value] of this.oneBotGroupInviteArks) {
      if (Number(value?.observedAt || 0) < now - 10000) this.oneBotGroupInviteArks.delete(cacheKey);
    }
    let invite = this.oneBotGroupInviteArks.get(key) || null;
    if (!invite) {
      try {
        const waited = await this.waitForNativeEvent(
          "group_invite_ark",
          () => undefined,
          (value) => String(value?.groupId || "") === String(groupId)
            && String(value?.inviterUid || "") === String(inviterUid),
          () => false,
          1000,
        );
        invite = waited.args[0] || null;
      } catch {
      }
    }
    if (invite) this.oneBotGroupInviteArks.delete(key);
    return invite;
  }
  rememberGroupIncreaseCandidate(candidate) {
    const now = Date.now();
    for (const [key, value] of this.oneBotGroupIncreaseCandidates) {
      if (Number(value?.observedAt || 0) < now - 10000) this.oneBotGroupIncreaseCandidates.delete(key);
    }
    const key = [candidate.groupId, candidate.memberUid, candidate.operatorUid, candidate.seq].join(":");
    this.oneBotGroupIncreaseCandidates.set(key, candidate);
    while (this.oneBotGroupIncreaseCandidates.size > 1000) {
      this.oneBotGroupIncreaseCandidates.delete(this.oneBotGroupIncreaseCandidates.keys().next().value);
    }
    this.emitNativeEvent("group_increase_candidate", candidate);
  }
  async takeGroupIncreaseCandidate(groupId, operatorUid) {
    let candidate = findGroupIncreaseCandidate(
      this.oneBotGroupIncreaseCandidates.values(),
      groupId,
      operatorUid,
    );
    if (!candidate && operatorUid) {
      candidate = findGroupIncreaseCandidate(
        this.oneBotGroupIncreaseCandidates.values(),
        groupId,
      );
    }
    if (!candidate) {
      try {
        const waited = await this.waitForNativeEvent(
          "group_increase_candidate",
          () => undefined,
          (value) => String(value?.groupId || "") === String(groupId)
            && (!operatorUid || String(value?.operatorUid || "") === String(operatorUid)),
          () => false,
          1000,
        );
        candidate = waited.args[0] || null;
      } catch {
      }
    }
    if (!candidate) return null;
    for (const [key, value] of this.oneBotGroupIncreaseCandidates) {
      if (String(value?.groupId || "") === String(candidate.groupId)
        && String(value?.memberUid || "") === String(candidate.memberUid)) {
        this.oneBotGroupIncreaseCandidates.delete(key);
      }
    }
    return candidate;
  }
  async resolveGroupMemberUin(groupId, memberUid) {
    groupId = String(groupId || "");
    memberUid = String(memberUid || "");
    if (!memberUid) return "0";
    if (/^[1-9]\d*$/.test(memberUid)) return memberUid;
    const cachedMember = Array.from(this.oneBotGroupMemberSnapshots.get(groupId)?.values?.() || [])
      .find((member) => String(member?.uid || "") === memberUid);
    if (cachedMember?.uin && String(cachedMember.uin) !== "0") {
      return this.rememberUin(memberUid, cachedMember.uin);
    }
    const userId = await this.resolveUin(memberUid);
    if (userId !== "0" || !groupId) return userId;
    const key = `${groupId}:${memberUid}`;
    const pending = this.oneBotGroupUinPending.get(key);
    if (pending) return pending;
    const request = this.resolveGroupMemberUinUncached(groupId, memberUid);
    this.oneBotGroupUinPending.set(key, request);
    try {
      return await request;
    } finally {
      if (this.oneBotGroupUinPending.get(key) === request) this.oneBotGroupUinPending.delete(key);
    }
  }
  async resolveGroupMemberUinUncached(groupId, memberUid) {
    let userId = "0";
    const service = this.session?.getGroupService?.();
    if (typeof service?.getMemberInfo === "function") try {
      const hasMember = (value) => collectionValues(extractNativeMemberMap(value)).some(
        (member) => String(member?.uid || "") === String(memberUid),
      );
      const waited = await this.waitForNativeEvent(
        "member_info",
        () => service.getMemberInfo(String(groupId), [String(memberUid)], true),
        (callbackGroup, _source, members) => String(callbackGroup) === String(groupId)
          && collectionValues(members).some((member) => String(member?.uid || "") === String(memberUid)),
        hasMember,
        1500,
      );
      const infos = waited.direct !== null
        ? extractNativeMemberMap(waited.direct)
        : waited.args[2] || waited.args[1];
      const member = collectionValues(infos).find(
        (value) => String(value?.uid || "") === String(memberUid),
      );
      if (member?.uin && String(member.uin) !== "0") return this.rememberUin(memberUid, member.uin);
      userId = await this.resolveUin(memberUid);
    } catch {
    }
    if (userId === "0" && typeof service?.getAllMemberList === "function") {
      try {
        await this.queryGroupMemberList(groupId, { no_cache: true });
        userId = this.oneBotUidToUin.get(memberUid) || "0";
      } catch {
      }
    }
    return userId;
  }
  rememberGroupMemberSnapshot(groupCode, members) {
    const groupId = String(groupCode || "");
    if (!groupId) return false;
    const snapshot = new Map();
    for (const member of Array.from(members || [])) {
      const uid = String(member?.uid || "");
      const uin = String(member?.uin || member?.user_id || "");
      const key = uid || uin;
      if (key) snapshot.set(key, { uid, uin });
      if (uid && uin && uin !== "0") this.rememberUin(uid, uin);
    }
    if (!snapshot.size) return false;
    this.oneBotGroupMemberSnapshots.set(groupId, snapshot);
    while (this.oneBotGroupMemberSnapshots.size > 500) {
      this.oneBotGroupMemberSnapshots.delete(this.oneBotGroupMemberSnapshots.keys().next().value);
    }
    return true;
  }
  async createThirdPartyGroupIncreaseNotice(groupId) {
    const oldMembers = this.oneBotGroupMemberSnapshots.get(String(groupId));
    if (!oldMembers) return null;
    await this.queryGroupMemberList(String(groupId), { no_cache: true });
    const newMembers = this.oneBotGroupMemberSnapshots.get(String(groupId));
    if (!newMembers) return null;
    const member = findAddedGroupMember(oldMembers, newMembers);
    if (!member) return null;
    const userId = member.uin && member.uin !== "0"
      ? member.uin
      : await this.resolveGroupMemberUin(String(groupId), member.uid);
    if (!userId || userId === "0") return null;
    return {
      post_type: "notice", notice_type: "group_increase", sub_type: "invite",
      group_id: Number(groupId) || groupId,
      user_id: Number(userId) || userId,
      operator_id: 0,
    };
  }
  async rememberGroupCard(groupCode, member, emitChange = true) {
    const groupId = String(groupCode || member?.groupCode || "");
    let userId = String(member?.uin || member?.user_id || "");
    if (!userId && member?.uid) userId = String(await this.resolveUin(String(member.uid)) || "");
    if (!groupId || !userId) return false;
    const card = this.displayText(member?.cardName ?? member?.card ?? "");
    const key = groupId + ":" + userId;
    const previous = this.oneBotGroupCards.get(key);
    this.oneBotGroupCards.set(key, card);
    while (this.oneBotGroupCards.size > 5000) this.oneBotGroupCards.delete(this.oneBotGroupCards.keys().next().value);
    if (!emitChange || previous === undefined || previous === card) return false;
    const noticeKey = "card:" + key + ":" + card;
    if (!this.rememberNotice(noticeKey)) return true;
    this.emitOneBotEvent({
      post_type: "notice", notice_type: "group_card",
      group_id: Number(groupId) || groupId, user_id: Number(userId) || userId,
      card_new: card, card_old: previous,
    });
    return true;
  }
  async detectMessageGroupCard(msg) {
    if (Number(msg?.chatType) !== 2 || !msg?.senderUin || String(msg.senderUin) === "0") return false;
    return this.rememberGroupCard(msg.peerUid || msg.peerUin, {
      uin: msg.senderUin,
      cardName: msg.sendMemberName ?? "",
    });
  }
  waitForNativeEvent(key, trigger, matcher = () => true, directMatcher = () => false, timeout = 5000) {
    const normalizedKey = String(key || "");
    let pending;
    let triggerResult;
    let timer;
    let settled = false;
    const waiters = this.pendingNativeEvents.get(normalizedKey) || new Set();
    this.pendingNativeEvents.set(normalizedKey, waiters);
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      waiters.delete(pending);
      if (!waiters.size) this.pendingNativeEvents.delete(normalizedKey);
    };
    const promise = new Promise((resolve, reject) => {
      const finish = (value, failed = false) => {
        if (settled) return;
        settled = true;
        cleanup();
        if (failed) reject(value);
        else resolve(value);
      };
      pending = {
        match: (...args) => {
          try { return Boolean(matcher(...args)); } catch { return false; }
        },
        resolveEvent: (...args) => finish({ args, direct: null }),
        resolveDirect: (value) => finish({ args: [], direct: value }),
        reject: (error) => finish(error, true),
      };
      waiters.add(pending);
      timer = setTimeout(() => {
        try {
          if (directMatcher(triggerResult)) {
            pending.resolveDirect(triggerResult);
            return;
          }
        } catch {
        }
        pending.reject(new Error(`等待 QQNT 回调超时: ${normalizedKey}`));
      }, Math.max(100, Number(timeout) || 5000));
    });
    Promise.resolve().then(trigger).then((result) => {
      triggerResult = result;
      try {
        if (directMatcher(result)) pending.resolveDirect(result);
      } catch {
      }
    }).catch((error) => pending?.reject(error));
    return promise;
  }
  emitNativeEvent(key, ...args) {
    const waiters = this.pendingNativeEvents.get(String(key || ""));
    if (!waiters?.size) return;
    for (const waiter of Array.from(waiters)) {
      if (waiter.match(...args)) waiter.resolveEvent(...args);
    }
  }
  rememberNotice(key) {
    const normalized = String(key || "");
    if (!normalized || this.oneBotNoticeKeys.has(normalized)) return false;
    this.oneBotNoticeKeys.set(normalized, true);
    while (this.oneBotNoticeKeys.size > 1000) this.oneBotNoticeKeys.delete(this.oneBotNoticeKeys.keys().next().value);
    return true;
  }
  getRecallElement(message) {
    if (Number(message?.msgType || 0) !== 5) return null;
    return Array.from(message?.elements || []).find((item) => item?.grayTipElement?.revokeElement) || null;
  }
  isCurrentRecallUpdate(message) {
    if (!this.getRecallElement(message)) return false;
    const recallTime = Number(message?.recallTime || 0);
    if (!Number.isFinite(recallTime) || recallTime <= 0) return false;
    const seconds = recallTime > 1e10 ? recallTime / 1000 : recallTime;
    const startedAt = Number(this.incomingMessageGate?.startedAt || Math.floor(Date.now() / 1000));
    return seconds >= startedAt - 5;
  }
  async emitRecallNotice(message) {
    const element = this.getRecallElement(message);
    const revoke = element?.grayTipElement?.revokeElement;
    if (!revoke?.operatorUid) return false;
    const chatType = Number(message?.chatType || 0);
    if (![1, 2].includes(chatType)) return false;
    const key = "recall:" + chatType + ":" + String(message?.peerUid || message?.peerUin || "") + ":" + nativeMessageKey(message);
    if (!this.rememberNotice(key)) return true;
    const groupId = chatType === 2 ? String(message?.peerUin || message?.peerUid || "") : "";
    let senderId = String(message?.senderUin || "");
    if ((!senderId || senderId === "0") && message?.senderUid) {
      senderId = chatType === 2
        ? await this.resolveGroupMemberUin(groupId, String(message.senderUid))
        : await this.resolveUin(String(message.senderUid));
    }
    const event = {
      post_type: "notice",
      notice_type: chatType === 2 ? "group_recall" : "friend_recall",
      user_id: Number(senderId) || senderId || 0,
      message_id: toOneBotMessageId(nativeMessageKey(message), message),
    };
    if (chatType === 2) {
      const operatorId = await this.resolveGroupMemberUin(groupId, String(revoke.operatorUid));
      event.group_id = Number(groupId) || groupId || 0;
      event.operator_id = Number(operatorId) || operatorId || 0;
    }
    this.emitOneBotEvent(event);
    return true;
  }
  async grayTipNotice(element, msg) {
    const gray = element?.grayTipElement;
    if (!gray) return null;
    const groupId = String(msg?.peerUin || msg?.peerUid || "");
    const group = gray.groupElement;
    if (group && Number(group.type || 0) === 5) {
      const userId = await this.resolveGroupMemberUin(groupId, String(group.memberUid || msg?.senderUid || ""));
      return {
        post_type: "notice", notice_type: "notify", sub_type: "group_name",
        group_id: Number(groupId) || groupId, user_id: Number(userId) || userId || 0,
        name_new: String(group.groupName || ""),
      };
    }
    if (group && Number(group.type || 0) === 8 && group.shutUp) {
      const memberUid = String(group.shutUp?.member?.uid || group.memberUid || "");
      const userId = memberUid ? await this.resolveGroupMemberUin(groupId, memberUid) : "0";
      const operatorId = await this.resolveGroupMemberUin(groupId, String(group.shutUp?.admin?.uid || group.adminUid || ""));
      let duration = Math.max(0, Number(group.shutUp?.duration || 0));
      if (!memberUid && duration > 0) duration = -1;
      return {
        post_type: "notice", notice_type: "group_ban", sub_type: duration !== 0 ? "ban" : "lift_ban",
        group_id: Number(groupId) || groupId, user_id: Number(userId) || userId || 0,
        operator_id: Number(operatorId) || operatorId || 0, duration,
      };
    }
    if (group && Number(group.type || 0) === 1 && String(group.memberUid || "") === String(this.selfInfo?.uid || "")) {
      const userId = this.getSelfUin();
      const operatorId = await this.resolveGroupMemberUin(groupId, String(group.adminUid || ""));
      return {
        post_type: "notice", notice_type: "group_increase", sub_type: "approve",
        group_id: Number(groupId) || groupId, user_id: Number(userId) || userId || 0,
        operator_id: Number(operatorId) || operatorId || 0,
      };
    }
    const jsonTip = gray.jsonGrayTipElement;
    if (jsonTip) {
      let rawInfo = {};
      try { rawInfo = JSON.parse(String(jsonTip.jsonStr || "{}")); } catch {}
      const businessId = String(jsonTip.busiId || "");
      if (businessId === "1061") {
        const uids = Array.from(rawInfo?.items || []).map((item) => String(item?.uid || "")).filter(Boolean);
        if (uids.length >= 2) {
          const isGroup = Number(msg?.chatType) === 2;
          const identities = await Promise.all(uids.slice(0, 2).map((uid) =>
            isGroup ? this.resolveGroupMemberUin(groupId, uid) : this.resolveUin(uid)
          ));
          const peerId = isGroup ? "" : await this.resolveUin(String(msg?.peerUid || ""));
          return {
            post_type: "notice", notice_type: "notify", sub_type: "poke",
            user_id: isGroup ? Number(identities[0]) || identities[0] || 0 : Number(peerId) || peerId || 0,
            target_id: Number(identities[1]) || identities[1] || 0,
            group_id: isGroup ? Number(groupId) || groupId : undefined,
            sender_id: isGroup ? undefined : Number(identities[0]) || identities[0] || 0,
            raw_info: Array.from(rawInfo?.items || []),
          };
        }
      }
      if (businessId === "19324" && Number(msg?.chatType) === 1) {
        const userId = await this.resolveUin(String(msg?.peerUid || msg?.senderUid || ""));
        return { post_type: "notice", notice_type: "friend_add", user_id: Number(userId) || userId || 0 };
      }
      if (Number(msg?.chatType) !== 2) return null;
      if (businessId === "2401") {
        const essence = parseEssenceGrayTip(rawInfo);
        return essence ? await this.createEssenceNotice(essence) : null;
      }
      if (businessId === "51" && isThirdPartyGroupIncreaseGrayTip(rawInfo)) {
        return this.createThirdPartyGroupIncreaseNotice(groupId);
      }
      const grayItems = Array.from(rawInfo?.items || []);
      const grayType = String(grayItems.at(-1)?.txt || "");
      if (grayType === "头衔") {
        const memberUin = String(grayItems[1]?.param?.[0] || "");
        const title = grayItems[3]?.txt;
        if (memberUin && title !== undefined) {
          return {
            post_type: "notice", notice_type: "notify", sub_type: "title",
            group_id: Number(groupId) || groupId, user_id: Number(memberUin) || memberUin, title: String(title),
          };
        }
        return null;
      }
      if (grayType === "移出" || !(Number(msg?.senderUin || 0) || 0)) return null;
      return {
        post_type: "notice", notice_type: "notify", sub_type: "gray_tip",
        group_id: Number(msg?.chatType) === 2 ? Number(groupId) || groupId : undefined,
        user_id: Number(msg?.senderUin || 0) || 0,
        message_id: toOneBotMessageId(nativeMessageKey(msg), msg),
        busi_id: businessId,
        content: String(jsonTip.jsonStr || ""),
        raw_info: { msgSeq: msg?.msgSeq, msgTime: msg?.msgTime, msgId: msg?.msgId, json: rawInfo },
      };
    }
    if (Number(msg?.chatType) === 2 && String(gray.xmlElement?.templId || "") === "10382") {
      if (this.packetRuntime?.events?.available) return null;
      const like = parseEmojiLikeGrayTip(gray.xmlElement?.content);
      return like ? await this.createGroupEmojiLikeNotice(groupId, like) : null;
    }
    return null;
  }
  async queryGroupMessageBySeq(groupId, sequence, reverse = true) {
    const service = this.getMsgService();
    const peer = { chatType: 2, peerUid: String(groupId), guildId: "" };
    if (typeof service?.queryMsgsWithFilterEx === "function") {
      const result = await service.queryMsgsWithFilterEx("0", "0", String(sequence), {
        chatInfo: peer,
        filterMsgType: [],
        filterSendersUid: [],
        filterMsgToTime: "0",
        filterMsgFromTime: "0",
        isReverseOrder: reverse,
        isIncludeCurrent: true,
        pageLimit: 1,
      });
      const message = collectionValues(result?.msgList || result)[0];
      if (message) return message;
    }
    if (typeof service?.getMsgsBySeqAndCount === "function") {
      const result = await service.getMsgsBySeqAndCount(peer, String(sequence), 1, true, true);
      return collectionValues(result?.msgList || result)[0] || null;
    }
    return null;
  }
  async createGroupEmojiLikeNotice(groupId, like) {
    const raw = await this.queryGroupMessageBySeq(groupId, like.messageSeq, true);
    if (!raw) return null;
    return {
      post_type: "notice", notice_type: "group_msg_emoji_like",
      group_id: Number(groupId) || groupId,
      user_id: Number(like.senderUin) || like.senderUin || 0,
      message_id: toOneBotMessageId(nativeMessageKey(raw), raw),
      likes: [{ emoji_id: String(like.emojiId), count: Math.max(0, Number(like.count ?? 1)) }],
      is_add: Boolean(like.isAdd ?? true),
    };
  }
  async handlePacketEvent(packet) {
    if (Number(packet?.type) !== 1 || packet?.cmd !== "trpc.msg.olpush.OlPushService.MsgPush") return false;
    const reaction = parseGroupReactionPacket(packet?.hex_data);
    if (!reaction) return false;
    const senderUin = await this.resolveGroupMemberUin(reaction.groupId, reaction.operatorUid);
    if (!senderUin || senderUin === "0") return false;
    const notice = await this.createGroupEmojiLikeNotice(reaction.groupId, { ...reaction, senderUin });
    if (!notice) return false;
    const noticeKey = [
      "packet-reaction", String(packet?.seq || ""), reaction.groupId,
      reaction.messageSeq, senderUin, reaction.emojiId, reaction.isAdd ? "add" : "remove",
    ].join(":");
    if (!this.rememberNotice(noticeKey)) return true;
    this.emitOneBotEvent(notice);
    return true;
  }
  async createEssenceNotice(essence) {
    const raw = await this.queryGroupMessageBySeq(essence.groupId, essence.messageSeq, false);
    if (!raw) return null;
    let operatorId = 0;
    try {
      const entries = await this.getEssenceMessages({ group_id: essence.groupId });
      const current = entries.find((item) => String(item.msg_seq) === String(essence.messageSeq));
      operatorId = Number(current?.operator_id || 0);
    } catch {
    }
    let senderId = String(raw.senderUin || "");
    if ((!senderId || senderId === "0") && raw.senderUid) senderId = String(await this.resolveUin(String(raw.senderUid)));
    return {
      post_type: "notice", notice_type: "essence", sub_type: "add",
      group_id: Number(essence.groupId) || essence.groupId,
      user_id: Number(senderId) || senderId || 0,
      sender_id: Number(senderId) || senderId || 0,
      operator_id: operatorId,
      message_id: toOneBotMessageId(nativeMessageKey(raw), raw),
    };
  }
  async handleMessageSideEvents(msg) {
    const elements = Array.from(msg.elements || []);
    const results = await Promise.allSettled([
      this.detectMessageGroupCard(msg),
      ...elements.map((element) => this.grayTipNotice(element, msg)),
    ]);
    for (const [index, result] of results.entries()) {
      if (result.status === "rejected") {
        logErr(this.botConfig.id, "[事件] 消息附属事件转换失败:", result.reason?.message || result.reason);
        continue;
      }
      if (index === 0 || !result.value) continue;
      const notice = result.value;
      const noticeKey = "gray:" + nativeMessageKey(msg) + ":" + notice.notice_type + ":" + (notice.sub_type || "");
      if (this.rememberNotice(noticeKey)) this.emitOneBotEvent(notice);
    }
  }
  async handleMessage(msg, forceSent = false) {
    const elements = msg.elements || [];
    if (Number(msg?.msgType || 0) === 1 || !elements.length) return;
    const sideEvents = this.handleMessageSideEvents(msg);
    const event = await this.toOneBotEvent(msg);
    if (!event) {
      await Promise.allSettled([sideEvents]);
      return;
    }
    if (forceSent) {
      event.post_type = "message_sent";
      event.message_sent_type = "self";
    }
    const emitted = this.oneBotMessages.has(String(event.message_id));
    this.rememberOneBotMessage(event, nativeMessageKey(msg), msg);
    const forwardIds = [];
    for (const element of elements) {
      const ark = this.forwardArkData(element?.arkElement?.bytesData);
      if (ark?.meta?.detail?.resid) forwardIds.push(ark.meta.detail.resid);
      if (element?.multiForwardMsgElement?.resId) forwardIds.push(element.multiForwardMsgElement.resId);
    }
    if (forwardIds.length) this.rememberForwardReference(msg, forwardIds);
    if (elements.some((element) => resolveReplyReference(element, msg))) {
      try {
        await this.rememberReplyTargets(msg);
      } catch (error) {
        logErr(this.botConfig.id, "[消息] 回复目标缓存失败:", error?.message || error);
      }
    }
    if (!emitted) this.oneBotEventCallback?.(event);
    if (Number(msg.chatType) === 2) {
      for (const element of elements) {
        const file = element?.fileElement;
        const key = "upload:" + nativeMessageKey(msg) + ":" + (element.elementId || file?.fileUuid || "");
        if (!file || !this.rememberNotice(key)) continue;
        this.emitOneBotEvent({
          post_type: "notice", notice_type: "group_upload",
          group_id: event.group_id, user_id: event.user_id,
          file: {
            id: String(file.fileMd5 || file.fileUuid || element.elementId || ""), name: String(file.fileName || ""),
            size: Number(file.fileSize || 0), busid: Number(file.fileBizId || 0),
          },
        });
      }
    }
    await Promise.allSettled([sideEvents]);
  }
  rememberOneBotMessage(event, nativeId = "", rawMessage = null) {
    const messageId = String(event.message_id);
    this.oneBotMessages.set(messageId, event);
    if (nativeId) this.oneBotNativeMessageIds.set(messageId, String(nativeId));
    if (rawMessage) this.oneBotRawMessages.set(messageId, rawMessage);
    while (this.oneBotMessages.size > 500) {
      const oldest = this.oneBotMessages.keys().next().value;
      this.oneBotMessages.delete(oldest);
      this.oneBotNativeMessageIds.delete(oldest);
      this.oneBotRawMessages.delete(oldest);
    }
  }
  async rememberReplyTargets(msg) {
    for (const element of msg.elements || []) {
      const reference = resolveReplyReference(element, msg);
      if (!reference) continue;
      if (reference.record) {
        const event = await this.toOneBotEvent(reference.record);
        if (event) this.rememberOneBotMessage(event, reference.nativeId || nativeMessageKey(reference.record), reference.record);
        continue;
      }
      const isGroup = Number(msg.chatType) === 2;
      const target = {
        time: 0,
        self_id: Number(this.getSelfUin()) || this.getSelfUin(),
        post_type: "message",
        message_type: isGroup ? "group" : "private",
        sub_type: isGroup ? "normal" : "friend",
        message_id: reference.messageId,
        message_seq: reference.messageId,
        real_id: reference.messageId,
        real_seq: reference.sequence,
        user_id: Number(reference.senderUin) || reference.senderUin || 0,
        message: [],
        raw_message: "",
        message_format: "array",
        font: 14,
        sender: {
          user_id: Number(reference.senderUin) || reference.senderUin || 0,
          nickname: reference.senderName,
          card: reference.senderName,
        },
      };
      if (isGroup) target.group_id = Number(msg.peerUin) || msg.peerUin;
      this.rememberOneBotMessage(target, reference.nativeId);
    }
  }
  rememberOneBotFile(element, data) {
    const value = {
      path: String(data.path || data.file_path || element?.filePath || element?.sourcePath || ""),
      url: String(data.url || element?.url || element?.originImageUrl || ""),
      name: String(data.name || data.file_name || element?.fileName || ""),
      size: String(data.file_size || element?.fileSize || ""),
      element_id: String(data.element_id || data.elementId || ""),
    };
    const keys = [
      data.file_id,
      data.file,
      data.element_id,
      data.elementId,
      element?.fileUuid,
      element?.fileSubId,
      element?.fileName,
    ].map((item) => String(item || "")).filter(Boolean);
    for (const key of new Set(keys)) this.oneBotFiles.set(key, value);
    while (this.oneBotFiles.size > 2000) {
      this.oneBotFiles.delete(this.oneBotFiles.keys().next().value);
    }
  }
  async oneBotTextSegment(textElement) {
    return oneBotTextSegment(textElement, (uid) => this.resolveUin(uid));
  }
  async oneBotElement(element, msg) {
    const reference = resolveReplyReference(element, msg);
    if (reference) return { type: "reply", data: { id: String(reference.messageId) } };
    if (element?.textElement) return this.oneBotTextSegment(element.textElement);
    if (element?.picElement) {
      const pic = element.picElement;
      const file = String(pic.fileName || pic.filePath || pic.sourcePath || pic.fileUuid || "");
      const data = {
        summary: pic.summary === undefined ? undefined : String(pic.summary),
        file,
        sub_type: pic.picSubType === undefined ? undefined : Number(pic.picSubType),
        url: String(pic.originImageUrl || pic.url || ""),
        file_size: String(pic.fileSize || ""),
      };
      this.rememberOneBotFile(pic, {
        ...data,
        file_id: String(pic.fileUuid || element.elementId || file),
      });
      return { type: "image", data };
    }
    if (element?.fileElement) {
      const file = element.fileElement;
      const data = {
        file: String(file.fileName || ""),
        file_id: String(file.fileUuid || element.elementId || file.fileName || ""),
        file_size: String(file.fileSize || ""),
        url: file.url ? String(file.url) : undefined,
      };
      this.rememberOneBotFile(file, {
        ...data,
        name: String(file.fileName || ""),
        path: String(file.filePath || ""),
        element_id: String(element.elementId || ""),
      });
      if (Number(element.elementType) === 23 || Number(element.elementType) === 30) {
        const isDir = Number(element.elementType) === 30;
        return {
          type: "onlinefile",
          data: {
            msgId: String(msg.msgId || ""),
            elementId: String(element.elementId || ""),
            fileName: String(file.fileName || ""),
            fileSize: String(file.fileSize || ""),
            isDir,
          },
        };
      }
      return { type: "file", data };
    }
    if (element?.pttElement) {
      const ptt = element.pttElement;
      const fileCode = String(ptt.fileName || randomUUID().replace(/-/g, ""));
      const data = {
        file: fileCode,
        path: String(ptt.filePath || ""),
        url: ptt.url || ptt.filePath ? String(ptt.url || ptt.filePath) : undefined,
        file_size: String(ptt.fileSize || ""),
      };
      this.rememberOneBotFile(ptt, {
        ...data,
        file_id: fileCode,
      });
      return { type: "record", data };
    }
    if (element?.videoElement) {
      const video = element.videoElement;
      const fileCode = String(video.fileName || randomUUID().replace(/-/g, ""));
      const data = {
        file: fileCode,
        url: video.url || video.filePath ? String(video.url || video.filePath) : undefined,
        file_size: String(video.fileSize || ""),
      };
      this.rememberOneBotFile(video, {
        ...data,
        file_id: fileCode,
        path: String(video.filePath || ""),
      });
      return { type: "video", data };
    }
    if (element?.faceElement) {
      const face = element.faceElement;
      const faceIndex = Number(face.faceIndex || 0);
      if (Number(face.faceType) === 5) {
        return {
          type: "poke",
          data: { type: String(face.pokeType || 0), id: String(face.faceIndex || "") },
        };
      }
      if (faceIndex === 358) return { type: "dice", data: { result: String(face.resultId || "") } };
      if (faceIndex === 359) return { type: "rps", data: { result: String(face.resultId || "") } };
      return {
        type: "face",
        data: {
          id: String(face.faceIndex || ""),
          raw: face,
          resultId: face.resultId === undefined ? undefined : String(face.resultId),
          chainCount: face.chainCount === undefined ? undefined : Number(face.chainCount),
        },
      };
    }
    if (element?.marketFaceElement) {
      const face = element.marketFaceElement;
      const emojiId = String(face.emojiId || "");
      const dir = emojiId.slice(0, 2);
      const file = dir && emojiId ? dir + "-" + emojiId + ".gif" : emojiId || "market-face.gif";
      const url = dir && emojiId
        ? "https://gxh.vip.qq.com/club/item/parcel/item/" + dir + "/" + emojiId + "/raw300.gif"
        : "";
      return { type: "image", data: {
        summary: String(face.faceName || "[商城表情]"), file, url,
        key: String(face.key || ""), emoji_id: emojiId,
        emoji_package_id: Number(face.emojiPackageId || 0),
      } };
    }
    if (element?.arkElement) {
      const content = String(element.arkElement.bytesData || "");
      return { type: "json", data: { data: content } };
    }
    if (element?.structLongMsgElement) {
      return null;
    }
    if (element?.markdownElement) {
      const markdown = element.markdownElement;
      const fileSetId = String(markdown?.mdExtInfo?.flashTransferInfo?.filesetId || "");
      if (fileSetId) return { type: "flashtransfer", data: { fileSetId } };
      return { type: "markdown", data: { content: String(markdown.content || "") } };
    }
    if (element?.multiForwardMsgElement) {
      return {
        type: "forward",
        data: {
          id: String(msg.msgId || nativeMessageKey(msg)),
        },
      };
    }
    if (element?.shareLocationElement) {
      return null;
    }
    if (element?.walletElement) {
      return null;
    }
    return null;
  }
  toOneBotRawMessage(message) {
    return encodeOneBotCqMessage(message);
  }
  async toOneBotEvent(msg) {
    const converted = await Promise.allSettled(
      Array.from(msg.elements || []).map((element) => this.oneBotElement(element, msg))
    );
    const message = [];
    for (const result of converted) {
      if (result.status === "fulfilled") {
        if (result.value) message.push(result.value);
      } else {
        logErr(this.botConfig.id, "[消息] 消息段转换失败:", result.reason?.message || result.reason);
      }
    }
    const chatType = Number(msg.chatType || 0);
    if (![1, 2, 100].includes(chatType)) return null;
    let peerUin = String(msg.peerUin || "");
    if (chatType === 100) {
      try {
        const tempInfo = await this.getMsgService()?.getTempChatInfo?.(
          100, String(msg.senderUid || msg.peerUid || "")
        );
        peerUin = String(tempInfo?.tmpChatInfo?.groupCode || tempInfo?.groupCode || peerUin || "");
      } catch {
      }
    } else if ((!peerUin || peerUin === "0") && msg.peerUid) {
      peerUin = await this.resolveUin(String(msg.peerUid));
    }
    if (chatType !== 1 && (!peerUin || peerUin === "0")) return null;
    let senderUin = String(msg.senderUin || "");
    if ((!senderUin || senderUin === "0") && msg.senderUid) {
      senderUin = chatType === 2
        ? await this.resolveGroupMemberUin(peerUin, String(msg.senderUid))
        : await this.resolveUin(String(msg.senderUid));
    }
    if (!senderUin || senderUin === "0") return null;
    const messageId = toOneBotMessageId(nativeMessageKey(msg), msg);
    const isGroup = chatType === 2;
    const isTempGroup = chatType === 100;
    const isSelf = String(senderUin) === String(this.getSelfUin());
    const rawTime = Number(msg.msgTime || 0);
    const event = createOneBotEvent(this.getSelfUin(), isSelf ? "message_sent" : "message", {
      time: Number.parseInt(String(rawTime), 10) || Date.now(),
      message_type: isGroup ? "group" : "private",
      sub_type: isTempGroup ? "group" : isGroup ? "normal" : "friend",
      message_id: messageId,
      message_seq: messageId,
      real_id: messageId,
      real_seq: String(msg.msgSeq || ""),
      user_id: Number(senderUin) || senderUin || 0,
      message,
      raw_message: this.toOneBotRawMessage(message).trim(),
      message_format: "array",
      message_sent_type: isSelf ? "self" : undefined,
      font: 14,
      sender: {
        user_id: Number(senderUin) || senderUin || 0,
        nickname: this.displayText(msg.sendNickName) || this.displayText(msg.sendMemberName),
        card: this.displayText(msg.sendMemberName),
        ...(isGroup ? {
          role: Number(msg.roleType) === 4 ? "owner" : Number(msg.roleType) === 3 ? "admin" : "member",
        } : {}),
      },
    });
    const inlineKeyboard = extractInlineKeyboardButtons(msg.elements);
    if (inlineKeyboard.length) event._inline_keyboard = inlineKeyboard;
    if (isGroup || isTempGroup) {
      event.group_id = Number(peerUin) || peerUin;
      if (isGroup) event.group_name = this.displayText(msg.peerName) || this.displayText(msg.groupName);
      else event.temp_source = 0;
    }
    if (isSelf || !isGroup) {
      event.target_id = Number(peerUin) || peerUin || 0;
    }
    return event;
  }
}

const BOT_ID = process.env["ELAINAQQ_BOT_ID"] || "";
const MANAGER_URL = process.env["ELAINAQQ_MANAGER_URL"] || "http://127.0.0.1:30010";
const EMBEDDED = process.env["ELAINAQQ_EMBEDDED"] === "1";
let shuttingDown = false;
const lifecycleKeepAlive = setInterval(() => {}, 60_000);
if (process.env["ELAINAQQ_WORKER_TEST"] === "1") lifecycleKeepAlive.unref?.();
const _origLog = console.log.bind(console);
const _origErr = console.error.bind(console);
function _ts() {
  return (/* @__PURE__ */ new Date()).toLocaleString("zh-CN", { hour12: false });
}
console.log = (...args) => _origLog(`[${_ts()}]`, ...args);
console.error = (...args) => _origErr(`[${_ts()}]`, ...args);
let instance = null;
const managerChannel = new EmbeddedManagerChannel({
  botId: BOT_ID,
  managerUrl: MANAGER_URL,
  logger: (...args) => logErr(BOT_ID, ...args),
});
function embeddedBotConfig() {
  return {
    id: BOT_ID,
    uin: process.env["ELAINAQQ_BOT_UIN"] || "",
    nickname: "",
    enabled: true
  };
}
async function main() {
  console.log(`[工作进程] 启动机器人编号=${BOT_ID}，使用账号独立桥接通道`);
  console.log(`[工作进程] 桥接地址: ${MANAGER_URL}`);
  if (!EMBEDDED) {
    throw new Error("内置 QQ 桥接只能由框架启动");
  }
  if (!BOT_ID) {
    console.error("[工作进程] 缺少 ELAINAQQ_BOT_ID 环境变量");
    process.exit(1);
  }
  const botConfig = embeddedBotConfig();
  const qqPath = findQQPath();
  const qqInfo = getQQInfo(qqPath);
  const wrapper = loadWrapper(qqPath, qqInfo.version);
  console.log(`[工作进程] 原生封装已加载，QQ ${qqInfo.version}`);
  instance = new QQInstance(botConfig, qqInfo, wrapper, "");
  managerChannel.attach(instance);
  void managerChannel.start();
  try {
    await instance.start();
    process.exitCode = 0;
  } catch (e) {
    console.error("[工作进程] QQ 启动失败:", e.message);
    try {
      await instance?.stop();
    } catch (stopError) {
      console.error("[工作进程] QQ 失败清理异常:", stopError?.message || stopError);
    }
    managerChannel.stop();
    setTimeout(() => process.exit(1), 500);
  }
}
process.on("SIGTERM", async () => {
  shuttingDown = true;
  console.log("[工作进程] 收到 SIGTERM");
  managerChannel.stop();
  clearInterval(lifecycleKeepAlive);
  if (instance) await instance.stop();
  process.exit(0);
});
process.on("SIGINT", async () => {
  shuttingDown = true;
  managerChannel.stop();
  clearInterval(lifecycleKeepAlive);
  if (instance) await instance.stop();
  process.exit(0);
});
process.on("uncaughtException", (error) => {
  console.error("[工作进程] 未捕获异常:", error?.stack || error);
});
process.on("unhandledRejection", (reason) => {
  console.error("[工作进程] 未处理的 Promise 异常:", reason?.stack || reason);
});
process.on("beforeExit", (code) => {
  if (!shuttingDown && process.env["ELAINAQQ_WORKER_TEST"] !== "1") {
    console.error("[工作进程] 事件循环意外结束，退出码: " + code);
  }
});
if (process.env["ELAINAQQ_WORKER_TEST"] !== "1") {
  main().catch((e) => {
    console.error("[工作进程] 启动失败:", e);
    clearInterval(lifecycleKeepAlive);
    process.exit(1);
  });
}

export { QQInstance };
