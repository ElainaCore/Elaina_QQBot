from __future__ import annotations

import asyncio
import unittest

from core.protocols.onebot.adapter import OneBotAdapter
from core.protocols.onebot.api import OneBotAPI
from core.protocols.onebot.contract import Channel
from core.protocols.onebot.event import MessageEvent, NoticeEvent, parse_event
from core.protocols.onebot.message import normalize_message
from core.protocols.onebot.protocol import normalize_action_response
from core.runtime.event_dispatcher import EventDispatcher
from core.runtime.event_pipeline import EventPipeline
from core.runtime.qlinux.runner import runner_event_to_onebot


class EventContractTests(unittest.TestCase):
    def test_aliases_are_locked_to_canonical_fields(self) -> None:
        event = parse_event({
            'postType': 'message',
            'selfId': '10001',
            'messageType': 'group',
            'messageId': '42',
            'userId': '20002',
            'groupId': '30003',
            'message': 'hello',
            'sender': {'uin': '20002', 'name': 'tester', 'permission': 'admin'},
        })

        self.assertIsInstance(event, MessageEvent)
        assert isinstance(event, MessageEvent)
        self.assertEqual(event.self_id, '10001')
        self.assertEqual(event.group_id, 30003)
        self.assertEqual(event.message_id, 42)
        self.assertEqual(event.sender_nickname, 'tester')
        self.assertEqual(event.member_role, 'admin')
        self.assertNotIn('postType', event.raw_data)
        self.assertNotIn('postType', event.extra)

    def test_unknown_message_segments_are_preserved(self) -> None:
        message = normalize_message([
            {'type': 'video', 'data': {'file': 'video.mp4'}},
            {'type': 'markdown', 'data': {'content': '# title'}},
            {'type': 'custom', 'data': 'payload'},
        ])

        self.assertEqual([item['type'] for item in message], ['video', 'markdown', 'custom'])
        self.assertEqual(message[2]['data'], {'data': 'payload'})

    def test_lagrange_notice_uses_same_event_model(self) -> None:
        payload = runner_event_to_onebot({
            'event': 'notice.group_recall',
            'bot_id': 'bot-1',
            'uin': '10001',
            'data': {'group_id': 30003, 'user_id': 20002, 'message_id': 42},
        })

        event = parse_event(payload or {})
        self.assertIsInstance(event, NoticeEvent)
        assert isinstance(event, NoticeEvent)
        self.assertEqual(event.notice_type, 'group_recall')
        self.assertEqual(event.group_id, 30003)

    def test_lagrange_message_extensions_keep_all_segments(self) -> None:
        payload = runner_event_to_onebot({
            'event': 'message.received',
            'bot_id': 'bot-1',
            'uin': '10001',
            'data': {
                'sequence': 43,
                'contact': {'uin': 20002},
                'entities': [
                    {'type': 'text', 'text': 'hello'},
                    {'type': 'file', 'file_id': 'f-1', 'name': 'a.txt'},
                ],
            },
        })

        event = parse_event(payload or {})
        self.assertIsInstance(event, MessageEvent)
        assert isinstance(event, MessageEvent)
        self.assertEqual([segment['type'] for segment in event.message], ['text', 'file'])


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatcher_cancellation_releases_pending_events(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def process(_event) -> None:
            started.set()
            await release.wait()

        dispatcher = EventDispatcher(process, max_concurrency=1, max_pending=8)
        await dispatcher.submit('session', object())
        await dispatcher.submit('session', object())
        await started.wait()
        worker = dispatcher._workers['session']
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        self.assertEqual(dispatcher.pending_count, 0)
        self.assertEqual(dispatcher._queues, {})

    async def test_four_channels_share_one_deduplicated_pipeline(self) -> None:
        received = []

        async def process(event) -> None:
            received.append(event)

        dispatcher = EventDispatcher(process, max_concurrency=4, max_pending=32)
        pipeline = EventPipeline(OneBotAdapter(), dispatcher)
        payload = {
            'time': 1,
            'self_id': 10001,
            'post_type': 'message',
            'message_type': 'private',
            'message_id': 42,
            'user_id': 20002,
            'message': [{'type': 'text', 'data': {'text': 'hello'}}],
        }

        for source in Channel:
            self.assertTrue(await pipeline.ingest(payload, source=source))
        await pipeline.shutdown()

        self.assertEqual(len(received), 1)
        self.assertEqual(pipeline.stats['duplicates'], 3)
        self.assertEqual(received[0].source, Channel.EMBEDDED)

    async def test_local_channel_response_is_standardized(self) -> None:
        adapter = OneBotAdapter()

        async def action(_name: str, _params: dict) -> dict:
            return {'message_id': 7}

        adapter.register_local_bot('10001', action, channel=Channel.LAGRANGE)
        response = await adapter.call_local_action('send_private_msg', {}, '10001')

        self.assertEqual(response['status'], 'ok')
        self.assertEqual(response['retcode'], 0)
        self.assertEqual(response['data'], {'message_id': 7})
        self.assertEqual(adapter.local_channels['10001'], Channel.LAGRANGE)

    async def test_local_raw_error_is_not_reported_as_success(self) -> None:
        adapter = OneBotAdapter()

        async def action(_name: str, _params: dict) -> dict:
            return {'error': 'unsupported segment'}

        adapter.register_local_bot('10001', action, channel=Channel.INJECTED)
        response = await adapter.call_local_action('send_group_msg', {}, '10001')

        self.assertEqual(response['status'], 'failed')
        self.assertEqual(response['message'], 'unsupported segment')

    async def test_nested_native_error_is_reported_as_failure(self) -> None:
        response = normalize_action_response({'status': 'ok', 'data': {'error': 'native failed'}})
        self.assertEqual(response['status'], 'failed')
        self.assertEqual(response['message'], 'native failed')

    async def test_http_client_does_not_fallback_to_other_account(self) -> None:
        adapter = OneBotAdapter()
        adapter.register_http_client('bot-a', 'http://127.0.0.1:5801', self_id='10001')
        self.assertIsNone(adapter._select_http_client('10002'))

    async def test_ambiguous_routes_require_explicit_self_id(self) -> None:
        adapter = OneBotAdapter()

        async def action(_name: str, _params: dict) -> dict:
            return {'ok': True}

        adapter.register_local_bot('10001', action)
        adapter.register_http_client('bot-b', 'http://127.0.0.1:5802', self_id='10002')
        response = await OneBotAPI(adapter).call_api('get_status')
        self.assertEqual(response['status'], 'failed')
        self.assertEqual(response['retcode'], 1400)


if __name__ == '__main__':
    unittest.main()
