import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BRIDGE_DIR = path.dirname(fileURLToPath(import.meta.url));

export const DEFAULT_VIDEO_THUMB = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgAAAAAgAB4iG8MwAAAABJRU5ErkJggg==",
  "base64",
);

export class MediaRuntime {
  constructor({ logger = () => {} } = {}) {
    this.logger = logger;
    this.loaded = false;
    this.addon = null;
    this.reason = "媒体原生模块尚未加载";
  }

  addonPath() {
    const fileName = `ffmpegAddon.${process.platform}.${process.arch}.node`;
    return path.resolve(BRIDGE_DIR, "..", "native", "media", fileName);
  }

  load() {
    if (this.loaded) return Boolean(this.addon);
    this.loaded = true;
    const addonPath = this.addonPath();
    if (!fs.existsSync(addonPath)) {
      this.reason = `当前平台缺少媒体原生模块: ${addonPath}`;
      return false;
    }
    try {
      const nativeModule = { exports: {} };
      process.dlopen(nativeModule, addonPath);
      this.addon = nativeModule.exports;
      this.reason = "";
      return true;
    } catch (error) {
      this.reason = `媒体原生模块加载失败: ${error?.message || error}`;
      this.logger(this.reason);
      return false;
    }
  }

  status() {
    return {
      available: this.load(),
      path: this.addonPath(),
      reason: this.reason,
    };
  }

  isSilk(filePath) {
    let fd;
    try {
      fd = fs.openSync(filePath, "r");
      const header = Buffer.alloc(10);
      fs.readSync(fd, header, 0, header.length, 0);
      const text = header.toString("binary");
      return text.includes("#!SILK") || text.includes("\x02#!SILK");
    } catch {
      return false;
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
    }
  }

  async duration(filePath) {
    if (this.load() && typeof this.addon?.getDuration === "function") {
      try {
        const duration = Number(await this.addon.getDuration(filePath));
        if (Number.isFinite(duration) && duration > 0) return duration;
      } catch {
      }
    }
    const size = fs.statSync(filePath).size;
    return Math.max(1, Math.floor(size / 1024 / 3));
  }

  async videoInfo(filePath) {
    if (this.load() && typeof this.addon?.getVideoInfo === "function") {
      try {
        const info = await this.addon.getVideoInfo(filePath);
        return {
          width: Math.max(1, Number(info?.width || 100)),
          height: Math.max(1, Number(info?.height || 100)),
          duration: Math.max(0, Number(info?.duration || 60)),
          format: String(info?.format || "mp4").split(",")[0],
          thumbnail: Buffer.isBuffer(info?.image)
            ? info.image
            : info?.image instanceof Uint8Array ? Buffer.from(info.image) : null,
        };
      } catch (error) {
        this.logger(`读取视频信息失败，使用兼容值: ${error?.message || error}`);
      }
    }
    return { width: 100, height: 100, duration: 60, format: "mp4", thumbnail: null };
  }

  async convertToSilk(inputPath, outputPath) {
    if (this.isSilk(inputPath)) return { path: inputPath, converted: false };
    if (!this.load() || typeof this.addon?.convertToNTSilkTct !== "function") {
      throw new Error(this.reason || "当前平台无法将语音转换为 QQ Silk");
    }
    try {
      await this.addon.convertToNTSilkTct(inputPath, outputPath);
      if (!fs.existsSync(outputPath) || !fs.statSync(outputPath).size) {
        throw new Error("语音转换失败: Silk 输出为空");
      }
      return { path: outputPath, converted: true };
    } catch (error) {
      try { fs.unlinkSync(outputPath); } catch {
      }
      throw error;
    }
  }

  async convertAudio(inputPath, outputPath, format) {
    if (!this.load() || typeof this.addon?.decodeAudioToFmt !== "function") {
      throw new Error(this.reason || "当前平台无法转换语音格式");
    }
    try {
      await this.addon.decodeAudioToFmt(inputPath, outputPath, String(format));
      if (!fs.existsSync(outputPath) || !fs.statSync(outputPath).size) {
        throw new Error("语音格式转换失败: 输出为空");
      }
      return outputPath;
    } catch (error) {
      try { fs.unlinkSync(outputPath); } catch {
      }
      throw error;
    }
  }
}
