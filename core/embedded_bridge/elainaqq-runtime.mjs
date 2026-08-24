import http from 'http';
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
import { nativeMessageKey, resolveReplyReference, toOneBotMessageId } from './message_identity.mjs';
import {
  ONEBOT_ACTIONS,
  OneBotActionError,
  assertKnownOneBotAction,
  checkNativeResult,
  normalizeOneBotAction,
  requireNativeMethod
} from './onebot_action_contract.mjs';

const BUILTIN_QQ_VERSION = "3.2.32-52194";
const AppidTable = {
  "3.2.12-28060": { appid: "537246140", qua: "V1_LNX_NQ_3.2.12_28060_GW_B" },
  "3.2.12-28131": { appid: "537246140", qua: "V1_LNX_NQ_3.2.12_28131_GW_B" },
  "3.2.12-28327": { appid: "537249393", qua: "V1_LNX_NQ_3.2.12_28327_GW_B" },
  "3.2.12-28418": { appid: "537249393", qua: "V1_LNX_NQ_3.2.12_28418_GW_B" },
  "3.2.13-28788": { appid: "537249787", qua: "V1_LNX_NQ_3.2.13_28788_GW_B" },
  "3.2.13-28971": { appid: "537249848", qua: "V1_LNX_NQ_3.2.13_28971_GW_B" },
  "3.2.13-29271": { appid: "537249913", qua: "V1_LNX_NQ_3.2.13_29271_GW_B" },
  "3.2.13-29456": { appid: "537249996", qua: "V1_LNX_NQ_3.2.13_29456_GW_B" },
  "3.2.13-29927": { appid: "537255847", qua: "V1_LNX_NQ_3.2.13_29927_GW_B" },
  "3.2.15-30366": { appid: "537258413", qua: "V1_LNX_NQ_3.2.15_30366_GW_B" },
  "3.2.15-30483": { appid: "537258474", qua: "V1_LNX_NQ_3.2.15_30483_GW_B" },
  "3.2.15-30594": { appid: "537258474", qua: "V1_LNX_NQ_3.2.15_30594_GW_B" },
  "3.2.15-30851": { appid: "537263831", qua: "V1_LNX_NQ_3.2.15_30851_GW_B" },
  "3.2.15-30899": { appid: "537263831", qua: "V1_LNX_NQ_3.2.15_30899_GW_B" },
  "3.2.15-31245": { appid: "537266485", qua: "V1_LNX_NQ_3.2.15_31245_GW_B" },
  "3.2.15-31363": { appid: "537266535", qua: "V1_LNX_NQ_3.2.15_31363_GW_B" },
  "3.2.16-32690": { appid: "537271229", qua: "V1_LNX_NQ_3.2.16_32690_GW_B" },
  "3.2.16-32721": { appid: "537271229", qua: "V1_LNX_NQ_3.2.16_32721_GW_B" },
  "3.2.16-32793": { appid: "537271279", qua: "V1_LNX_NQ_3.2.16_32793_GW_B" },
  "3.2.16-32869": { appid: "537271329", qua: "V1_LNX_NQ_3.2.16_32869_GW_B" },
  "3.2.16-33139": { appid: "537273909", qua: "V1_LNX_NQ_3.2.16_33139_GW_B" },
  "3.2.16-33800": { appid: "537274009", qua: "V1_LNX_NQ_3.2.16_33800_GW_B" },
  "3.2.17-34231": { appid: "537279245", qua: "V1_LNX_NQ_3.2.17_34231_GW_B" },
  "3.2.17-34362": { appid: "537279296", qua: "V1_LNX_NQ_3.2.17_34362_GW_B" },
  "3.2.17-34467": { appid: "537282292", qua: "V1_LNX_NQ_3.2.17_34467_GW_B" },
  "3.2.17-34566": { appid: "537282343", qua: "V1_LNX_NQ_3.2.17_34566_GW_B" },
  "3.2.17-34606": { appid: "537282343", qua: "V1_LNX_NQ_3.2.17_34606_GW_B" },
  "3.2.17-34740": { appid: "537290727", qua: "V1_LNX_NQ_3.2.17_34740_GW_B" },
  "3.2.17-35184": { appid: "537291084", qua: "V1_LNX_NQ_3.2.17_35184_GW_B" },
  "3.2.17-35341": { appid: "537291383", qua: "V1_LNX_NQ_3.2.17_35341_GW_B" },
  "3.2.18-35951": { appid: "537296013", qua: "V1_LNX_NQ_3.2.18_35951_GW_B" },
  "3.2.18-36580": { appid: "537298509", qua: "V1_LNX_NQ_3.2.18_36580_GW_B" },
  "3.2.18-37012": { appid: "537304107", qua: "V1_LNX_NQ_3.2.18_37012_GW_B" },
  "3.2.18-37051": { appid: "537304158", qua: "V1_LNX_NQ_3.2.18_37051_GW_B" },
  "3.2.18-37475": { appid: "537304210", qua: "V1_LNX_NQ_3.2.18_37475_GW_B" },
  "3.2.18-37625": { appid: "537304261", qua: "V1_LNX_NQ_3.2.18_37625_GW_B" },
  "3.2.19-38503": { appid: "537307640", qua: "V1_LNX_NQ_3.2.19_38503_GW_B" },
  "3.2.19-38626": { appid: "537307691", qua: "V1_LNX_NQ_3.2.19_38626_GW_B" },
  "3.2.19-38960": { appid: "537313891", qua: "V1_LNX_NQ_3.2.19_38960_GW_B" },
  "3.2.19-39038": { appid: "537313942", qua: "V1_LNX_NQ_3.2.19_39038_GW_B" },
  "3.2.20-40768": { appid: "537319840", qua: "V1_LNX_NQ_3.2.20_40768_GW_B" },
  "3.2.20-40824": { appid: "537319840", qua: "V1_LNX_NQ_3.2.20_40824_GW_B" },
  "3.2.20-40990": { appid: "537319891", qua: "V1_LNX_NQ_3.2.20_40990_GW_B" },
  "3.2.21-41857": { appid: "537320197", qua: "V1_LNX_NQ_3.2.21_41857_GW_B" },
  "3.2.21-42086": { appid: "537320248", qua: "V1_LNX_NQ_3.2.21_42086_GW_B" },
  "3.2.22-42941": { appid: "537328659", qua: "V1_LNX_NQ_3.2.22_42941_GW_B" },
  "3.2.23-44343": { appid: "537336639", qua: "V1_LNX_NQ_3.2.23_44343_GW_B" },
  "3.2.25-45758": { appid: "537340249", qua: "V1_LNX_NQ_3.2.25_45758_GW_B" },
  "3.2.30-50828": { appid: "537358775", qua: "V1_LNX_NQ_3.2.30_50828_GW_B" },
  "3.2.30-50969": { appid: "537376344", qua: "V1_LNX_NQ_3.2.30_50969_GW_B" },
  "3.2.32-52194": { appid: "537379447", qua: "V1_LNX_NQ_3.2.32_52194_GW_B" }
};
function findQQPath() {
  if (process.env["QQ_PATH"]) return process.env["QQ_PATH"];
  if (os.platform() === "linux") {
    for (const p of ["/opt/QQ/qq", "/usr/share/qq/qq"]) {
      if (fs.existsSync(p)) return p;
    }
  } else if (os.platform() === "win32") {
    const commonPaths = [
      "C:\\Program Files\\Tencent\\QQNT\\QQ.exe",
      "C:\\Program Files (x86)\\Tencent\\QQNT\\QQ.exe",
      path.join(os.homedir(), "AppData\\Local\\Programs\\Tencent\\QQNT\\QQ.exe")
    ];
    for (const p of commonPaths) {
      if (fs.existsSync(p)) return p;
    }
  } else if (os.platform() === "darwin") {
    const macPath = "/Applications/QQ.app/Contents/MacOS/QQ";
    if (fs.existsSync(macPath)) return macPath;
  }
  throw new Error("未找到 QQ 安装路径，请设置环境变量 QQ_PATH");
}
function getQQInfo(execPath) {
  if (process.env["QQ_VERSION"]) {
    const version = process.env["QQ_VERSION"];
    console.log(`[QQInfo] 使用环境变量指定版本: ${version}`);
    return buildQQInfo(execPath, version);
  }
  let versionConfigPath;
  if (os.platform() === "win32") {
    versionConfigPath = path.join(path.dirname(execPath), "versions", "config.json");
  } else if (os.platform() === "darwin") {
    versionConfigPath = path.resolve(os.homedir(), "./Library/Application Support/QQ/versions/config.json");
  } else {
    versionConfigPath = path.resolve(os.homedir(), "./.config/QQ/versions/config.json");
  }
  if (versionConfigPath && !fs.existsSync(versionConfigPath)) {
    const alt = path.join(path.dirname(execPath), "./resources/app/versions/config.json");
    versionConfigPath = fs.existsSync(alt) ? alt : void 0;
  }
  if (versionConfigPath && fs.existsSync(versionConfigPath)) {
    try {
      const versionConfig = JSON.parse(fs.readFileSync(versionConfigPath, "utf-8"));
      console.log(`[QQInfo] 使用快更配置: ${versionConfig.curVersion}`);
      return buildQQInfo(execPath, versionConfig.curVersion);
    } catch (e) {
      console.log(`[QQInfo] 读取快更配置失败: ${e}`);
    }
  }
  let pkgPath;
  if (os.platform() === "darwin") {
    pkgPath = path.join(path.dirname(execPath), "..", "Resources", "app", "package.json");
  } else if (os.platform() === "linux") {
    pkgPath = path.join(path.dirname(execPath), "./resources/app/package.json");
  } else {
    pkgPath = path.join(path.dirname(execPath), "./resources/app/package.json");
  }
  if (fs.existsSync(pkgPath)) {
    try {
      const packageInfo = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
      if (packageInfo.version) {
        console.log(`[QQInfo] 从 package.json 读取: ${packageInfo.version}`);
        return buildQQInfo(execPath, packageInfo.version);
      }
    } catch (e) {
      console.log(`[QQInfo] 读取 package.json 失败: ${e}`);
    }
  }
  console.log(`[QQInfo] 使用内置版本: ${BUILTIN_QQ_VERSION}`);
  return buildQQInfo(execPath, BUILTIN_QQ_VERSION);
}
function buildQQInfo(execPath, version) {
  const buildVersion = version.split("-")[1] || "";
  let appid;
  let qua;
  if (AppidTable[version]) {
    appid = AppidTable[version].appid;
    qua = AppidTable[version].qua;
  } else {
    // 未知版本从 QQ native 模块读取 AppID。
    appid = readAppidFromMajor(execPath, version);
    const platformAppid = { win32: "537246092", darwin: "537246140", linux: "537246140" };
    appid = appid || platformAppid[os.platform()] || "537246092";
    const platformPrefix = { win32: "WIN", darwin: "MAC", linux: "LNX" };
    const prefix = platformPrefix[os.platform()] || "WIN";
    const productVersion = version.split("-")[0] || version;
    qua = `V1_${prefix}_NQ_${productVersion}_${buildVersion}_GW_B`;
  }
  console.log(`[QQInfo] version=${version}, appid=${appid}, qua=${qua}`);
  return { execPath, version, buildVersion, appid, qua };
}
function majorPathCandidates(execPath, version) {
  const base = path.dirname(execPath);
  if (os.platform() === "darwin") return [path.resolve(base, "../Resources/app/major.node")];
  if (os.platform() === "linux") return [path.resolve(base, "resources/app/major.node"), path.resolve(base, "resources/app/resources/app/major.node")];
  return [path.resolve(base, "versions/" + version + "/resources/app/major.node"), path.resolve(base, "resources/app/major.node"), path.resolve(base, "resources/app/versions/" + version + "/major.node")];
}
function readAppidFromMajor(execPath, version) {
  let majorPath = majorPathCandidates(execPath, version).find((candidate) => fs.existsSync(candidate));
  if (!majorPath && os.platform() === "win32") {
    const versionsDir = path.join(path.dirname(execPath), "versions");
    if (fs.existsSync(versionsDir)) {
      const candidates = fs.readdirSync(versionsDir).map((name) => path.join(versionsDir, name, "resources", "app", "major.node")).filter((candidate) => fs.existsSync(candidate));
      majorPath = candidates[candidates.length - 1];
    }
  }
  if (!majorPath) return "";
  try {
    const content = fs.readFileSync(majorPath);
    const marker = Buffer.from("QQAppId/", "utf8");
    let offset = 0;
    while (offset < content.length) {
      const index = content.indexOf(marker, offset);
      if (index < 0) break;
      const start = index + marker.length;
      const end = content.indexOf(0, start);
      if (end < 0) break;
      const value = content.subarray(start, end).toString("utf8");
      if (/^\d+$/.test(value)) return value;
      offset = end + 1;
    }
    const legacyMarker = Buffer.from([0xA4, 0x09, 0x00, 0x00, 0x00, 0x35]);
    offset = 0;
    while (offset < content.length) {
      const index = content.indexOf(legacyMarker, offset);
      if (index < 0) break;
      const start = index + legacyMarker.length - 1;
      const end = content.indexOf(0, start);
      if (end < 0) break;
      const value = content.subarray(start, end).toString('utf8');
      if (/^\d+$/.test(value)) return value;
      offset = end + 1;
    }
  } catch (error) {
    console.log("[QQInfo] 读取 major.node AppID 失败: " + error.message);
  }
  return "";
}
function loadWrapper(execPath, version) {
  if (globalThis.__ELAINAQQ_WRAPPER__) return globalThis.__ELAINAQQ_WRAPPER__;
  const configuredWrapper = process.env["ELAINAQQ_WRAPPER_PATH"];
  if (configuredWrapper) {
    const mod2 = { exports: {} };
    process.dlopen(mod2, configuredWrapper);
    return mod2.exports;
  }
  let appPath;
  if (os.platform() === "darwin") {
    appPath = path.resolve(path.dirname(execPath), "../Resources/app");
  } else if (os.platform() === "linux") {
    appPath = path.resolve(path.dirname(execPath), "./resources/app");
  } else {
    appPath = path.resolve(path.dirname(execPath), `./versions/${version}/`);
  }
  let wrapperPath = path.resolve(appPath, "wrapper.node");
  if (!fs.existsSync(wrapperPath)) {
    wrapperPath = path.join(appPath, "./resources/app/wrapper.node");
  }
  if (!fs.existsSync(wrapperPath)) {
    wrapperPath = path.join(path.dirname(execPath), `./resources/app/versions/${version}/wrapper.node`);
  }
  if (!fs.existsSync(wrapperPath) && os.platform() === "win32") {
    const versionsDir = path.join(path.dirname(execPath), "versions");
    if (fs.existsSync(versionsDir)) {
      const candidates = fs.readdirSync(versionsDir).map((name) => path.join(versionsDir, name, "resources", "app", "wrapper.node")).filter((candidate) => fs.existsSync(candidate)).sort();
      if (candidates.length) wrapperPath = candidates[candidates.length - 1];
    }
  }
  if (!fs.existsSync(wrapperPath)) {
    throw new Error(`wrapper.node 未找到: ${wrapperPath}`);
  }
  const mod = { exports: {} };
  process.dlopen(mod, wrapperPath);
  process.env["ELAINAQQ_WRAPPER_PATH"] = wrapperPath;
  return mod.exports;
}
function getDataPaths(wrapper) {
  const configuredDataPath = process.env["ELAINAQQ_DATA_DIR"];
  if (configuredDataPath) {
    const dataPath2 = path.resolve(configuredDataPath);
    fs.mkdirSync(dataPath2, { recursive: true });
    const dataPathGlobal2 = path.resolve(dataPath2, "./nt_qq/global");
    fs.mkdirSync(dataPathGlobal2, { recursive: true });
    return [dataPath2, dataPathGlobal2];
  }
  if (os.platform() === "darwin") {
    const appDataPath = path.resolve(os.homedir(), "./Library/Application Support/QQ");
    return [appDataPath, path.join(appDataPath, "global")];
  }
  let dataPath = "";
  try {
    dataPath = wrapper.NodeQQNTWrapperUtil.getNTUserDataInfoConfig();
  } catch {
  }
  if (!dataPath) {
    dataPath = path.resolve(os.homedir(), "./.config/QQ");
    fs.mkdirSync(dataPath, { recursive: true });
  }
  const dataPathGlobal = path.resolve(dataPath, "./nt_qq/global");
  return [dataPath, dataPathGlobal];
}

