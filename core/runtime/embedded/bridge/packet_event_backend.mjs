import fs from "node:fs";
import { constants } from "node:os";

const SUPPORTED_PLATFORMS = new Set([
  "win32.x64",
  "linux.x64",
  "linux.arm64",
  "darwin.x64",
  "darwin.arm64",
]);

/** Observe QQNT packets through the same MoeHoo hook used by NapCat event parsers. */
export class NativePacketEventBackend {
  constructor({
    version,
    nativePath = "",
    offsetsPath = "",
    mode = "auto",
    logger = () => {},
    onPacket = () => {},
  } = {}) {
    this.version = String(version || "");
    this.nativePath = String(nativePath || "");
    this.offsetsPath = String(offsetsPath || "");
    this.mode = String(mode || "auto").toLowerCase();
    this.logger = logger;
    this.onPacket = onPacket;
    this.nativeModule = null;
    this.available = false;
    this.loaded = false;
    this.offsets = null;
    this.reason = "尚未初始化";
  }

  load() {
    if (this.loaded) return true;
    if (["off", "false", "0", "disable", "disabled"].includes(this.mode)) {
      this.reason = "配置已禁用原始包事件后端";
      return false;
    }
    const platform = process.platform + "." + process.arch;
    if (!SUPPORTED_PLATFORMS.has(platform)) {
      this.reason = "MoeHoo 不支持当前平台: " + platform;
      return false;
    }
    if (!this.nativePath || !fs.existsSync(this.nativePath)) {
      this.reason = "未找到 MoeHoo 原始包事件模块";
      return false;
    }
    try {
      this.nativeModule = { exports: {} };
      process.dlopen(this.nativeModule, this.nativePath, constants.dlopen.RTLD_LAZY);
      this.loaded = true;
      this.reason = "原始包事件 Hook 尚未安装";
      return true;
    } catch (error) {
      this.reason = "加载 MoeHoo 失败: " + (error?.message || error);
      return false;
    }
  }

  initHook() {
    if (!this.loaded && !this.load()) return false;
    if (!this.offsetsPath || !fs.existsSync(this.offsetsPath)) {
      this.reason = "未找到原始包事件版本偏移表";
      return false;
    }
    const key = this.version + "-" + process.arch;
    let offsets;
    try {
      offsets = JSON.parse(fs.readFileSync(this.offsetsPath, "utf8"))?.[key];
    } catch (error) {
      this.reason = "读取原始包事件偏移表失败: " + (error?.message || error);
      return false;
    }
    if (!offsets?.send || !offsets?.recv) {
      this.reason = "当前 QQ 版本没有安全的原始包事件偏移: " + key;
      return false;
    }
    const initHook = this.nativeModule?.exports?.initHook;
    if (typeof initHook !== "function") {
      this.reason = "MoeHoo 模块缺少 initHook";
      return false;
    }
    try {
      const callback = (type, uin, cmd, seq, hexData) => {
        try {
          const result = this.onPacket({
            type: Number(type),
            uin: String(uin || ""),
            cmd: String(cmd || ""),
            seq: Number(seq || 0),
            hex_data: String(hexData || ""),
          });
          Promise.resolve(result).catch((error) => {
            this.logger("原始包事件处理失败: " + (error?.message || error));
          });
        } catch (error) {
          this.logger("原始包事件处理失败: " + (error?.message || error));
        }
      };
      const initialized = initHook(String(offsets.send), String(offsets.recv), callback, false);
      if (initialized === false) {
        this.reason = "MoeHoo Hook 初始化失败: " + key;
        return false;
      }
      this.offsets = { send: String(offsets.send), recv: String(offsets.recv) };
      this.available = true;
      this.reason = "";
      this.logger("原始包事件 Hook 初始化成功: " + key);
      return true;
    } catch (error) {
      this.reason = "初始化 MoeHoo Hook 失败: " + (error?.message || error);
      return false;
    }
  }

  init() {
    return this.load() && this.initHook();
  }

  status() {
    return {
      enabled: this.available,
      available: this.available,
      loaded: this.loaded,
      backend: "moehoo",
      version: this.version,
      arch: process.arch,
      offsets: this.offsets,
      reason: this.reason,
    };
  }
}
