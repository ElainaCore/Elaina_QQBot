import fs from "node:fs";
import { constants } from "node:os";

const SUPPORTED_PLATFORMS = new Set([
  "win32.x64",
  "linux.x64",
  "linux.arm64",
  "darwin.x64",
  "darwin.arm64",
]);

/** Install the same version-specific napi2native hook that NapCat uses for raw packets. */
export class NativePacketBackend {
  constructor({ version, nativePath = "", offsetsPath = "", mode = "auto", logger = () => {} } = {}) {
    this.version = String(version || "");
    this.nativePath = String(nativePath || "");
    this.offsetsPath = String(offsetsPath || "");
    this.mode = String(mode || "auto").toLowerCase();
    this.logger = logger;
    this.available = false;
    this.reason = "尚未初始化";
  }

  init() {
    if (["off", "false", "0", "disabled"].includes(this.mode)) {
      this.reason = "配置已禁用原始发包后端";
      return false;
    }

    const platform = process.platform + "." + process.arch;
    if (!SUPPORTED_PLATFORMS.has(platform)) {
      this.reason = "napi2native 不支持当前平台: " + platform;
      return false;
    }
    if (!this.nativePath || !fs.existsSync(this.nativePath)) {
      this.reason = "未找到 napi2native 原生模块";
      return false;
    }
    if (!this.offsetsPath || !fs.existsSync(this.offsetsPath)) {
      this.reason = "未找到 napi2native 版本偏移表";
      return false;
    }

    const key = this.version + "-" + process.arch;
    let offsets;
    try {
      const table = JSON.parse(fs.readFileSync(this.offsetsPath, "utf8"));
      offsets = table?.[key];
    } catch (error) {
      this.reason = "读取 napi2native 偏移表失败: " + (error?.message || error);
      return false;
    }
    if (!offsets?.send || !offsets?.recv) {
      this.reason = "当前 QQ 版本没有安全的原始发包偏移: " + key;
      return false;
    }

    try {
      const nativeModule = { exports: {} };
      process.dlopen(nativeModule, this.nativePath, constants.dlopen.RTLD_LAZY);
      const initHook = nativeModule.exports?.initHook;
      if (typeof initHook !== "function") {
        this.reason = "napi2native 模块缺少 initHook";
        return false;
      }
      if (!initHook(String(offsets.send), String(offsets.recv))) {
        this.reason = "napi2native Hook 初始化失败: " + key;
        return false;
      }
      this.available = true;
      this.reason = "";
      this.logger("原始发包 Hook 初始化成功: " + key);
      return true;
    } catch (error) {
      this.reason = "加载 napi2native 失败: " + (error?.message || error);
      return false;
    }
  }

  status() {
    return {
      enabled: this.available,
      available: this.available,
      backend: "native",
      version: this.version,
      arch: process.arch,
      reason: this.reason,
    };
  }
}
