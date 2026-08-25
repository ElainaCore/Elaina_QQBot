import fs from 'fs';
import os from 'os';
import path from 'path';

export const BUILTIN_QQ_VERSION = "3.2.32-52194";
export const QQ_APPID_TABLE = {
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
    try {
      const versionConfig = JSON.parse(fs.readFileSync(versionConfigPath, "utf-8"));
      console.log(`[QQ信息] 使用快更配置: ${versionConfig.curVersion}`);
      return buildQQInfo(execPath, versionConfig.curVersion);
    } catch (e) {
      console.log(`[QQ信息] 读取快更配置失败: ${e}`);
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
        console.log(`[QQ信息] 从 package.json 读取: ${packageInfo.version}`);
        return buildQQInfo(execPath, packageInfo.version);
      }
    } catch (e) {
      console.log(`[QQ信息] 读取 package.json 失败: ${e}`);
    }
  }
  console.log(`[QQ信息] 使用内置版本: ${BUILTIN_QQ_VERSION}`);
  return buildQQInfo(execPath, BUILTIN_QQ_VERSION);
}
export function buildQQInfo(execPath, version) {
  const buildVersion = version.split("-")[1] || "";
  let appid;
  let qua;
  if (QQ_APPID_TABLE[version]) {
    appid = QQ_APPID_TABLE[version].appid;
    qua = QQ_APPID_TABLE[version].qua;
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

