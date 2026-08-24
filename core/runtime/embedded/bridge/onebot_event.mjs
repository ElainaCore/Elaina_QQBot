function oneBotId(value) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : value;
}

function withoutUndefined(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

export function normalizeOneBotTimestamp(value, fallback = Math.floor(Date.now() / 1000)) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return Math.floor(Number(fallback));
  return Math.floor(numeric > 100_000_000_000 ? numeric / 1000 : numeric);
}

/** Build the wire-level event shape used by NapCat OneBot 11. */
export function createOneBotEvent(selfId, postType, fields = {}) {
  const { time, ...payload } = fields;
  return withoutUndefined({
    time: normalizeOneBotTimestamp(time),
    self_id: oneBotId(selfId),
    post_type: postType,
    ...payload,
  });
}

export function createLifecycleEvent(selfId, subType = "connect") {
  return createOneBotEvent(selfId, "meta_event", {
    meta_event_type: "lifecycle",
    sub_type: subType,
  });
}

export function createHeartbeatEvent(selfId, interval, online = true, good = true) {
  return createOneBotEvent(selfId, "meta_event", {
    meta_event_type: "heartbeat",
    status: { online, good },
    interval,
  });
}
