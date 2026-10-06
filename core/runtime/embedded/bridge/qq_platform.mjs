import fs from 'fs';
import os from 'os';
import path from 'path';

// 应用 ID / QUA 与内置版本跟随 NapCat (napcat-core/external/appid.json)。
// 表按平台分前缀: 9.9.* 为 Windows, 3.2.* 为 Linux, 6.9.* 为 macOS。
function loadQQAppidTable() {
  const raw = JSON.parse(
    fs.readFileSync(new URL("./qq_appid.json", import.meta.url), "utf8")
  );
  const table = {};
  for (const [version, info] of Object.entries(raw)) {
    // 跳过带 arch 后缀的键 (如 3.2.33-52892-arm64)，运行时按 <version>-<arch> 另行解析。
    if (version.split("-").length > 2) continue;
    if (!info || info.appid == null) continue;
    table[version] = { appid: String(info.appid), qua: String(info.qua) };
  }
  return table;
}

export const QQ_APPID_TABLE = loadQQAppidTable();

function platformAppidTable(prefixes) {
  return Object.fromEntries(
    Object.entries(QQ_APPID_TABLE).filter(([version]) =>
      prefixes.some((prefix) => version.startsWith(prefix))
    )
  );
}

export const WINDOWS_QQ_APPID_TABLE = platformAppidTable(["9.9"]);
export const LINUX_QQ_APPID_TABLE = platformAppidTable(["3.2"]);
export const MACOS_QQ_APPID_TABLE = platformAppidTable(["6.9"]);

function platformVersionPrefixes() {
  if (os.platform() === "win32") return ["9.9"];
  if (os.platform() === "darwin") return ["6.9"];
  return ["3.2"];
}

function latestBuiltinVersion() {
  const prefixes = platformVersionPrefixes();
  const versions = Object.keys(QQ_APPID_TABLE).filter((version) =>
    prefixes.some((prefix) => version.startsWith(prefix))
  );
  if (!versions.length) return "";
  versions.sort(
    (a, b) => (Number(a.split("-")[1]) || 0) - (Number(b.split("-")[1]) || 0)
  );
  return versions[versions.length - 1];
}

// 无法从 QQ 安装目录读取版本时的兜底版本，取当前平台表中构建号最大者。
export const BUILTIN_QQ_VERSION = latestBuiltinVersion() || "9.9.36-53489";
export function findQQPath() {
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
export function getQQInfo(execPath) {
  if (process.env["QQ_VERSION"]) {
    const version = process.env["QQ_VERSION"];
    console.log(`[QQ信息] 使用环境变量指定版本: ${version}`);
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
    let versionConfig;
    try {
      versionConfig = JSON.parse(fs.readFileSync(versionConfigPath, "utf-8"));
    } catch (e) {
      console.log('[QQ信息] 读取版本配置失败');
    }
    if (versionConfig) {
      const version = String(versionConfig.curVersion || "").trim();
      if (!version) throw new Error('QQ 版本配置缺少 curVersion');
      console.log(`[QQ信息] 使用版本配置: ${version}`);
      return buildQQInfo(execPath, version);
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
    let packageInfo;
    try {
      packageInfo = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
    } catch (e) {
      console.log(`[QQ信息] 读取 package.json 失败: ${e}`);
    }
    if (packageInfo?.version) {
      const version = String(packageInfo.version).trim();
      console.log(`[QQ信息] 从 package.json 读取: ${version}`);
      return buildQQInfo(execPath, version);
    }
  }
  console.log(`[QQ信息] 使用内置版本: ${BUILTIN_QQ_VERSION}`);
  return buildQQInfo(execPath, BUILTIN_QQ_VERSION);
}
export function buildQQInfo(execPath, version) {
  if (os.platform() === "win32" && !WINDOWS_QQ_APPID_TABLE[version]) {
    throw new Error(`当前 Windows QQ 版本 ${version} 暂不兼容，无法启动 HookQQ`);
  }
  const buildVersion = version.split("-")[1] || "";
  let appid;
  let qua;
  if (QQ_APPID_TABLE[version]) {
    appid = QQ_APPID_TABLE[version].appid;
    qua = QQ_APPID_TABLE[version].qua;
  } else {
    // 非 Windows 的未知版本从 QQ native 模块读取 AppID。
    appid = readAppidFromMajor(execPath, version);
    const platformAppid = { win32: "537246092", darwin: "537246140", linux: "537246140" };
    appid = appid || platformAppid[os.platform()] || "537246092";
    const platformPrefix = { win32: "WIN", darwin: "MAC", linux: "LNX" };
    const prefix = platformPrefix[os.platform()] || "WIN";
    const productVersion = version.split("-")[0] || version;
    qua = `V1_${prefix}_NQ_${productVersion}_${buildVersion}_GW_B`;
  }
  console.log(`[QQ信息] 版本=${version}, AppID=${appid}, QUA=${qua}`);
  return { execPath, version, buildVersion, appid, qua };
}
export function majorPathCandidates(execPath, version) {
  const base = path.dirname(execPath);
  if (os.platform() === "darwin") return [path.resolve(base, "../Resources/app/major.node")];
  if (os.platform() === "linux") return [path.resolve(base, "resources/app/major.node"), path.resolve(base, "resources/app/resources/app/major.node")];
  return [path.resolve(base, "versions/" + version + "/resources/app/major.node"), path.resolve(base, "resources/app/major.node"), path.resolve(base, "resources/app/versions/" + version + "/major.node")];
}
export function readAppidFromMajor(execPath, version) {
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
    console.log("[QQ信息] 读取 major.node AppID 失败: " + error.message);
  }
  return "";
}
export function loadWrapper(execPath, version) {
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
export function getDataPaths(wrapper) {
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
