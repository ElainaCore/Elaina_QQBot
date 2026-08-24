import unittest

from core.protocols.onebot.inline_keyboard import (
    build_group_message_request,
    extract_inline_keyboard_buttons,
)


def _varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _field(tag: int, value: bytes) -> bytes:
    return _varint((tag << 3) | 2) + _varint(len(value)) + value


class InlineKeyboardTest(unittest.TestCase):
    def test_napcat_group_message_request(self):
        self.assertEqual(
            build_group_message_request(963830602, 483925),
            '0a0e08cac6cbcb0310d5c41d18d5c41d1001',
        )

    def test_extract_callback_from_wrapped_packet_response(self):
        callback = b'BOT1.0_callback-token'
        action = _field(5, callback)
        button = _field(1, b'1') + _field(3, action)
        response = _field(9, _field(4, button)).hex()
        self.assertEqual(
            extract_inline_keyboard_buttons(
                {'status': 'ok', 'retcode': 0, 'data': response},
                bot_appid='102050728',
            ),
            [{
                'bot_appid': '102050728',
                'button_id': '1',
                'callback_data': 'BOT1.0_callback-token',
            }],
        )


if __name__ == '__main__':
    unittest.main()
