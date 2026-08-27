from __future__ import annotations

import base64
import json
import unittest

from core.runtime.embedded import packet


class EmbeddedPacketTests(unittest.TestCase):
    def oidb_response(self, body: bytes) -> bytes:
        return packet._varint_field(3, 0) + packet._bytes_field(4, body)

    def test_rkey_packet_and_response_match_napcat_shape(self) -> None:
        request = packet.build_rkey_packet()
        self.assertEqual(request.cmd, 'OidbSvcTrpcTcp.0x9067_202')

        private = b''.join((
            packet._string_field(1, 'rkey=private'),
            packet._varint_field(2, 3600),
            packet._varint_field(4, 1700000000),
            packet._varint_field(5, 10),
        ))
        group = b''.join((
            packet._string_field(1, 'rkey=group'),
            packet._varint_field(2, 3600),
            packet._varint_field(4, 1700000000),
            packet._varint_field(5, 20),
        ))
        body = packet._bytes_field(4, packet._bytes_field(1, private) + packet._bytes_field(1, group))

        self.assertEqual(packet.parse_rkey_response(self.oidb_response(body)), [
            {'rkey': 'rkey=private', 'ttl': 3600, 'time': 1700000000, 'type': 10},
            {'rkey': 'rkey=group', 'ttl': 3600, 'time': 1700000000, 'type': 20},
        ])

    def test_unidirectional_friend_response(self) -> None:
        payload = {
            'rpt_block_list': [{
                'uint64_uin': 12345,
                'str_uid': 'uid-value',
                'bytes_nick': base64.b64encode('昵称'.encode()).decode(),
                'uint32_age': 18,
                'bytes_source': base64.b64encode('来源'.encode()).decode(),
            }],
        }
        response = packet._string_field(4, json.dumps(payload, ensure_ascii=False))
        self.assertEqual(packet.parse_unidirectional_friend_response(response), [{
            'uin': 12345,
            'uid': 'uid-value',
            'nick_name': '昵称',
            'age': 18,
            'source': '来源',
        }])

    def test_ai_voice_index_and_download_url(self) -> None:
        index = b'voice-index'
        message = packet._bytes_field(1, packet._bytes_field(1, index))
        generated = self.oidb_response(packet._bytes_field(4, message))
        self.assertEqual(packet.parse_ai_voice_index(generated), index)

        download_info = packet._string_field(1, 'example.qq.com') + packet._string_field(2, '/voice.amr')
        download = b''.join((packet._string_field(1, '?rkey=value'), packet._bytes_field(3, download_info)))
        response = self.oidb_response(packet._bytes_field(3, download))
        self.assertEqual(
            packet.parse_group_ptt_url_response(response),
            'https://example.qq.com/voice.amr?rkey=value',
        )

    def test_packet_request_accepts_hex_and_rejects_invalid_data(self) -> None:
        request = packet.normalize_packet_request({'cmd': 'Test.Command', 'data': '0a 01 ff'})
        self.assertEqual(request.data, b'\x0a\x01\xff')
        with self.assertRaises(ValueError):
            packet.normalize_packet_request({'cmd': 'Test.Command', 'data': 'not-hex'})

    def test_oidb_response_rejects_server_error(self) -> None:
        response = packet._varint_field(3, 1001) + packet._string_field(5, 'permission denied')
        with self.assertRaisesRegex(ValueError, 'permission denied'):
            packet.parse_oidb_response(response)


if __name__ == '__main__':
    unittest.main()
