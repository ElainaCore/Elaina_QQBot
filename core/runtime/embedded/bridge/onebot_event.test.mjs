import assert from "node:assert/strict";
import test from "node:test";

import { createOneBotEvent, normalizeOneBotTimestamp } from "./onebot_event.mjs";

test("normalizes OneBot event timestamps to seconds", () => {
  assert.equal(normalizeOneBotTimestamp(1_787_608_205), 1_787_608_205);
  assert.equal(normalizeOneBotTimestamp(1_787_608_205_123), 1_787_608_205);
  assert.equal(createOneBotEvent(1, "message", { time: 1_787_608_205_123 }).time, 1_787_608_205);
});
