import { NativePacketBackend } from "./packet_backend.mjs";
import { readPacketRuntimeOptions } from "./packet_config.mjs";
import { NativePacketEventBackend } from "./packet_event_backend.mjs";

const MESSAGE_PUSH_COMMAND = "trpc.msg.olpush.OlPushService.MsgPush";

function unavailableStatus(backend, version, reason) {
  return {
    enabled: false,
    available: false,
    loaded: false,
    backend,
    version: String(version || ""),
    arch: process.arch,
    reason,
  };
}

/** 统一管理原始包发送与事件钩子的装载顺序和状态。 */
export class PacketRuntime {
  constructor({ version, options = readPacketRuntimeOptions(), logger = () => {}, onMessagePush = null } = {}) {
    this.version = String(version || "");
    this.logger = logger;
    this.sender = new NativePacketBackend({
      version: this.version,
      mode: options.mode,
      bypassOptions: options.bypassOptions,
      verbose: options.verbose,
      logger: (message) => logger("sender", message),
    });
    this.events = new NativePacketEventBackend({
      version: this.version,
      mode: options.mode,
      o3HookMode: options.o3HookMode,
      logger: (message) => logger("events", message),
    });
    if (typeof onMessagePush === "function") {
      this.events.onCmd(MESSAGE_PUSH_COMMAND, onMessagePush);
    }
  }

  loadBeforeSession() {
    const senderLoaded = this.sender.load();
    if (!senderLoaded) this.logger("sender", this.sender.status().reason);
    const eventsLoaded = this.events.init();
    if (!eventsLoaded) this.logger("events", this.events.status().reason);
    return senderLoaded || eventsLoaded;
  }

  initializeAfterSession() {
    const initialized = this.sender.initHook();
    if (!initialized) this.logger("sender", this.sender.status().reason);
    return initialized;
  }

  close() {
    this.events.removeAllListeners();
  }

  status() {
    const sender = this.sender?.status() || unavailableStatus(
      "native_packet",
      this.version,
      "原始发包后端尚未初始化",
    );
    const events = this.events?.status() || unavailableStatus(
      "native_packet_events",
      this.version,
      "原始包事件后端尚未初始化",
    );
    return {
      ...sender,
      sender,
      events,
      event_available: Boolean(events.available),
    };
  }
}