const botUinMap = /* @__PURE__ */ new Map();
function botTag(botId) {
  return botUinMap.get(botId) || botId.slice(0, 8);
}
function log(botId, ...args) {
  console.log(`[Bot ${botTag(botId)}]`, ...args);
}
function logErr(botId, ...args) {
  console.error(`[Bot ${botTag(botId)}]`, ...args);
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
function encodeProtoVarint(value) {
  let remaining = BigInt(value);
  if (remaining < 0n) throw new Error("protobuf varint 不能为负数");
  const bytes = [];
  do {
    let byte = Number(remaining & 0x7fn);
    remaining >>= 7n;
    if (remaining) byte |= 0x80;
    bytes.push(byte);
  } while (remaining);
  return Buffer.from(bytes);
}
function encodeProtoVarintField(fieldNumber, value) {
  return Buffer.concat([
    encodeProtoVarint(BigInt(fieldNumber) << 3n),
    encodeProtoVarint(value),
  ]);
}
function encodeProtoBytesField(fieldNumber, value) {
  const bytes = Buffer.from(value);
  return Buffer.concat([
    encodeProtoVarint((BigInt(fieldNumber) << 3n) | 2n),
    encodeProtoVarint(bytes.length),
    bytes,
  ]);
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
  statusCallback = null;
  oneBotEventCallback = null;
  redPacketCallback = null;
  oneBotMessages = /* @__PURE__ */ new Map();
  oneBotNativeMessageIds = /* @__PURE__ */ new Map();
  oneBotRawMessages = /* @__PURE__ */ new Map();
  oneBotForwardMessages = /* @__PURE__ */ new Map();
  pendingSentMessages = /* @__PURE__ */ new Set();
  forwardSendTail = Promise.resolve();
  oneBotFiles = /* @__PURE__ */ new Map();
  oneBotFileStreams = /* @__PURE__ */ new Map();
  oneBotStreamFiles = /* @__PURE__ */ new Set();
  oneBotOnlineClients = [];
  redPackets = /* @__PURE__ */ new Map();
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
      log(id, "步骤6: 注册消息监听...");
      this.registerMsgListener();
      this.registerEventListeners();
      this.botConfig.uin = this.selfInfo.uin;
      this.botConfig.nickname = this.selfInfo.nick || this.selfInfo.uin;
      botUinMap.set(this.botConfig.id, this.selfInfo.uin);
      this.setStatus("online", {
        loginUin: this.selfInfo.uin,
        nickname: this.botConfig.nickname,
      });
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
    throw new Error(`QQNT session API 不兼容: ${JSON.stringify(methods)}${detail}`);
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
      for (const pending of Array.from(this.pendingSentMessages)) {
        pending.reject(new OneBotActionError("QQ 会话已停止", 1500, "send_msg"));
      }
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
  getMsgService() {
    return this.session?.getMsgService();
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
        return { online: this.runtime.status === "online", good: this.runtime.status === "online" };
      case "get_version_info":
        return {
          app_name: "ElainaQQ Embedded QQ",
          app_version: this.qqInfo.version,
          protocol_version: "v11",
          supported_actions: Array.from(ONEBOT_ACTIONS).sort(),
        };
      case "can_send_image":
        return { yes: true };
      case "can_send_record":
        return { yes: true };
      case "get_msg":
        return this.getOneBotMessage(String(params.message_id));
      case "get_group_list":
        return this.queryGroupList();
      case "get_group_info":
        return this.queryGroupInfo(String(params.group_id));
      case "get_group_member_list":
        return this.queryGroupMemberList(String(params.group_id));
      case "get_group_member_info":
        return this.queryGroupMemberInfo(String(params.group_id), String(params.user_id));
      case "get_friend_list":
        return this.queryFriendList();
      case "get_stranger_info":
        return this.queryStrangerInfo(params);
      case "delete_msg":
        return this.deleteOneBotMessage(String(params.message_id));
      case "mark_group_msg_as_read":
        return this.markOneBotMessageRead("group", String(params.group_id));
      case "mark_private_msg_as_read":
        return this.markOneBotMessageRead("private", String(params.user_id));
      case "set_group_kick":
        return this.setGroupKick(String(params.group_id), String(params.user_id), this.asBoolean(params.reject_add_request));
      case "set_group_ban":
        return this.setGroupBan(String(params.group_id), String(params.user_id), Number(params.duration || 0));
      case "set_group_whole_ban":
        return this.setGroupWholeBan(String(params.group_id), this.asBoolean(params.enable, true));
      case "set_group_admin":
        return this.setGroupAdmin(String(params.group_id), String(params.user_id), this.asBoolean(params.enable, true));
      case "set_group_card":
        return this.setGroupCard(String(params.group_id), String(params.user_id), String(params.card || ""));
      case "set_group_name":
        return this.setGroupName(String(params.group_id), String(params.group_name || ""));
      case "set_group_leave":
        return this.setGroupLeave(String(params.group_id));
      case "send_like":
        return this.sendLike(String(params.user_id), Number(params.times || 1));
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
        return {};
      case "bot_exit":
        await this.stop();
        return {};
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
        return this.markAllOneBotMessagesRead();
      case "mark_msg_as_read":
        return this.markCachedOneBotMessageRead(String(params.message_id));
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
        return this.deleteFriend(params);
      case "set_friend_remark":
        return this.setFriendRemark(params);
      case "set_friend_add_request":
        return this.setFriendAddRequest(params);
      case "get_doubt_friends_add_request":
        return this.getDoubtFriendRequests(params);
      case "set_doubt_friends_add_request":
        return this.setDoubtFriendRequest(params);
      case "get_group_system_msg":
      case "get_group_ignored_notifies":
      case "get_group_ignore_add_request":
        return this.getGroupRequests(params);
      case "set_group_add_request":
      case "set_group_add_option":
      case "set_group_robot_add_option":
        return this.setGroupAddRequest(params);
      case "get_group_shut_list":
        return this.getGroupShutList(String(params.group_id));
      case "set_group_kick_members":
        return this.setGroupKickMembers(params);
      case "set_group_remark":
        return this.setGroupRemark(params);
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
        return this.setOnlineStatus(params);
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
        return this.setQqAvatar(params);
      case "send_packet":
        return this.sendNativePacket(params);
      case "get_packet_status":
      case "nc_get_packet_status":
        return { enabled: typeof this.getMsgService()?.sendSsoCmdReqByContend === "function" };
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
        return this.restartEmbeddedQq();
      case "send_poke":
      case "friend_poke":
      case "group_poke":
        return this.sendPoke(params);
      case "set_group_special_title":
        return this.setGroupSpecialTitle(params);
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
        return {};
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
      case "set_group_member_invite_policy":
      case "set_group_member_permissions":
      case "set_group_new_member_history_visibility":
      case "set_group_search":
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
      ? raw?.peerUid || event._peer_uid || event.user_id
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
    const messages = Array.from(result?.msgList || []).map((record) => {
      const event = this.toOneBotEvent(record);
      this.rememberOneBotMessage(event, nativeMessageKey(record), record);
      return event;
    });
    const oldest = messages.reduce((current, event) => {
      if (!current) return event;
      return Number(event.time || 0) < Number(current.time || 0) ? event : current;
    }, null);
    return {
      messages,
      next_cursor: String(oldest?.message_seq || oldest?.real_seq || ""),
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
      toOneBotMessageId(nativeMessageKey(raw)),
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
    const messageId = toOneBotMessageId(rawId);
    const ark = Array.from(raw.elements || []).map((element) => this.forwardArkData(element?.arkElement?.bytesData)).find(Boolean);
    const forwardElement = Array.from(raw.elements || []).find((element) => element?.multiForwardMsgElement)?.multiForwardMsgElement;
    const forwardId = String(ark?.meta?.detail?.resid || forwardElement?.resId || rawId);
    const event = this.toOneBotEvent(raw);
    this.rememberOneBotMessage(event, rawId, raw);
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
        let segment = this.oneBotElement(element, raw);
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
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getGroupDetailInfo", "get_group_detail_info");
    const result = await method(groupId, 0);
    checkNativeResult(result, "获取群详情失败");
    const data = result?.data || result?.groupInfo || result?.result || result || {};
    return {
      ...(await this.queryGroupInfo(groupId)),
      group_memo: String(data.groupMemo || data.group_memo || ""),
      group_create_time: Number(data.groupCreateTime || data.createTime || 0),
      group_level: Number(data.groupLevel || 0),
      member_count: Number(data.memberNum || data.member_count || 0),
      max_member_count: Number(data.maxMemberNum || data.max_member_count || 0),
    };
  }
  async queryFriendsWithCategory() {
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "getBuddyListV2", "get_friends_with_category");
    const result = await method("ElainaQQ", true, 0);
    checkNativeResult(result, "获取好友分组失败");
    return Promise.all(Array.from(result?.data || []).map(async (category) => ({
      categoryId: Number(category.categoryId || 0),
      categorySortId: Number(category.categorySortId || 0),
      categoryName: String(category.categroyName || category.categoryName || ""),
      categoryMbCount: Number(category.categroyMbCount || 0),
      onlineCount: Number(category.onlineCount || 0),
      buddyList: await Promise.all(Array.from(category.buddyUids || []).map(async (uid) => {
        const uin = await this.resolveUin(uid);
        return {
          user_id: Number(uin) || uin,
          nickname: String(service.getBuddyNick?.(uid) || ""),
          remark: String(service.getBuddyRemark?.(uid) || ""),
        };
      })),
    })));
  }
  async resolveUin(uid) {
    if (!uid) return "";
    try {
      const converted = await this.session?.getUixConvertService?.().getUin([uid]);
      const uin = converted?.uinInfo?.get?.(uid);
      if (uin) return String(uin);
    } catch {
    }
    try {
      const uin = this.session?.getProfileService?.().getUinByUid("FriendsServiceImpl", [uid])?.get?.(uid);
      if (uin) return String(uin);
    } catch {
    }
    return String(uid);
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
    const result = await getRequests();
    const flag = String(params.flag || "");
    const request = Array.from(result?.buddyReqs || result?.data || []).find((item) => String(item.reqTime || item.flag) === flag);
    if (!request) throw new OneBotActionError("好友请求不存在或已过期", 1404, "set_friend_add_request");
    const approve = requireNativeMethod(service, "approvalFriendRequest", "set_friend_add_request");
    await approve({ friendUid: String(request.friendUid || request.uid), reqTime: flag, accept: this.asBoolean(params.approve, true) });
    if (params.remark) {
      const setRemark = requireNativeMethod(service, "setBuddyRemark", "set_friend_add_request");
      await setRemark({ uid: String(request.friendUid || request.uid), remark: String(params.remark) });
    }
    return {};
  }
  async getDoubtFriendRequests(params) {
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "getDoubtBuddyReq", "get_doubt_friends_add_request");
    return await method(String(params.req_id || ""), Math.max(1, Number(params.count || 50)), String(params.uk || ""));
  }
  async setDoubtFriendRequest(params) {
    const service = this.session?.getBuddyService?.();
    const method = requireNativeMethod(service, "approvalDoubtBuddyReq", "set_doubt_friends_add_request");
    await method(String(params.user_id || params.uid || ""), String(params.flag || params.req_id || ""), this.asBoolean(params.approve, true) ? "1" : "0");
    return {};
  }
  groupRequestList(result) {
    const candidates = result?.notifies || result?.notifyList || result?.data || result?.result?.notifies || [];
    return Array.from(candidates instanceof Map ? candidates.values() : candidates || []);
  }
  async loadGroupRequests(doubt, params = {}) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getSingleScreenNotifies", "get_group_system_msg");
    const result = await method(doubt, String(params.start_seq || "0"), Math.min(200, Math.max(1, Number(params.count || 100))));
    checkNativeResult(result, "获取群系统消息失败");
    return this.groupRequestList(result).map((notify) => ({ ...notify, _doubt: doubt }));
  }
  groupRequestToOneBot(notify) {
    const groupId = String(notify?.group?.groupCode || notify?.groupCode || "");
    return {
      request_id: String(notify?.seq || notify?.flag || ""),
      invitor_uin: Number(notify?.user2?.uin || 0),
      invitor_nick: String(notify?.user2?.nickName || ""),
      group_id: Number(groupId) || groupId,
      group_name: String(notify?.group?.groupName || ""),
      checked: Number(notify?.status || 0) !== 0,
      actor: Number(notify?.actionUser?.uin || 0),
      requester_uid: String(notify?.user1?.uid || notify?.actionUser?.uid || notify?.userUid || ""),
      message: String(notify?.postscript || ""),
      flag: String(notify?.seq || notify?.flag || ""),
      sub_type: notify?.invitationExt ? "invite" : "add",
    };
  }
  async getGroupRequests(params = {}) {
    const [normal, doubtful] = await Promise.all([
      this.loadGroupRequests(false, params),
      this.loadGroupRequests(true, params),
    ]);
    const requests = [...normal, ...doubtful];
    return {
      invited_requests: requests.filter((item) => item.invitationExt).map((item) => this.groupRequestToOneBot(item)),
      join_requests: requests.filter((item) => !item.invitationExt).map((item) => this.groupRequestToOneBot(item)),
    };
  }
  async setGroupAddRequest(params) {
    const flag = String(params.flag || params.request_id || "");
    const [normal, doubtful] = await Promise.all([
      this.loadGroupRequests(false, { count: params.count }),
      this.loadGroupRequests(true, { count: params.count }),
    ]);
    const notify = [...normal, ...doubtful].find((item) => String(item.seq || item.flag) === flag);
    if (!notify) throw new OneBotActionError("群请求不存在或已过期", 1404, "set_group_add_request");
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "operateSysNotify", "set_group_add_request");
    await method(Boolean(notify._doubt), {
      operateType: this.asBoolean(params.approve, true) ? 1 : 2,
      targetMsg: {
        seq: flag,
        type: notify.type,
        groupCode: String(notify?.group?.groupCode || notify.groupCode || ""),
        postscript: String(params.reason || " ") || " ",
      },
    });
    return {};
  }
  async getGroupShutList(groupId) {
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "getGroupShutUpMemberList", "get_group_shut_list");
    const result = await method(groupId);
    checkNativeResult(result, "获取群禁言列表失败");
    const values = result?.members || result?.shutUpMembers || result?.result?.members || [];
    return Promise.all(Array.from(values instanceof Map ? values.values() : values || []).map(async (item) => {
      const uin = String(item.uin || await this.resolveUin(item.uid));
      return {
        user_id: Number(uin) || uin,
        nickname: String(item.nick || item.nickname || ""),
        shut_up_timestamp: Number(item.shutUpTime || item.shut_up_timestamp || 0),
      };
    }));
  }
  async setGroupKickMembers(params) {
    const groupId = String(params.group_id || "");
    const ids = params.user_ids || params.user_id || params.users || [];
    const userIds = Array.isArray(ids) ? ids : [ids];
    if (!userIds.length) throw new OneBotActionError("缺少要移除的群成员", 1400, "set_group_kick_members");
    const uids = await Promise.all(userIds.map((userId) => this.resolveUid(String(userId))));
    const service = this.session?.getGroupService?.();
    const method = requireNativeMethod(service, "kickMember", "set_group_kick_members");
    await method(groupId, uids, this.asBoolean(params.reject_add_request), String(params.reason || ""));
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
      checkNativeResult(await method(String(params.group_id), file.path), "设置群头像失败");
      return {};
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
        message_id: toOneBotMessageId(String(item.msgId || groupId + ":" + seq + ":" + random)),
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
    checkNativeResult(await method({ groupCode: groupId, msgRandom, msgSeq }), enable ? "设置精华消息失败" : "移除精华消息失败");
    return {};
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
    const cmd = String(params.cmd || "");
    const hex = String(params.data || "").replace(/\s+/g, "");
    if (!cmd || !/^(?:[0-9a-fA-F]{2})*$/.test(hex)) throw new OneBotActionError("发包参数 cmd/data 无效", 1400, "send_packet");
    const method = requireNativeMethod(this.getMsgService(), "sendSsoCmdReqByContend", "send_packet");
    const result = await method(cmd, Buffer.from(hex, "hex"));
    if (result === undefined || result === null) return undefined;
    if (Buffer.isBuffer(result) || result instanceof Uint8Array) return Buffer.from(result).toString("hex");
    const data = result.data ?? result.body ?? result.payload ?? result.buffer;
    if (Buffer.isBuffer(data) || data instanceof Uint8Array) return Buffer.from(data).toString("hex");
    return typeof result === "string" ? result : result;
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
        if (raw) latestMsg = this.toOneBotEvent(raw);
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
      const messageId = toOneBotMessageId(rawId);
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
      folder_name: String(folder.folderName || folder.name || ""),
      create_time: Number(folder.createTime || 0),
      creator: Number(folder.creatorUin || folder.creator || 0),
      creator_name: String(folder.creatorName || ""),
      total_file_count: Number(folder.totalFileCount || folder.fileCount || 0),
    };
  }
  async getGroupFiles(action, params) {
    const groupId = String(params.group_id || "");
    const service = this.session?.getRichMediaService?.();
    if (action === "get_group_file_system_info") {
      const countMethod = requireNativeMethod(service, "batchGetGroupFileCount", action);
      const listMethod = requireNativeMethod(service, "getGroupFileList", action);
      const [countResult, listResult] = await Promise.all([
        countMethod([groupId]),
        listMethod(groupId, { sortType: 1, fileCount: 1, startIndex: 0, sortOrder: 2, showOnlinedocFolder: 0 }),
      ]);
      checkNativeResult(countResult, "获取群文件数量失败");
      checkNativeResult(listResult, "获取群文件空间失败");
      const space = listResult?.groupSpaceResult || {};
      return {
        file_count: Number(countResult?.groupFileCounts?.[0] || 0),
        limit_count: 10000,
        used_space: Number(space.usedSpace || 0),
        total_space: Number(space.totalSpace || 0),
      };
    }
    const method = requireNativeMethod(service, "getGroupFileList", action);
    const result = await method(groupId, {
      sortType: 1,
      fileCount: Math.min(200, Math.max(1, Number(params.file_count || 50))),
      startIndex: Number(params.start_index || 0),
      sortOrder: 2,
      showOnlinedocFolder: 0,
      folderId: action === "get_group_files_by_folder" ? String(params.folder || params.folder_id || "") : "",
    });
    checkNativeResult(result, "获取群文件列表失败");
    const items = this.groupFileItems(result);
    return {
      files: items.filter((item) => item?.fileInfo || item?.file || item?.fileId || item?.fileUuid).map((item) => this.oneBotGroupFileItem(groupId, item)),
      folders: items.filter((item) => item?.folderInfo || item?.folder).map((item) => this.oneBotGroupFolderItem(groupId, item)),
    };
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
  bknFromSkey(skey) {
    let hash = 5381;
    for (const char of String(skey || "")) hash += (hash << 5) + char.charCodeAt(0);
    return hash & 2147483647;
  }
  async getOneBotCredentials(action, params) {
    const domain = String(params.domain || "qun.qq.com");
    const pskey = await this.getDomainPskey(domain);
    const skey = String(params.skey || "");
    const cookies = [skey ? "skey=" + skey : "", pskey ? "p_skey=" + pskey : ""].filter(Boolean).join("; ");
    if (action === "get_cookies") return { cookies };
    if (action === "get_csrf_token") return { token: this.bknFromSkey(skey || pskey) };
    return { cookies, csrf_token: this.bknFromSkey(skey || pskey) };
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
  async sendPoke(params) {
    const targetId = String(params.target_id || params.user_id || "");
    const peerId = String(params.group_id || params.user_id || "");
    if (!/^\d+$/.test(targetId) || !/^\d+$/.test(peerId)) {
      throw new OneBotActionError("戳一戳缺少有效的 user_id/group_id", 1400, "send_poke");
    }
    const isGroup = Boolean(params.group_id);
    const inner = Buffer.concat([
      encodeProtoVarintField(1, BigInt(targetId)),
      encodeProtoVarintField(isGroup ? 2 : 5, BigInt(peerId)),
      encodeProtoVarintField(6, 0),
    ]);
    const packet = Buffer.concat([
      encodeProtoVarintField(1, 0xED3),
      encodeProtoVarintField(2, 1),
      encodeProtoBytesField(4, inner),
      encodeProtoVarintField(12, 1),
    ]);
    const method = requireNativeMethod(this.getMsgService(), "sendSsoCmdReqByContend", "send_poke");
    await method("OidbSvcTrpcTcp.0xED3_1", packet);
    return null;
  }
  async setGroupSpecialTitle(_params) {
    throw new OneBotActionError("当前 QQ 原生会话未提供群头衔设置接口", 1405, "set_group_special_title");
  }
  redPacketBillNo(wallet) {
    let billNo = wallet?.billNo || wallet?.grabedMsg?.billNo || wallet?.redBag?.billNo || "";
    if (!billNo && typeof wallet?.receiver?.nativeAndroid === "string") {
      const match = wallet.receiver.nativeAndroid.match(/(?:^|[?&])id=(\d+)/);
      if (match) billNo = match[1];
    }
    return String(billNo || "");
  }
  rememberRedPacket(msg, wallet) {
    const billNo = this.redPacketBillNo(wallet);
    if (!billNo) return null;
    const existing = this.redPackets.get(billNo);
    if (existing) return null;
    const chatType = Number(msg?.chatType ?? 2);
    const peerUin = String(msg?.peerUin || "");
    const packet = {
      createdAt: Date.now(),
      billNo,
      wallet,
      peerUid: String(msg?.peerUid || ""),
      peerUin,
      groupId: chatType === 2 ? peerUin : "",
      groupName: String(msg?.peerName || ""),
      senderId: String(msg?.senderUin || ""),
      senderName: String(msg?.sendMemberName || msg?.sendNickName || ""),
      chatType,
      msgSeq: String(msg?.msgSeq || ""),
      redBagType: Number(wallet?.redBag?.redBagType ?? wallet?.redBagType ?? wallet?.grabedMsg?.redBagType ?? -1),
      senderRole: Number(msg?.roleType ?? 4),
      wishing: String(wallet?.receiver?.title || wallet?.receiver?.notice || ""),
      password: String(wallet?.redBag?.authKey || wallet?.receiver?.title || ""),
      redChannel: Number(wallet?.redChannel ?? 0),
      exclusiveUin: String(wallet?.redBag?.receiveUin || wallet?.redBag?.receiverUin || wallet?.receiver?.uin || wallet?.exclusiveUin || "")
    };
    this.redPackets.set(billNo, packet);
    const cutoff = Date.now() - 10 * 60 * 1e3;
    for (const [key, value] of this.redPackets) {
      if (value.createdAt < cutoff) this.redPackets.delete(key);
    }
    while (this.redPackets.size > 5e3) {
      this.redPackets.delete(this.redPackets.keys().next().value);
    }
    return packet;
  }
  redPacketPayload(packet) {
    return {
      bill_no: packet.billNo,
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
    try {
      const timeout = Symbol("red-packet-timeout");
      const nativeResult = await Promise.race([
        Promise.resolve(service.grabRedBag(request)),
        new Promise((resolve) => {
          timer = setTimeout(() => resolve(timeout), 1800);
        })
      ]);
      if (nativeResult === timeout) {
        return { ok: false, amount: 0, err_code: -1, err_msg: "领取超时" };
      }
      const response = nativeResult?.grabRedBagRsp || nativeResult || {};
      const amountFen = Number.parseInt(String(response?.recvdOrder?.amount || 0), 10) || 0;
      const errCode = Number(response?.retCode ?? response?.result ?? nativeResult?.result ?? 0);
      const errMsg = String(response?.retMsg || response?.errMsg || nativeResult?.errMsg || (errCode ? `错误码${errCode}` : ""));
      return { ok: errCode === 0, amount: amountFen / 100, err_code: errCode, err_msg: errMsg };
    } catch (error) {
      return { ok: false, amount: 0, err_code: -4, err_msg: String(error?.message || error) };
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
      const messageId = toOneBotMessageId(rawId);
      this.oneBotNativeMessageIds.set(String(messageId), rawId);
      const event = {
        time: Math.floor(Date.now() / 1000),
        self_id: Number(this.getSelfUin()) || this.getSelfUin(),
        post_type: "message",
        message_type: type,
        sub_type: "normal",
        message_id: messageId,
        real_id: String(result?.msgSeq || ""),
        real_seq: String(result?.msgSeq || ""),
        user_id: Number(this.getSelfUin()) || this.getSelfUin(),
        message: segments,
        raw_message: this.toOneBotRawMessage(segments),
        sender: {
          user_id: Number(this.getSelfUin()) || this.getSelfUin(),
          nickname: this.getSelfNick(),
          card: this.getSelfNick(),
        },
      };
      if (type === "group") event.group_id = Number(target) || target;
      this.rememberOneBotMessage(event, rawId, result?.msgId ? result : result?.msg || result?.message || null);
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
    if (Array.isArray(message)) return message.filter((item) => item && typeof item === "object");
    if (message && typeof message === "object") return [message];
    const text = String(message ?? "");
    if (autoEscape || !text.includes("[CQ:")) return [{ type: "text", data: { text } }];
    const result = [];
    const pattern = /\[CQ:([A-Za-z0-9_]+)((?:,[^\]]*)?)\]/g;
    let offset = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > offset) {
        result.push({ type: "text", data: { text: this.decodeCq(text.slice(offset, match.index)) } });
      }
      const data = {};
      for (const part of String(match[2] || "").replace(/^,/, "").split(",")) {
        if (!part) continue;
        const separator = part.indexOf("=");
        const key = separator < 0 ? part : part.slice(0, separator);
        const value = separator < 0 ? "" : part.slice(separator + 1);
        data[key] = this.decodeCq(value);
      }
      result.push({ type: match[1], data });
      offset = pattern.lastIndex;
    }
    if (offset < text.length) result.push({ type: "text", data: { text: this.decodeCq(text.slice(offset)) } });
    return result.length ? result : [{ type: "text", data: { text } }];
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
    if (!this.session) throw new Error("QQ Session 尚未初始化");
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
    for (const raw of Array.from(messages || [])) {
      for (const pending of Array.from(this.pendingSentMessages)) {
        let matched = false;
        try {
          matched = pending.match(raw);
        } catch (error) {
          pending.reject(error);
          continue;
        }
        if (matched) pending.resolve(raw);
      }
    }
  }
  async sendNativeElementsToPeer(peer, elements, logType = "private") {
    if (!this.session) throw new Error("QQ Session 尚未初始化");
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
      const status = Number(raw?.sendStatus);
      return !Number.isFinite(status) || status === 2 || status === 3;
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
  async queryGroupList() {
    const service = this.session?.getGroupService();
    if (!service?.getGroupList) return [];
    const result = await service.getGroupList(false);
    checkNativeResult(result, "获取群列表失败");
    const rawGroups = result?.groupList || result?.groups || result?.data?.groupList
      || result?.data || result?.result?.groupList || result?.result || [];
    const groups = rawGroups instanceof Map
      ? Array.from(rawGroups.values())
      : Array.isArray(rawGroups)
        ? rawGroups
        : Object.values(rawGroups || {});
    return groups.filter((group) => group && typeof group === "object").map((group) => ({
      group_id: Number(group.groupCode || group.group_id || group.groupId) || group.groupCode || group.group_id,
      group_name: group.groupName || group.group_name || group.remarkName || "",
      member_count: Number(group.memberNum || group.member_count || 0),
      max_member_count: Number(group.maxMemberNum || group.max_member_count || 0)
    })).filter((group) => group.group_id);
  }
  async queryGroupInfo(groupId) {
    const service = this.session?.getGroupService();
    if (!service?.getGroupDetailInfo) return null;
    const result = await service.getGroupDetailInfo(groupId, 0);
    const data = result?.data || result?.groupInfo || result?.result || result || {};
    return {
      group_id: Number(data.groupCode || groupId) || groupId,
      group_name: data.groupName || data.group_name || "",
      member_count: Number(data.memberNum || data.member_count || 0),
      max_member_count: Number(data.maxMemberNum || data.max_member_count || 0)
    };
  }
  async queryGroupMemberList(groupId) {
    const service = this.session?.getGroupService();
    if (!service?.getAllMemberList) return [];
    const result = await service.getAllMemberList(groupId, false);
    const infos = result?.result?.infos || result?.infos || [];
    const values = infos instanceof Map ? Array.from(infos.values()) : Array.from(infos);
    return values.map((member) => ({
      group_id: Number(groupId) || groupId,
      user_id: Number(member.uin || member.user_id) || member.uin || member.user_id,
      nickname: member.nick || member.nickname || "",
      card: member.cardName || member.card || "",
      role: member.role === 4 ? "owner" : member.role === 3 ? "admin" : "member",
      title: member.memberSpecialTitle || "",
      join_time: Number(member.joinTime || 0),
      last_sent_time: Number(member.lastSpeakTime || 0),
      shut_up_timestamp: Number(member.shutUpTime || 0)
    }));
  }
  async queryGroupMemberInfo(groupId, userId) {
    const members = await this.queryGroupMemberList(groupId);
    const member = members.find((item) => String(item.user_id) === userId);
    if (!member) throw new Error(`群 ${groupId} 中不存在成员 ${userId}`);
    return member;
  }
  async queryFriendList() {
    const service = this.session?.getBuddyService();
    if (!service?.getBuddyListV2) return [];
    const result = await service.getBuddyListV2("0", true, 0);
    checkNativeResult(result, "获取好友列表失败");
    const ids = [...new Set((result?.data || []).flatMap((item) => item.buddyUids || []))];
    const friends = await Promise.all(ids.map(async (uid) => {
      const uin = await this.resolveUin(uid);
      return {
        user_id: Number(uin) || uin,
        nickname: this.displayText(service.getBuddyNick?.(uid)),
        remark: this.displayText(service.getBuddyRemark?.(uid)),
      };
    }));
    return friends.filter((friend) => /^\d+$/.test(String(friend.user_id)));
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
    checkNativeResult(await method(peer, [nativeId]), "撤回消息失败");
    return {};
  }
  async handleQuickOperation(params) {
    const context = params?.context;
    const operation = params?.operation;
    if (!context || typeof context !== "object" || !operation || typeof operation !== "object") {
      throw new OneBotActionError("快速操作缺少事件上下文或操作参数", 1400, ".handle_quick_operation");
    }
    if (context.post_type === "message") {
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
    if (value === void 0 || value === null) return fallback;
    if (typeof value === "string") return value.toLowerCase() === "true";
    return Boolean(value);
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
    await this.session?.getGroupService?.().kickMember(groupId, [uid], rejectAdd, "");
    return {};
  }
  async setGroupBan(groupId, userId, duration) {
    const uid = await this.resolveUid(userId);
    const result = await this.session?.getGroupService?.().setMemberShutUp(groupId, [{ uid, timeStamp: duration }]);
    if (result?.result && result.result !== 0) throw new Error(result.errMsg || "群禁言失败");
    return {};
  }
  async setGroupWholeBan(groupId, enable) {
    const result = await this.session?.getGroupService?.().setGroupShutUp(groupId, enable);
    if (result?.result && result.result !== 0) throw new Error(result.errMsg || "全员禁言失败");
    return {};
  }
  async setGroupAdmin(groupId, userId, enable) {
    const uid = await this.resolveUid(userId);
    await this.session?.getGroupService?.().modifyMemberRole(groupId, uid, enable ? 3 : 2);
    return {};
  }
  async setGroupCard(groupId, userId, card) {
    const uid = await this.resolveUid(userId);
    await this.session?.getGroupService?.().modifyMemberCardName(groupId, uid, card);
    return {};
  }
  async setGroupName(groupId, groupName) {
    const result = await this.session?.getGroupService?.().modifyGroupName(groupId, groupName, false);
    if (result?.result && result.result !== 0) throw new Error(result.errMsg || "修改群名称失败");
    return {};
  }
  async setGroupLeave(groupId) {
    await this.session?.getGroupService?.().quitGroup(groupId);
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
    log(id, "[SESSION] guid:", guid);
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
        log(id, "[SESSION] onSessionInitComplete:", safeJson(args, 300));
      };
      sessionListener.onOpentelemetryInit = (info) => {
        log(id, "[SESSION] onOpentelemetryInit:", safeJson(info, 500));
        if (info?.is_init) finish();
        else finish(new Error("session opentelemetry init failed"));
      };
      log(id, "[SESSION] session.init...");
      try {
        this.session.init(
          sessionConfig,
          this.sessionDependsAdapter,
          this.sessionDispatcherAdapter,
          sessionListener
        );
        log(id, "[SESSION] session.startNT()");
        if (this.startupSession && typeof this.startupSession.start === "function") {
          log(id, "[SESSION] startupSession.start()");
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
      log(id, "[MSG] session 为空，跳过");
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
        const isGroup = Number(chatType) === 2;
        const matches = [];
        for (const event of self.oneBotMessages.values()) {
          if (String(event.message_seq || event.real_seq || event.real_id || "") !== String(msgSeq || "")) continue;
          matches.push(event);
        }
        const recalled = matches.find((event) => !isGroup || String(event.group_id || "") === String(uid || "")) || matches[0] || null;
        const privateUid = String(uid || recalled?.user_id || "");
        const resolvedPrivateUin = isGroup ? "" : await self.resolveUin(privateUid);
        const userId = isGroup
          ? Number(recalled?.user_id || 0) || recalled?.user_id || 0
          : Number(resolvedPrivateUin) || resolvedPrivateUin;
        const event = {
          time: Math.floor(Date.now() / 1e3),
          self_id: Number(self.getSelfUin()) || self.getSelfUin(),
          post_type: "notice",
          notice_type: isGroup ? "group_recall" : "friend_recall",
          user_id: userId,
          message_id: recalled?.message_id || String(msgSeq || ""),
        };
        if (isGroup) {
          const groupId = recalled?.group_id || uid;
          event.group_id = Number(groupId) || groupId;
          event.operator_id = userId;
        }
        self.oneBotEventCallback?.(event);
      } catch (error) {
        logErr(id, "[EVENT] 撤回事件转换失败:", error?.message || error);
      }
    };
    listenerImpl.onMsgInfoListUpdate = (messages) => {
      self.handleSentMessageUpdates(messages);
    };
    listenerImpl.onAddSendMsg = (message) => {
      self.handleSentMessageUpdates([message]);
    };
    listenerImpl.onRecvMsg = (msgs) => {
      const gate = self.incomingMessageGate;
      if (!gate) return;
      const ignored = { history: 0, invalid_time: 0, duplicate: 0 };
      for (const msg of msgs) {
        const decision = gate.inspect(msg);
        if (!decision.accept) {
          ignored[decision.reason] += 1;
          continue;
        }
        self.handleMessage(msg);
      }
      const ignoredCount = ignored.history + ignored.invalid_time + ignored.duplicate;
      if (ignoredCount) {
        log(
          id,
          `[MSG] 已忽略 ${ignoredCount} 条非实时消息` +
          ` (登录前=${ignored.history}, 时间无效=${ignored.invalid_time}, 重复=${ignored.duplicate})`
        );
      }
    };
    this.msgListener = proxied(listenerImpl);
    try {
      this.session.getMsgService().addKernelMsgListener(this.msgListener);
      log(id, `[MSG] 消息监听注册成功，仅接收 ${this.incomingMessageGate.startedAt} 之后的实时消息`);
    } catch (e) {
      logErr(id, "[MSG] 注册消息监听失败:", e.message);
    }
  }
  registerEventListeners() {
    const id = this.botConfig.id;
    const emit = (event) => this.oneBotEventCallback?.({
      time: Math.floor(Date.now() / 1e3),
      self_id: Number(this.getSelfUin()) || this.getSelfUin(),
      ...event,
    });

    try {
      const buddy = new BuddyListener();
      buddy.onBuddyReqChange = async (payload) => {
        for (const request of Array.from(payload?.buddyReqs || []).slice(0, Number(payload?.unreadNums || 0))) {
          if (request?.isInitiator || request?.isDecide || !request?.isUnread) continue;
          const userId = await this.resolveUin(String(request.friendUid || ""));
          emit({
            post_type: "request",
            request_type: "friend",
            user_id: Number(userId) || userId,
            comment: String(request.extWords || ""),
            flag: String(request.reqTime || request.flag || ""),
          });
        }
      };
      this.buddyListener = proxied(buddy);
      this.buddyListenerHandle = this.session?.getBuddyService?.().addKernelBuddyListener?.(this.buddyListener);
    } catch (error) {
      logErr(id, "[EVENT] 好友事件监听注册失败:", error?.message || error);
    }

    try {
      const group = new GroupListener();
      group.onGroupNotifiesUpdated = async (_doubt, notifies) => {
        for (const notify of Array.from(notifies || [])) {
          const groupId = String(notify?.group?.groupCode || notify?.groupCode || "");
          const affectedUid = String(notify?.user1?.uid || notify?.actionUser?.uid || "");
          const affectedUin = affectedUid ? await this.resolveUin(affectedUid) : "";
          const flag = String(notify?.seq || notify?.flag || "");
          const type = Number(notify?.type || 0);
          const status = Number(notify?.status || 0);
          if (status === 1 && [1, 5, 7].includes(type)) {
            emit({
              post_type: "request",
              request_type: "group",
              sub_type: type === 1 ? "invite" : "add",
              group_id: Number(groupId) || groupId,
              user_id: Number(affectedUin) || affectedUin || 0,
              comment: String(notify?.postscript || ""),
              flag,
            });
          } else if ([4, 6].includes(type)) {
            emit({
              post_type: "notice", notice_type: "group_increase", sub_type: "approve",
              group_id: Number(groupId) || groupId, user_id: Number(affectedUin) || affectedUin || 0, operator_id: 0,
            });
          } else if ([9, 10, 11].includes(type)) {
            emit({
              post_type: "notice", notice_type: "group_decrease", sub_type: type === 11 ? "leave" : "kick",
              group_id: Number(groupId) || groupId, user_id: Number(affectedUin) || affectedUin || 0, operator_id: 0,
            });
          } else if ([8, 12, 13].includes(type)) {
            emit({
              post_type: "notice", notice_type: "group_admin", sub_type: type === 8 ? "set" : "unset",
              group_id: Number(groupId) || groupId, user_id: Number(affectedUin) || affectedUin || 0,
            });
          }
        }
      };
      this.groupListener = proxied(group);
      this.groupListenerHandle = this.session?.getGroupService?.().addKernelGroupListener?.(this.groupListener);
    } catch (error) {
      logErr(id, "[EVENT] 群事件监听注册失败:", error?.message || error);
    }
  }
  handleMessage(msg) {
    const elements = msg.elements || [];
    if (!elements.length) return;
    const event = this.toOneBotEvent(msg);
    this.rememberOneBotMessage(event, nativeMessageKey(msg), msg);
    const forwardIds = [];
    for (const element of elements) {
      const ark = this.forwardArkData(element?.arkElement?.bytesData);
      if (ark?.meta?.detail?.resid) forwardIds.push(ark.meta.detail.resid);
      if (element?.multiForwardMsgElement?.resId) forwardIds.push(element.multiForwardMsgElement.resId);
    }
    if (forwardIds.length) this.rememberForwardReference(msg, forwardIds);
    this.rememberReplyTargets(msg);
    this.oneBotEventCallback?.(event);
    for (const element of elements) {
      if (!element?.walletElement) continue;
      const packet = this.rememberRedPacket(msg, element.walletElement);
      if (packet) this.redPacketCallback?.(this.redPacketPayload(packet));
    }
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
  rememberReplyTargets(msg) {
    for (const element of msg.elements || []) {
      const reference = resolveReplyReference(element, msg);
      if (!reference) continue;
      if (reference.record) {
        const event = this.toOneBotEvent(reference.record);
        this.rememberOneBotMessage(event, reference.nativeId || nativeMessageKey(reference.record), reference.record);
        continue;
      }
      const isGroup = Number(msg.chatType) === 2;
      const target = {
        time: 0,
        self_id: this.getSelfUin(),
        post_type: "message",
        message_type: isGroup ? "group" : "private",
        sub_type: "normal",
        message_id: reference.messageId,
        real_id: reference.sequence,
        real_seq: reference.sequence,
        user_id: Number(reference.senderUin) || reference.senderUin || 0,
        message: [],
        raw_message: "",
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
  oneBotTextSegment(textElement) {
    const content = String(textElement?.content || "");
    const atType = Number(textElement?.atType || 0);
    if (atType === 1) return { type: "at", data: { qq: "all", name: content.replace(/^@/, "") } };
    if (atType !== 0) {
      const qq = String(textElement?.atUid || textElement?.atNtUid || textElement?.atTinyId || "");
      return { type: "at", data: { qq, name: content.replace(/^@/, "") } };
    }
    return content ? { type: "text", data: { text: content } } : null;
  }
  oneBotElement(element, msg) {
    const reference = resolveReplyReference(element, msg);
    if (reference) return { type: "reply", data: { id: String(reference.messageId) } };
    if (element?.textElement) return this.oneBotTextSegment(element.textElement);
    if (element?.picElement) {
      const pic = element.picElement;
      const file = String(pic.sourcePath || pic.filePath || pic.fileName || pic.fileUuid || "");
      const data = {
        file,
        file_id: String(pic.fileUuid || element.elementId || file),
        url: String(pic.originImageUrl || pic.url || ""),
        file_size: String(pic.fileSize || ""),
        summary: String(pic.summary || ""),
        sub_type: Number(pic.picSubType || 0),
      };
      this.rememberOneBotFile(pic, data);
      return { type: "image", data };
    }
    if (element?.fileElement) {
      const file = element.fileElement;
      const data = {
        file: String(file.fileName || file.filePath || file.fileUuid || ""),
        file_id: String(file.fileUuid || element.elementId || file.fileName || ""),
        name: String(file.fileName || ""),
        path: String(file.filePath || ""),
        file_size: String(file.fileSize || ""),
        element_id: String(element.elementId || ""),
      };
      this.rememberOneBotFile(file, data);
      if (Number(element.elementType) === 23 || Number(element.elementType) === 30) {
        const isDir = Number(element.elementType) === 30;
        return {
          type: "onlinefile",
          data: {
            ...data,
            msg_id: String(msg.msgId || ""),
            element_id: String(element.elementId || ""),
            is_dir: isDir,
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
      const data = {
        file: String(ptt.fileName || ptt.fileUuid || ptt.filePath || ""),
        file_id: String(ptt.fileUuid || element.elementId || ptt.fileName || ""),
        path: String(ptt.filePath || ""),
        url: String(ptt.url || ""),
        file_size: String(ptt.fileSize || ""),
        duration: Number(ptt.duration || 0),
      };
      this.rememberOneBotFile(ptt, data);
      return { type: "record", data };
    }
    if (element?.videoElement) {
      const video = element.videoElement;
      const data = {
        file: String(video.fileName || video.fileUuid || video.filePath || ""),
        file_id: String(video.fileUuid || element.elementId || video.fileName || ""),
        path: String(video.filePath || ""),
        url: String(video.url || ""),
        file_size: String(video.fileSize || ""),
        duration: Number(video.fileTime || 0),
      };
      this.rememberOneBotFile(video, data);
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
          resultId: face.resultId === undefined ? undefined : String(face.resultId),
          chainCount: face.chainCount === undefined ? undefined : Number(face.chainCount),
        },
      };
    }
    if (element?.marketFaceElement) {
      const face = element.marketFaceElement;
      return {
        type: "mface",
        data: {
          emoji_package_id: Number(face.emojiPackageId || 0),
          emoji_id: String(face.emojiId || ""),
          key: String(face.key || ""),
          summary: String(face.faceName || "[商城表情]"),
        },
      };
    }
    if (element?.arkElement) {
      const content = String(element.arkElement.bytesData || "");
      const forward = this.forwardArkData(content);
      if (forward) {
        return {
          type: "forward",
          data: {
            id: String(toOneBotMessageId(nativeMessageKey(msg))),
            res_id: String(forward.meta.detail.resid),
          },
        };
      }
      return { type: "json", data: { data: content } };
    }
    if (element?.structLongMsgElement) {
      return {
        type: "xml",
        data: {
          data: String(element.structLongMsgElement.xmlContent || ""),
          resid: String(element.structLongMsgElement.resId || ""),
        },
      };
    }
    if (element?.markdownElement) {
      const markdown = element.markdownElement;
      const fileSetId = String(markdown?.mdExtInfo?.flashTransferInfo?.filesetId || "");
      if (fileSetId) return { type: "flashtransfer", data: { fileset_id: fileSetId, fileSetId } };
      return { type: "markdown", data: { content: String(markdown.content || "") } };
    }
    if (element?.multiForwardMsgElement) {
      const forward = element.multiForwardMsgElement;
      return {
        type: "forward",
        data: {
          id: String(toOneBotMessageId(nativeMessageKey(msg))),
          res_id: String(forward.resId || ""),
        },
      };
    }
    if (element?.shareLocationElement) {
      const location = element.shareLocationElement;
      let ext = {};
      try {
        ext = JSON.parse(String(location.ext || "{}"));
      } catch {
      }
      return {
        type: "location",
        data: {
          lat: Number(ext.lat || ext.latitude || 0),
          lon: Number(ext.lon || ext.lng || ext.longitude || 0),
          title: String(ext.title || location.text || ""),
          content: String(ext.content || ext.address || ""),
        },
      };
    }
    if (element?.walletElement) {
      const title = String(element.walletElement?.receiver?.title || element.walletElement?.receiver?.notice || "").trim();
      return { type: "text", data: { text: title ? "[QQ红包] " + title : "[QQ红包]" } };
    }
    return null;
  }
  encodeCq(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/\[/g, "&#91;").replace(/\]/g, "&#93;").replace(/,/g, "&#44;");
  }
  toOneBotRawMessage(message) {
    return Array.from(message || []).map((segment) => {
      if (segment?.type === "text") return String(segment?.data?.text || "");
      const data = Object.entries(segment?.data || {}).filter(([, value]) => value !== undefined).map(([key, value]) => {
        const rendered = typeof value === "object" ? JSON.stringify(value) : String(value);
        return key + "=" + this.encodeCq(rendered);
      });
      return "[CQ:" + String(segment?.type || "unknown") + (data.length ? "," + data.join(",") : "") + "]";
    }).join("");
  }
  toOneBotEvent(msg) {
    const message = [];
    const inlineKeyboard = [];
    for (const element of msg.elements || []) {
      const segment = this.oneBotElement(element, msg);
      if (segment) message.push(segment);
      const keyboard = element?.inlineKeyboardElement;
      if (keyboard) {
        for (const row of keyboard.rows || []) {
          for (const button of row?.buttons || []) {
            const findCallbackData = (value) => {
              if (!value || typeof value !== "object") return "";
              for (const child of Object.values(value)) {
                if (typeof child === "string" && child.startsWith("BOT1.0_")) return child;
              }
              for (const child of Object.values(value)) {
                const found = findCallbackData(child);
                if (found) return found;
              }
              return "";
            };
            const callbackData = String(
              findCallbackData(button) || button?.callback_data ||
              button?.action?.callback_data || button?.action?.data || button?.data || ""
            );
            if (!callbackData) continue;
            inlineKeyboard.push({
              bot_appid: String(keyboard.botAppid || keyboard.bot_appid || ""),
              button_id: String(button?.id || button?.button_id || button?.action?.button_id || "1"),
              callback_data: callbackData
            });
          }
        }
      }
    }
    const messageId = toOneBotMessageId(nativeMessageKey(msg));
    const isGroup = Number(msg.chatType) === 2;
    const rawTime = Number(msg.msgTime || 0);
    const event = {
      time: rawTime > 1e10 ? Math.floor(rawTime / 1e3) : rawTime || Math.floor(Date.now() / 1e3),
      self_id: this.getSelfUin(),
      post_type: "message",
      message_type: isGroup ? "group" : "private",
      sub_type: "normal",
      message_id: messageId,
      real_id: String(msg.msgSeq || ""),
      real_seq: String(msg.msgSeq || ""),
      message_seq: Number(msg.msgSeq || 0),
      user_id: Number(msg.senderUin) || msg.senderUin || 0,
      message,
      raw_message: this.toOneBotRawMessage(message),
      font: 0,
      sender: {
        user_id: Number(msg.senderUin) || msg.senderUin || 0,
        nickname: this.displayText(msg.sendNickName) || this.displayText(msg.sendMemberName),
        card: this.displayText(msg.sendMemberName),
        sex: String(msg.sex || "unknown"),
        age: Number(msg.age || 0),
        role: Number(msg.roleType) === 4 ? "owner" : Number(msg.roleType) === 3 ? "admin" : "member",
        title: String(msg.memberSpecialTitle || ""),
      },
      _peer_uid: String(msg.peerUid || ""),
      _chat_type: Number(msg.chatType || 0),
    };
    if (isGroup) {
      event.group_id = Number(msg.peerUin) || msg.peerUin;
      event.group_name = this.displayText(msg.peerName) || this.displayText(msg.groupName);
    }
    if (inlineKeyboard.length) event._elaina_inline_keyboard = inlineKeyboard;
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
let controlLoopRunning = true;
function embeddedBotConfig() {
  return {
    id: BOT_ID,
    uin: process.env["ELAINAQQ_BOT_UIN"] || "",
    nickname: "",
    enabled: true
  };
}
async function main() {
  console.log(`[Worker] 启动 botId=${BOT_ID}，使用账号独立桥接通道`);
  console.log(`[Worker] 桥接地址: ${MANAGER_URL}`);
  if (!EMBEDDED) {
    throw new Error("内置 QQ bridge 只能由框架启动");
  }
  if (!BOT_ID) {
    console.error("[Worker] 缺少 ELAINAQQ_BOT_ID 环境变量");
    process.exit(1);
  }
  const botConfig = embeddedBotConfig();
  const qqPath = findQQPath();
  const qqInfo = getQQInfo(qqPath);
  const wrapper = loadWrapper(qqPath, qqInfo.version);
  console.log(`[Worker] wrapper 加载成功, QQ ${qqInfo.version}`);
  instance = new QQInstance(botConfig, qqInfo, wrapper, "");
  instance.setStatusCallback((runtime) => {
    reportStatus(runtime);
  });
  instance.setOneBotEventCallback((event) => {
    reportEmbeddedEvent(event);
  });
  instance.setRedPacketCallback((packet) => {
    reportRedPacket(packet);
  });
  void startControlLoop();
  try {
    await instance.start();
    process.exitCode = 0;
  } catch (e) {
    console.error("[Worker] QQ 启动失败:", e.message);
    try {
      await instance?.stop();
    } catch (stopError) {
      console.error("[Worker] QQ 失败清理异常:", stopError?.message || stopError);
    }
    keepAliveAgent.destroy();
    setTimeout(() => process.exit(1), 500);
  }
}
const keepAliveAgent = new http.Agent({
  keepAlive: true,
  keepAliveMsecs: 3e4,
  maxSockets: 4,
  maxFreeSockets: 2
});
let managerReportTail = Promise.resolve();
function queueManagerReport(path, body, label) {
  managerReportTail = managerReportTail
    .catch(() => {})
    .then(() => managerRequest("POST", path, body, 5e3))
    .catch((error) => {
      logErr(BOT_ID, label, error?.message || error);
    });
}
function reportStatus(runtime) {
  queueManagerReport("/api/embedded/events", { bot_id: BOT_ID, self_id: runtime.loginUin || BOT_ID, runtime }, "[BRIDGE] 状态上报失败:");
}
function reportEmbeddedEvent(event) {
  queueManagerReport("/api/embedded/events", { bot_id: BOT_ID, self_id: event.self_id || BOT_ID, event }, "[BRIDGE] 事件上报失败:");
}
function reportRedPacket(packet) {
  queueManagerReport("/api/embedded/red-packets", {
    bot_id: BOT_ID,
    self_id: instance?.getSelfUin() || BOT_ID,
    red_packet: packet
  }, "[BRIDGE] 红包上报失败:");
}
function managerRequest(method, apiPath, body = null, timeout = 3e4) {
  return new Promise((resolve, reject) => {
    try {
      const url = new URL(apiPath, MANAGER_URL);
      const payload = body === null ? "" : stringifyJson(body);
      const headers = body === null ? {} : {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(payload)
      };
      const req = http.request({
        agent: keepAliveAgent,
        hostname: url.hostname,
        port: url.port,
        path: `${url.pathname}${url.search}`,
        method,
        headers,
        timeout
      }, (res) => {
        if (res.statusCode === 204) {
          res.resume();
          res.on("end", () => resolve(null));
          return;
        }
        let responseBody = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          responseBody += chunk;
          if (responseBody.length > 8 * 1024 * 1024) req.destroy(new Error("控制响应过大"));
        });
        res.on("end", () => {
          let data = {};
          try {
            data = responseBody ? JSON.parse(responseBody) : {};
          } catch {
            reject(new Error("控制响应格式错误"));
            return;
          }
          if ((res.statusCode || 500) >= 400) {
            reject(new Error(data.error || data.message || `HTTP ${res.statusCode}`));
          } else {
            resolve(data);
          }
        });
      });
      req.on("error", reject);
      req.on("timeout", () => req.destroy(new Error("控制请求超时")));
      if (payload) req.write(payload);
      req.end();
    } catch (error) {
      reject(error);
    }
  });
}
async function executeControlCommand(command) {
  const requestId = String(command?.request_id || "");
  if (!requestId) return;
  let result;
  try {
    if (!instance) throw new Error("QQ 实例未运行");
    if (command.type === "action") {
      const data = await instance.callOneBotAction(String(command.action || ""), command.params || {});
      result = { status: "ok", retcode: 0, data, message: "", wording: "" };
    } else if (command.type === "grab_red_packet") {
      const data = await instance.grabRedPacket({ bill_no: command.bill_no });
      result = { status: "ok", retcode: 0, data, message: "", wording: "" };
    } else if (command.type === "refresh_qr") {
      result = { success: true, data: instance.refreshQrCode() };
    } else {
      throw new Error("不支持的控制命令");
    }
  } catch (error) {
    const message = error?.message || String(error);
    const retcode = Number(error?.retcode || 1400);
    result = {
      status: "failed",
      retcode: Number.isFinite(retcode) ? retcode : 1400,
      data: null,
      message,
      wording: message,
    };
  }
  await managerRequest("POST", "/api/embedded/control/result", {
    bot_id: BOT_ID,
    request_id: requestId,
    result
  }, 5e3);
}
async function startControlLoop() {
  while (controlLoopRunning) {
    try {
      const command = await managerRequest(
        "GET",
        `/api/embedded/control/poll?bot_id=${encodeURIComponent(BOT_ID)}`,
        null,
        3e4
      );
      if (command) await executeControlCommand(command);
    } catch (error) {
      if (controlLoopRunning) await new Promise((resolve) => setTimeout(resolve, 1e3));
    }
  }
}
process.on("SIGTERM", async () => {
  shuttingDown = true;
  console.log("[Worker] 收到 SIGTERM");
  controlLoopRunning = false;
  clearInterval(lifecycleKeepAlive);
  if (instance) await instance.stop();
  keepAliveAgent.destroy();
  process.exit(0);
});
process.on("SIGINT", async () => {
  shuttingDown = true;
  controlLoopRunning = false;
  clearInterval(lifecycleKeepAlive);
  if (instance) await instance.stop();
  keepAliveAgent.destroy();
  process.exit(0);
});
process.on("uncaughtException", (error) => {
  console.error("[Worker] 未捕获异常:", error?.stack || error);
});
process.on("unhandledRejection", (reason) => {
  console.error("[Worker] 未处理 Promise 异常:", reason?.stack || reason);
});
process.on("beforeExit", (code) => {
  if (!shuttingDown && process.env["ELAINAQQ_WORKER_TEST"] !== "1") {
    console.error("[Worker] 事件循环意外结束，退出码: " + code);
  }
});
if (process.env["ELAINAQQ_WORKER_TEST"] !== "1") {
  main().catch((e) => {
    console.error("[Worker] 启动失败:", e);
    clearInterval(lifecycleKeepAlive);
    process.exit(1);
  });
}

export { QQInstance };
