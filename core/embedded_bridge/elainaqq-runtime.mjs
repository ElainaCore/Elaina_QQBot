import http from 'http';
import fs from 'fs';
import path from 'path';
import os from 'os';
import {
  GlobalAdapter,
  LoginListener,
  MessageListener,
  O3MiscListener,
  SessionDependsAdapter,
  SessionDispatcherAdapter,
  SessionListener
} from './session_adapters.mjs';

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
  statusCallback = null;
  oneBotEventCallback = null;
  oneBotMessages = /* @__PURE__ */ new Map();
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
      if (this.session && this.msgListener) {
        try {
          this.session.getMsgService().removeKernelMsgListener(this.msgListener);
        } catch {
        }
      }
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
    switch (action) {
      case "elaina_grab_red_packet":
        return this.grabRedPacket(params);
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
        return { app_name: "ElainaQQ Embedded QQ", app_version: this.qqInfo.version, protocol_version: "v11" };
      case "can_send_image":
        return { yes: true };
      case "can_send_record":
        return { yes: false };
      case "get_msg":
        return this.oneBotMessages.get(String(params.message_id)) || null;
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
        return { user_id: Number(params.user_id) || params.user_id, nickname: String(params.user_id) };
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
        this.redPackets.clear();
        return {};
      case "bot_exit":
        await this.stop();
        return {};
      default:
        throw new Error("内置 QQ 暂未实现 OneBot action: " + action);
    }
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
  redPacketNotice(packet) {
    const notice = {
      time: Math.floor(Date.now() / 1e3),
      self_id: Number(this.getSelfUin()) || this.getSelfUin(),
      post_type: "notice",
      notice_type: "elaina_red_packet",
      sub_type: packet.redChannel === 32 ? "password" : packet.redBagType === 3 ? "exclusive" : "normal",
      user_id: Number(packet.senderId) || packet.senderId || 0,
      red_packet: {
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
      }
    };
    if (packet.groupId) notice.group_id = Number(packet.groupId) || packet.groupId;
    return notice;
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
  async sendOneBotMessage(type, target, message, autoEscape = false) {
    if (!target || target === "undefined") throw new Error("缺少消息目标");
    const segments = this.normalizeOneBotMessage(message, autoEscape);
    const elements = [];
    const temporaryFiles = [];
    try {
      for (const segment of segments) {
        const segmentType = String(segment.type || "").toLowerCase();
        const data = segment.data || {};
        if (segmentType === "text") {
          if (data.text !== void 0 && String(data.text)) elements.push(this.textElement(String(data.text)));
        } else if (segmentType === "at") {
          if (type !== "group") continue;
          elements.push(await this.atElement(target, String(data.qq || data.user_id || "")));
        } else if (segmentType === "face") {
          const faceIndex = Number(data.id);
          if (!Number.isInteger(faceIndex) || faceIndex < 0) throw new Error(`无效的表情 ID: ${data.id}`);
          elements.push({
            elementType: 6,
            elementId: "",
            faceElement: { faceIndex, faceType: faceIndex >= 222 ? 2 : 1, sourceType: 1 }
          });
        } else if (segmentType === "image") {
          const file = String(data.file || data.url || "");
          if (!file) throw new Error("图片消息缺少 file/url");
          const prepared = await this.imageElement(file, String(data.summary || ""));
          elements.push(prepared.element);
          if (prepared.temporary) temporaryFiles.push(prepared.path);
        } else if (segmentType === "json") {
          const content = typeof data.data === "string" ? data.data : JSON.stringify(data.data ?? data);
          elements.push({
            elementType: 10,
            elementId: "",
            arkElement: { bytesData: content, linkInfo: null, subElementType: null }
          });
        } else {
          throw new Error(`内置 QQ 暂不支持消息段: ${segmentType || "unknown"}`);
        }
      }
      if (!elements.length) throw new Error("消息内容为空");
      const result = await this.sendNativeElements(type, target, elements);
      const rawId = String(result?.msgId || result?.messageId || result?.msg_id || Date.now());
      const numericId = Number(rawId);
      return { message_id: Number.isSafeInteger(numericId) ? numericId : Date.now() };
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
    try {
      const result = await this.session.getMsgService().sendMsg(
        "0",
        { chatType: type === "group" ? 2 : 1, peerUid, guildId: "" },
        elements,
        /* @__PURE__ */ new Map()
      );
      const resultCode = Number(result?.result ?? result?.retcode ?? 0);
      if (Number.isFinite(resultCode) && resultCode !== 0) {
        throw new Error(result?.errMsg || result?.message || `发送失败 (${resultCode})`);
      }
      return result || {};
    } catch (error) {
      logErr(this.botConfig.id, `${type === "group" ? "群" : "私聊"}消息发送失败:`, error);
      throw error;
    }
  }
  async imageElement(input, summary = "") {
    const materialized = await this.materializeFile(input);
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
          picSubType: 0,
          fileUuid: "",
          fileSubId: "",
          thumbFileSize: 0,
          summary,
          thumbPath: /* @__PURE__ */ new Map()
        }
      }
    };
  }
  async materializeFile(input) {
    const value = input.trim();
    if (!value) throw new Error("文件地址为空");
    const tempPath = path.join(os.tmpdir(), `elaina_${process.pid}_${Date.now()}_${Math.random().toString(16).slice(2)}.png`);
    if (value.startsWith("base64://") || value.startsWith("data:")) {
      const encoded = value.startsWith("base64://") ? value.slice(9) : value.slice(value.indexOf(",") + 1);
      const data = Buffer.from(encoded, "base64");
      if (!data.length) throw new Error("base64 文件内容为空");
      fs.writeFileSync(tempPath, data);
      return { path: tempPath, temporary: true };
    }
    if (/^https?:\/\//i.test(value)) {
      await this.downloadFile(value, tempPath);
      return { path: tempPath, temporary: true };
    }
    let localPath = value;
    if (value.startsWith("file://")) {
      localPath = decodeURIComponent(value.slice(7));
      if (os.platform() === "win32" && /^\/[A-Za-z]:/.test(localPath)) localPath = localPath.slice(1);
    }
    localPath = path.resolve(localPath);
    if (!fs.statSync(localPath).isFile()) throw new Error(`文件不存在: ${localPath}`);
    return { path: localPath, temporary: false };
  }
  async downloadFile(url, destination, redirects = 0) {
    if (redirects > 5) throw new Error("下载图片重定向次数过多");
    const client = url.startsWith("https:") ? (await import('https')).default : (await import('http')).default;
    await new Promise((resolve, reject) => {
      const request = client.get(url, (response) => {
        const status = Number(response.statusCode || 0);
        if (status >= 300 && status < 400 && response.headers.location) {
          response.resume();
          const next = new URL(response.headers.location, url).toString();
          this.downloadFile(next, destination, redirects + 1).then(resolve, reject);
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
    const groups = result?.groupList || result?.groups || result?.data || result?.result?.groupList || [];
    return Array.from(groups).map((group) => ({
      group_id: Number(group.groupCode || group.group_id || group.groupId) || group.groupCode || group.group_id,
      group_name: group.groupName || group.group_name || "",
      member_count: Number(group.memberNum || group.member_count || 0),
      max_member_count: Number(group.maxMemberNum || group.max_member_count || 0)
    }));
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
    const ids = (result?.data || []).flatMap((item) => item.buddyUids || []);
    return ids.map((uid) => ({ user_id: Number(uid) || uid, nickname: service.getBuddyNick?.(uid) || "" }));
  }
  async deleteOneBotMessage(messageId) {
    const event = this.oneBotMessages.get(messageId);
    if (!event || !this.session) return {};
    const peer = { chatType: event.message_type === "group" ? 2 : 1, peerUid: String(event.group_id ?? event.user_id), guildId: "" };
    const service = this.session.getMsgService();
    if (service?.recallMsg) await service.recallMsg(peer, [messageId]);
    return {};
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
    const listenerImpl = new MessageListener();
    listenerImpl.onRecvMsg = (msgs) => {
      for (const msg of msgs) {
        self.handleMessage(msg);
      }
    };
    this.msgListener = proxied(listenerImpl);
    try {
      this.session.getMsgService().addKernelMsgListener(this.msgListener);
      log(id, "[MSG] 消息监听注册成功 (Proxy dispatch)");
    } catch (e) {
      logErr(id, "[MSG] 注册消息监听失败:", e.message);
    }
  }
  handleMessage(msg) {
    const elements = msg.elements || [];
    if (!elements.length) return;
    const event = this.toOneBotEvent(msg);
    const messageId = String(event.message_id);
    this.oneBotMessages.set(messageId, event);
    if (this.oneBotMessages.size > 500) {
      this.oneBotMessages.delete(this.oneBotMessages.keys().next().value);
    }
    this.oneBotEventCallback?.(event);
    for (const element of elements) {
      if (!element?.walletElement) continue;
      const packet = this.rememberRedPacket(msg, element.walletElement);
      if (packet) this.oneBotEventCallback?.(this.redPacketNotice(packet));
    }
  }
  toOneBotEvent(msg) {
    const message = [];
    const inlineKeyboard = [];
    for (const element of msg.elements || []) {
      if (element.elementType === 1 && element.textElement?.content) {
        message.push({ type: "text", data: { text: element.textElement.content } });
      } else if (element.elementType === 2) {
        message.push({ type: "image", data: { file: element.picElement?.sourcePath || element.picElement?.url || "" } });
      } else if (element.elementType === 6) {
        message.push({ type: "face", data: { id: String(element.faceElement?.faceIndex || "") } });
      } else if (element.walletElement) {
        const title = String(element.walletElement?.receiver?.title || element.walletElement?.receiver?.notice || "").trim();
        message.push({ type: "text", data: { text: title ? `[QQ红包] ${title}` : "[QQ红包]" } });
      }
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
    const rawId = String(msg.msgId || Date.now());
    const parsedId = Number(rawId);
    const messageId = Number.isFinite(parsedId) && parsedId > 0 ? parsedId : Math.abs(Array.from(rawId).reduce((sum, char) => sum * 31 + char.charCodeAt(0) | 0, 0));
    const isGroup = Number(msg.chatType) === 2;
    const rawTime = Number(msg.msgTime || 0);
    const event = {
      time: rawTime > 1e10 ? Math.floor(rawTime / 1e3) : rawTime || Math.floor(Date.now() / 1e3),
      self_id: this.getSelfUin(),
      post_type: "message",
      message_type: isGroup ? "group" : "private",
      sub_type: "normal",
      message_id: messageId,
      user_id: Number(msg.senderUin) || msg.senderUin || 0,
      message,
      raw_message: message.filter((item) => item.type === "text").map((item) => item.data.text).join(""),
      sender: { user_id: Number(msg.senderUin) || msg.senderUin || 0, nickname: msg.sendNickName || msg.sendMemberName || "", card: msg.sendMemberName || "" }
    };
    if (isGroup) event.group_id = Number(msg.peerUin) || msg.peerUin;
    if (inlineKeyboard.length) event._elaina_inline_keyboard = inlineKeyboard;
    return event;
  }
}

const BOT_ID = process.env["ELAINAQQ_BOT_ID"] || "";
const MANAGER_URL = process.env["ELAINAQQ_MANAGER_URL"] || "http://127.0.0.1:30010";
const EMBEDDED = process.env["ELAINAQQ_EMBEDDED"] === "1";
let shuttingDown = false;
const lifecycleKeepAlive = setInterval(() => {}, 60_000);
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
function reportStatus(runtime) {
  callManager("POST", "/api/embedded/events", { bot_id: BOT_ID, self_id: runtime.loginUin || BOT_ID, runtime }).catch((error) => {
    logErr(BOT_ID, "[BRIDGE] 状态上报失败:", error?.message || error);
  });
}
function reportEmbeddedEvent(event) {
  callManager("POST", "/api/embedded/events", { bot_id: BOT_ID, self_id: event.self_id || BOT_ID, event }).catch((error) => {
    logErr(BOT_ID, "[BRIDGE] 事件上报失败:", error?.message || error);
  });
}
function callManager(method, path, body) {
  return callManagerRaw(method, path, JSON.stringify(body));
}
function callManagerRaw(method, apiPath, payload) {
  return new Promise((resolve, reject) => {
    try {
      const url = new URL(apiPath, MANAGER_URL);
      const req = http.request({
        agent: keepAliveAgent,
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method,
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) },
        timeout: 2e3
        // 本地桥接服务无需长轮询。
      }, (res) => {
        let responseBody = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          if (responseBody.length < 32768) responseBody += chunk;
        });
        res.on("end", () => {
          const statusCode = Number(res.statusCode || 500);
          if (statusCode >= 200 && statusCode < 300) {
            resolve({ statusCode, body: responseBody });
            return;
          }
          let message = `HTTP ${statusCode}`;
          try {
            const data = responseBody ? JSON.parse(responseBody) : {};
            message = data.error || data.message || message;
          } catch {
          }
          reject(new Error(message));
        });
      });
      req.on("error", reject);
      req.on("timeout", () => {
        req.destroy(new Error("本地桥接请求超时"));
      });
      req.write(payload);
      req.end();
    } catch (error) {
      reject(error);
    }
  });
}
function managerRequest(method, apiPath, body = null, timeout = 3e4) {
  return new Promise((resolve, reject) => {
    try {
      const url = new URL(apiPath, MANAGER_URL);
      const payload = body === null ? "" : JSON.stringify(body);
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
    } else if (command.type === "refresh_qr") {
      result = { success: true, data: instance.refreshQrCode() };
    } else {
      throw new Error("不支持的控制命令");
    }
  } catch (error) {
    const message = error?.message || String(error);
    result = { status: "failed", retcode: 1400, data: null, message, wording: message };
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
  if (!shuttingDown) console.error("[Worker] 事件循环意外结束，退出码: " + code);
});
if (process.env["ELAINAQQ_WORKER_TEST"] !== "1") {
  main().catch((e) => {
    console.error("[Worker] 启动失败:", e);
    clearInterval(lifecycleKeepAlive);
    process.exit(1);
  });
}

export { QQInstance };
