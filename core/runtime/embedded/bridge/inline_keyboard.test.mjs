import assert from "node:assert/strict";
import test from "node:test";

import { extractInlineKeyboardButtons } from "./inline_keyboard.mjs";

test("extracts QQNT inline keyboard callback data", () => {
  assert.deepEqual(extractInlineKeyboardButtons([{
    elementType: 17,
    inlineKeyboardElement: {
      botAppid: "102050728",
      rows: [{
        buttons: [{ id: "1", data: "BOT1.0_callback-token" }],
      }],
    },
  }]), [{
    bot_appid: "102050728",
    button_id: "1",
    callback_data: "BOT1.0_callback-token",
  }]);
});

test("accepts action data and object-backed QQNT collections", () => {
  const elements = {
    0: {
      inlineKeyboardElement: {
        bot_appid: 123,
        content: {
          rows: {
            0: {
              buttons: {
                0: {
                  buttonId: 7,
                  action: { callbackData: "BOT1.0_nested-token" },
                },
              },
            },
          },
        },
      },
    },
  };
  assert.deepEqual(extractInlineKeyboardButtons(elements), [{
    bot_appid: "123",
    button_id: "7",
    callback_data: "BOT1.0_nested-token",
  }]);
});
