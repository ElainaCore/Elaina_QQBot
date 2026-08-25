import fs from "node:fs";
import { constants } from "node:os";

import { normalizePacketBypass, packetBoolean } from "./packet_config.mjs";
import { packetResource, readPacketOffsets } from "./packet_resources.mjs";

/** 加载框架内置的对应版本原始发包钩子。 */
export class NativePacketBackend {
  constructor({
    version,
    mode = "auto",
    logger = () => {},
    bypassOptions = {},
    verbose = false,
  } = {}) {
    this.version = String(version || "");
    this.resource = packetResource("sender");
    this.nativePath = this.resource.nativePath;
    this.offsetsPath = this.resource.offsetsPath;
    this.mode = String(mode || "auto").toLowerCase();
    this.logger = logger;
    this.bypassOptions = normalizePacketBypass(bypassOptions);
    this.verbose = packetBoolean(verbose, false);
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

    if (!this.resource.supported) {
      this.reason = "原始发包模块不支持当前平台: " + this.resource.platform;
      return false;
    }
    if (!this.nativePath || !fs.existsSync(this.nativePath)) {
      this.reason = "未找到原始发包模块: " + this.nativePath;
      return false;
    }

    try {
      this.nativeModule = { exports: {} };
      process.dlopen(this.nativeModule, this.nativePath, constants.dlopen.RTLD_LAZY);
      this.loaded = true;
      const setVerbose = this.nativeModule.exports?.setVerbose;
      if (typeof setVerbose === "function") setVerbose(this.verbose);
      const enableAllBypasses = this.nativeModule.exports?.enableAllBypasses;
      if (typeof enableAllBypasses === "function") {
        this.bypassEnabled = Boolean(enableAllBypasses(this.bypassOptions));
      }
      this.reason = "原始发包 Hook 尚未安装";
      this.logger(
        "原始发包模块已加载，native bypass " +
        (this.bypassEnabled ? "已启用" : "未启用或当前 addon 不支持")
      );
      return true;
    } catch (error) {
      this.reason = "加载原始发包模块失败: " + (error?.message || error);
      this.loaded = false;
      return false;
    }
  }

  initHook() {
    if (!this.loaded && !this.load()) return false;
    if (!this.offsetsPath || !fs.existsSync(this.offsetsPath)) {
      this.reason = "未找到原始发包版本偏移表: " + this.offsetsPath;
      return false;
    }

    let key;
    let offsets;
    try {
      ({ key, offsets } = readPacketOffsets(this.resource, this.version));
    } catch (error) {
      this.reason = "读取原始发包偏移表失败: " + (error?.message || error);
      return false;
    }
    if (!offsets?.send || !offsets?.recv) {
      this.reason = "当前 QQ 版本没有安全的原始发包偏移: " + key;
      return false;
    }

    try {
      const initHook = this.nativeModule?.exports?.initHook;
      if (typeof initHook !== "function") {
        this.reason = "原始发包模块缺少 initHook";
        return false;
      }
      if (!initHook(String(offsets.send), String(offsets.recv))) {
        this.reason = "原始发包 Hook 初始化失败: " + key;
        return false;
      }
      this.offsets = { send: String(offsets.send), recv: String(offsets.recv) };
      this.available = true;
      this.reason = "";
      this.logger("原始发包 Hook 初始化成功: " + key);
      return true;
    } catch (error) {
      this.reason = "初始化原始发包 Hook 失败: " + (error?.message || error);
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
      bypass_options: { ...this.bypassOptions },
      verbose: this.verbose,
      hook_initialized: this.available,
      backend: "native_packet",
      version: this.version,
      arch: process.arch,
      offsets: this.offsets,
      reason: this.reason,
    };
  }
}
