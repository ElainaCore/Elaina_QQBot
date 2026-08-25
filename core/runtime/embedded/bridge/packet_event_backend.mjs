import fs from "node:fs";
import { constants } from "node:os";

import { packetBoolean } from "./packet_config.mjs";
import { packetResource, readPacketOffsets } from "./packet_resources.mjs";

/** 通过框架内置事件钩子监听 QQNT 数据包。 */
export class NativePacketEventBackend {
  constructor({
    version,
    mode = "auto",
    logger = () => {},
    onPacket = null,
    o3HookMode = false,
  } = {}) {
    this.version = String(version || "");
    this.resource = packetResource("events");
    this.nativePath = this.resource.nativePath;
    this.offsetsPath = this.resource.offsetsPath;
    this.mode = String(mode || "auto").toLowerCase();
    this.logger = logger;
    this.o3HookMode = packetBoolean(o3HookMode, false);
    this.listeners = new Map();
    this.nativeModule = null;
    this.available = false;
    this.loaded = false;
    this.offsets = null;
    this.reason = "尚未初始化";
    if (typeof onPacket === "function") this.onAll(onPacket);
  }

  addListener(key, callback, once = false) {
    if (typeof callback !== "function") throw new TypeError("原始包监听器必须是函数");
    if (!this.listeners.has(key)) this.listeners.set(key, new Set());
    const entry = { callback, once: Boolean(once) };
    this.listeners.get(key).add(entry);
    return () => this.removeListener(key, callback);
  }

  removeListener(key, callback) {
    const entries = this.listeners.get(key);
    if (!entries) return false;
    for (const entry of entries) {
      if (entry.callback !== callback) continue;
      entries.delete(entry);
      if (!entries.size) this.listeners.delete(key);
      return true;
    }
    return false;
  }

  onAll(callback) { return this.addListener("all", callback); }
  onType(type, callback) { return this.addListener("type:" + Number(type), callback); }
  onSend(callback) { return this.onType(0, callback); }
  onRecv(callback) { return this.onType(1, callback); }
  onCmd(cmd, callback) { return this.addListener("cmd:" + String(cmd), callback); }
  onExact(type, cmd, callback) {
    return this.addListener("exact:" + Number(type) + ":" + String(cmd), callback);
  }
  onceAll(callback) { return this.addListener("all", callback, true); }
  onceType(type, callback) { return this.addListener("type:" + Number(type), callback, true); }
  onceSend(callback) { return this.onceType(0, callback); }
  onceRecv(callback) { return this.onceType(1, callback); }
  onceCmd(cmd, callback) { return this.addListener("cmd:" + String(cmd), callback, true); }
  onceExact(type, cmd, callback) {
    return this.addListener("exact:" + Number(type) + ":" + String(cmd), callback, true);
  }
  off(key, callback) { return this.removeListener(String(key), callback); }
  offAll(key) { return this.listeners.delete(String(key)); }
  removeAllListeners() { this.listeners.clear(); }
  listenerCount() {
    let count = 0;
    for (const entries of this.listeners.values()) count += entries.size;
    return count;
  }

  emitPacket(packet) {
    const type = Number(packet.type);
    const cmd = String(packet.cmd || "");
    const keys = ["exact:" + type + ":" + cmd, "cmd:" + cmd, "type:" + type, "all"];
    for (const key of keys) {
      const entries = this.listeners.get(key);
      if (!entries) continue;
      for (const entry of [...entries]) {
        if (entry.once) entries.delete(entry);
        try {
          Promise.resolve(entry.callback(packet)).catch((error) => {
            this.logger("原始包事件处理失败: " + (error?.message || error));
          });
        } catch (error) {
          this.logger("原始包事件处理失败: " + (error?.message || error));
        }
      }
      if (!entries.size) this.listeners.delete(key);
    }
  }

  load() {
    if (this.loaded) return true;
    if (["off", "false", "0", "disable", "disabled"].includes(this.mode)) {
      this.reason = "配置已禁用原始包事件后端";
      return false;
    }
    if (!this.resource.supported) {
      this.reason = "原始包事件模块不支持当前平台: " + this.resource.platform;
      return false;
    }
    if (!this.nativePath || !fs.existsSync(this.nativePath)) {
      this.reason = "未找到原始包事件模块: " + this.nativePath;
      return false;
    }
    try {
      this.nativeModule = { exports: {} };
      process.dlopen(this.nativeModule, this.nativePath, constants.dlopen.RTLD_LAZY);
      this.loaded = true;
      this.reason = "原始包事件 Hook 尚未安装";
      return true;
    } catch (error) {
      this.reason = "加载原始包事件模块失败: " + (error?.message || error);
      return false;
    }
  }

  initHook() {
    if (!this.loaded && !this.load()) return false;
    if (!this.offsetsPath || !fs.existsSync(this.offsetsPath)) {
      this.reason = "未找到原始包事件版本偏移表: " + (this.offsetsPath || "未配置路径");
      return false;
    }
    let key;
    let offsets;
    try {
      ({ key, offsets } = readPacketOffsets(this.resource, this.version));
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
      this.reason = "原始包事件模块缺少 initHook";
      return false;
    }
    try {
      const setO3Setting = this.nativeModule?.exports?.setO3Setting;
      if (typeof setO3Setting === "function") setO3Setting(this.o3HookMode);
      const callback = (type, uin, cmd, seq, hexData) => {
        this.emitPacket({
          type: Number(type),
          uin: String(uin || ""),
          cmd: String(cmd || ""),
          seq: Number(seq || 0),
          hex_data: String(hexData || ""),
        });
      };
      const initialized = initHook(
        String(offsets.send),
        String(offsets.recv),
        callback,
        this.o3HookMode,
      );
      if (initialized === false) {
        this.reason = "原始包事件 Hook 初始化失败: " + key;
        return false;
      }
      this.offsets = { send: String(offsets.send), recv: String(offsets.recv) };
      this.available = true;
      this.reason = "";
      this.logger("原始包事件 Hook 初始化成功: " + key);
      return true;
    } catch (error) {
      this.reason = "初始化原始包事件 Hook 失败: " + (error?.message || error);
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
      backend: "native_packet_events",
      o3_hook_mode: this.o3HookMode,
      listener_count: this.listenerCount(),
      version: this.version,
      arch: process.arch,
      offsets: this.offsets,
      reason: this.reason,
    };
  }
}
