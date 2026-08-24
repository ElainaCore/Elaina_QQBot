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
    this.nativeModule = null;
    this.offsets = null;
    this.loaded = false;
    this.bypassEnabled = false;
  }

  load() {
    if (this.loaded) return true;
    if (["off", "false", "0", "disable", "disabled"].includes(this.mode)) {
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

    try {
      this.nativeModule = { exports: {} };
      process.dlopen(this.nativeModule, this.nativePath, constants.dlopen.RTLD_LAZY);
      this.loaded = true;
      const enableAllBypasses = this.nativeModule.exports?.enableAllBypasses;
      if (typeof enableAllBypasses === "function") {
        this.bypassEnabled = Boolean(enableAllBypasses({
          hook: true,
          window: true,
          module: true,
          process: true,
          container: true,
          js: true,
        }));
      }
      this.reason = "原始发包 Hook 尚未安装";
      this.logger(
        "napi2native 已加载，native bypass " +
        (this.bypassEnabled ? "已启用" : "未启用或当前 addon 不支持")
      );
      return true;
    } catch (error) {
      this.reason = "加载 napi2native 失败: " + (error?.message || error);
      this.loaded = false;
      return false;
    }
  }

  initHook() {
    if (!this.loaded && !this.load()) return false;
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
      const initHook = this.nativeModule?.exports?.initHook;
      if (typeof initHook !== "function") {
        this.reason = "napi2native 模块缺少 initHook";
        return false;
      }
      if (!initHook(String(offsets.send), String(offsets.recv))) {
        this.reason = "napi2native Hook 初始化失败: " + key;
        return false;
      }
      this.offsets = { send: String(offsets.send), recv: String(offsets.recv) };
      this.available = true;
      this.reason = "";
      this.logger("原始发包 Hook 初始化成功: " + key);
      return true;
    } catch (error) {
      this.reason = "初始化 napi2native Hook 失败: " + (error?.message || error);
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
      bypass_enabled: this.bypassEnabled,
      hook_initialized: this.available,
      backend: "native",
      version: this.version,
      arch: process.arch,
      offsets: this.offsets,
      reason: this.reason,
    };
  }
}
