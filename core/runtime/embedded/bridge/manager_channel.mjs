import http from "node:http";

function stringifyJson(value) {
  const seen = new WeakSet();
  return JSON.stringify(value, (_, item) => {
    if (typeof item === "bigint") return item.toString();
    if (item instanceof Map) return Object.fromEntries(item);
    if (item instanceof Set) return Array.from(item);
    if (item instanceof Uint8Array) return Buffer.from(item).toString("base64");
    if (item && typeof item === "object") {
      if (seen.has(item)) return undefined;
      seen.add(item);
    }
    return item;
  });
}

function controlFailure(error) {
  const message = error?.message || String(error);
  const retcode = Number(error?.retcode || 1400);
  return {
    status: "failed",
    retcode: Number.isFinite(retcode) ? retcode : 1400,
    data: null,
    message,
    wording: message,
  };
}

export class EmbeddedManagerChannel {
  constructor({ botId, managerUrl, logger = console.error }) {
    this.botId = String(botId || "");
    this.managerUrl = String(managerUrl || "http://127.0.0.1:30010");
    this.logger = logger;
    this.instance = null;
    this.running = false;
    this.loopPromise = null;
    this.reportTails = new Map();
    this.statusTail = Promise.resolve();
    this.agent = new http.Agent({
      keepAlive: true,
      keepAliveMsecs: 30_000,
      maxSockets: 16,
      maxFreeSockets: 8,
    });
  }

  attach(instance) {
    this.instance = instance;
    instance.setStatusCallback((runtime) => this.reportStatus(runtime));
    instance.setOneBotEventCallback((event) => this.reportEvent(event));
    instance.setRedPacketCallback((packet) => this.reportRedPacket(packet));
  }

  start() {
    if (this.loopPromise) return this.loopPromise;
    this.running = true;
    this.loopPromise = this.controlLoop().finally(() => {
      this.loopPromise = null;
    });
    return this.loopPromise;
  }

  stop() {
    this.running = false;
    this.agent.destroy();
  }

  request(method, apiPath, body = null, timeout = 30_000) {
    return new Promise((resolve, reject) => {
      try {
        const url = new URL(apiPath, this.managerUrl);
        const payload = body === null ? "" : stringifyJson(body);
        const headers = body === null ? {} : {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        };
        const request = http.request({
          agent: this.agent,
          hostname: url.hostname,
          port: url.port,
          path: `${url.pathname}${url.search}`,
          method,
          headers,
          timeout,
        }, (response) => {
          if (response.statusCode === 204) {
            response.resume();
            response.on("end", () => resolve(null));
            return;
          }
          let responseBody = "";
          response.setEncoding("utf8");
          response.on("data", (chunk) => {
            responseBody += chunk;
            if (responseBody.length > 8 * 1024 * 1024) {
              request.destroy(new Error("控制响应过大"));
            }
          });
          response.on("end", () => {
            let data;
            try {
              data = responseBody ? JSON.parse(responseBody) : {};
            } catch {
              reject(new Error("控制响应格式错误"));
              return;
            }
            if ((response.statusCode || 500) >= 400) {
              reject(new Error(data.error || data.message || `HTTP ${response.statusCode}`));
            } else {
              resolve(data);
            }
          });
        });
        request.on("error", reject);
        request.on("timeout", () => request.destroy(new Error("控制请求超时")));
        if (payload) request.write(payload);
        request.end();
      } catch (error) {
        reject(error);
      }
    });
  }

  queueReport(apiPath, body, label, orderingKey = "global", prerequisite = Promise.resolve()) {
    const key = `${apiPath}:${orderingKey}`;
    const previous = this.reportTails.get(key) || Promise.resolve();
    const current = Promise.allSettled([previous, prerequisite])
      .then(() => this.request("POST", apiPath, body, 5_000))
      .catch((error) => this.logger(label, error?.message || error));
    this.reportTails.set(key, current);
    const cleanup = () => {
      if (this.reportTails.get(key) === current) this.reportTails.delete(key);
    };
    current.then(cleanup, cleanup);
    return current;
  }

  eventReportKey(event) {
    const conversation = event?.group_id || event?.target_id || event?.user_id
      || event?.peer_id || event?.notice_type || event?.post_type || "global";
    return `${event?.self_id || this.botId}:${conversation}`;
  }

  reportStatus(runtime) {
    this.statusTail = this.queueReport(
      "/api/embedded/events",
      { bot_id: this.botId, self_id: runtime.loginUin || this.botId, runtime },
      "[桥接] 状态上报失败:",
      "status",
    );
    return this.statusTail;
  }

  reportEvent(event) {
    return this.queueReport(
      "/api/embedded/events",
      { bot_id: this.botId, self_id: event.self_id || this.botId, event },
      "[桥接] 事件上报失败:",
      this.eventReportKey(event),
      this.statusTail,
    );
  }

  reportRedPacket(packet) {
    const selfId = this.instance?.getSelfUin() || this.botId;
    return this.queueReport(
      "/api/embedded/red-packets",
      { bot_id: this.botId, self_id: selfId, red_packet: packet },
      "[桥接] 红包上报失败:",
      `${selfId}:${packet?.group_id || packet?.user_id || "全局"}`,
      this.statusTail,
    );
  }

  async executeControlCommand(command) {
    const requestId = String(command?.request_id || "");
    if (!requestId) return;
    let result;
    try {
      if (!this.instance) throw new Error("QQ 实例未运行");
      if (command.type === "action") {
        const data = await this.instance.callOneBotAction(String(command.action || ""), command.params || {});
        result = { status: "ok", retcode: 0, data, message: "", wording: "" };
      } else if (command.type === "packet") {
        const data = await this.instance.sendNativePacket(command.packet || {});
        result = { status: "ok", retcode: 0, data, message: "", wording: "" };
      } else if (command.type === "resolve_uid") {
        const data = await this.instance.resolveUid(String(command.user_id || ""));
        result = { status: "ok", retcode: 0, data, message: "", wording: "" };
      } else if (command.type === "grab_red_packet") {
        const data = await this.instance.grabRedPacket({ bill_no: command.bill_no });
        result = { status: "ok", retcode: 0, data, message: "", wording: "" };
      } else if (command.type === "refresh_qr") {
        result = { success: true, data: this.instance.refreshQrCode() };
      } else {
        throw new Error("不支持的控制命令");
      }
    } catch (error) {
      result = controlFailure(error);
    }
    await this.request("POST", "/api/embedded/control/result", {
      bot_id: this.botId,
      request_id: requestId,
      result,
    }, 5_000);
  }

  async controlLoop() {
    while (this.running) {
      try {
        const command = await this.request(
          "GET",
          `/api/embedded/control/poll?bot_id=${encodeURIComponent(this.botId)}`,
          null,
          30_000,
        );
        if (command) await this.executeControlCommand(command);
      } catch {
        if (this.running) await new Promise((resolve) => setTimeout(resolve, 1_000));
      }
    }
  }
}
