function oneBotId(value) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : value;
}

function withoutUndefined(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

/** Build the wire-level event shape used by NapCat OneBot 11. */
export function createOneBotEvent(selfId, postType, fields = {}) {
  const { time, ...payload } = fields;
  return withoutUndefined({
    time: time ?? Math.floor(Date.now() / 1000),
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
