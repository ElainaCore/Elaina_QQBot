function collectionValues(value) {
  if (Array.isArray(value)) return value;
  if (value instanceof Map) return Array.from(value.values());
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

function firstText(source, names) {
  if (!source || typeof source !== "object") return "";
  for (const name of names) {
    const value = source[name];
    if (value !== undefined && value !== null && String(value)) return String(value);
  }
  return "";
}

/** Normalize QQNT inline-keyboard elements for framework consumers. */
export function extractInlineKeyboardButtons(elements) {
  const result = [];
  const seen = new Set();
  for (const element of collectionValues(elements)) {
    const keyboard = element?.inlineKeyboardElement;
    if (!keyboard || typeof keyboard !== "object") continue;
    const botAppid = firstText(keyboard, ["botAppid", "bot_appid", "appid"]);
    const rows = collectionValues(keyboard.rows ?? keyboard.content?.rows);
    for (const row of rows) {
      for (const button of collectionValues(row?.buttons)) {
        if (!button || typeof button !== "object") continue;
        const buttonId = firstText(button, ["id", "buttonId", "button_id"]);
        const callbackData = firstText(button, ["data", "callbackData", "callback_data"]).trim()
          || firstText(button.action, ["data", "callbackData", "callback_data"]).trim();
        if (!callbackData) continue;
        const identity = `${botAppid}\u0000${buttonId}\u0000${callbackData}`;
        if (seen.has(identity)) continue;
        seen.add(identity);
        result.push({
          bot_appid: botAppid,
          button_id: buttonId || "1",
          callback_data: callbackData,
        });
      }
    }
  }
  return result;
}
