const ACTION_ENV = "ELAINAQQ_ONEBOT_ACTIONS";

function loadActions() {
  const encoded = String(process.env[ACTION_ENV] || "[]");
  try {
    const actions = JSON.parse(encoded);
    return new Set(Array.isArray(actions) ? actions.map(String) : []);
  } catch {
    return new Set();
  }
}

export const ONEBOT_ACTIONS = loadActions();

export class OneBotActionError extends Error {
  constructor(message, retcode = 1404, action = "") {
    super(message);
    this.name = "OneBotActionError";
    this.retcode = retcode;
    this.action = action;
  }
}

export function normalizeOneBotAction(action) {
  return String(action || "").replace(/_(?:async|rate_limited)$/i, "");
}

export function assertKnownOneBotAction(action) {
  if (!ONEBOT_ACTIONS.has(action)) {
    throw new OneBotActionError(`未知的 OneBot action: ${action || "<empty>"}`, 1404, action);
  }
}

export function requireNativeMethod(service, method, action) {
  if (!service || typeof service[method] !== "function") {
    throw new OneBotActionError(`当前 QQ 版本不支持 ${action}`, 1405, action);
  }
  return service[method].bind(service);
}

export function checkNativeResult(result, fallback) {
  const nested = result?.result && typeof result.result === "object" ? result.result : null;
  const rawCode = [
    result?.result,
    result?.retcode,
    result?.retCode,
    result?.code,
    result?.errCode,
    nested?.retcode,
    nested?.retCode,
    nested?.code,
    nested?.errCode,
  ].find((value) => ["number", "string", "bigint"].includes(typeof value));
  const code = Number(rawCode ?? 0);
  if (Number.isFinite(code) && code !== 0) {
    throw new OneBotActionError(
      String(
        result?.errMsg || result?.retMsg || result?.message || result?.clientWording ||
        nested?.errMsg || nested?.retMsg || nested?.message || nested?.clientWording ||
        fallback || `QQ 原生调用失败 (${code})`
      ),
      code,
    );
  }
  return result;
}
