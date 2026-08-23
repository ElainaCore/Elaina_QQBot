import asyncio
import re
import socket
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import web.api as panel_api
from core.embedded_qq import EmbeddedBot, EmbeddedQQManager
from core.onebot.api import (
    OneBotAPI,
    api_call_source,
    bypass_api_interceptors,
    set_api_interceptors,
)
from core.onebot.event import MessageEvent
from core.plugin.manager import PluginManager


class FakeAdapter:
    def __init__(self):
        self.local_actions = {'10001': object()}
        self.calls = []
        self.api_responses = {}
        self.http_clients = {}

    async def call_local_action(self, action, params, self_id):
        self.calls.append((action, dict(params), self_id))
        return {'status': 'ok', 'data': {'action': action, 'params': dict(params)}}

    def get_bot_ws(self, _self_id):
        return None


class ApiInterceptorTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        set_api_interceptors([])

    async def test_middleware_can_mutate_and_observe_source(self):
        adapter = FakeAdapter()
        seen = {}

        async def middleware(request, call_next):
            seen['source'] = request.source_plugin
            seen['context'] = request.context
            seen['local'] = request.local
            request.params['message'] += ' suffix'
            return await call_next()

        set_api_interceptors(
            [
                {
                    'func': middleware,
                    'priority': 100,
                    '_plugin': 'hook',
                    '_allowed_bots': None,
                }
            ]
        )
        event = type(
            'Event',
            (),
            {
                'self_id': '10001',
                'user_id': '20002',
                'group_id': '30003',
                'message_type': 'group',
                'post_type': 'message',
            },
        )()
        with api_call_source('example', event):
            result = await OneBotAPI(adapter).call_api(
                'send_group_msg',
                {'group_id': '30003', 'message': 'hello'},
                self_id='10001',
            )

        self.assertEqual(seen['source'], 'example')
        self.assertEqual(seen['context']['group_id'], '30003')
        self.assertTrue(seen['local'])
        self.assertEqual(adapter.calls[0][1]['message'], 'hello suffix')
        self.assertEqual(result['status'], 'ok')

    async def test_takeover_and_bypass(self):
        adapter = FakeAdapter()

        async def middleware(_request, _call_next):
            return {'status': 'ok', 'data': {'message_id': -1}}

        set_api_interceptors(
            [
                {
                    'func': middleware,
                    'priority': 100,
                    '_plugin': 'hook',
                    '_allowed_bots': None,
                }
            ]
        )
        api = OneBotAPI(adapter)
        result = await api.call_api('send_group_msg', {'message': 'owned'}, self_id='10001')
        self.assertEqual(result['data']['message_id'], -1)
        self.assertEqual(adapter.calls, [])

        with bypass_api_interceptors():
            await api.call_api('send_group_msg', {'message': 'raw'}, self_id='10001')
        self.assertEqual(adapter.calls[0][1]['message'], 'raw')


class HandlerFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_filter_skips_only_the_target_plugin(self):
        called = []

        async def handler_a(_event, _match):
            called.append('a')

        async def handler_b(_event, _match):
            called.append('b')

        async def filter_a(_event, target_plugin):
            return target_plugin == 'plugin_a'

        def entry(name, func):
            return {
                'func': func,
                'is_coro': True,
                'pattern': r'.*',
                'compiled': re.compile(r'.*'),
                'name': name,
                'desc': '',
                'priority': 0,
                'owner_only': False,
                'group_only': False,
                'private_only': False,
                'event_types': None,
                'cooldown': 0,
                'block': False,
                '_plugin': name,
                '_allowed_bots': None,
            }

        with tempfile.TemporaryDirectory() as directory:
            manager = PluginManager(directory)
            manager._all_handlers = [
                entry('plugin_a', handler_a),
                entry('plugin_b', handler_b),
            ]
            manager._all_interceptors = []
            manager._all_handler_filters = [
                {
                    'func': filter_a,
                    'is_coro': True,
                    'priority': 100,
                    '_plugin': 'policy',
                    '_allowed_bots': None,
                }
            ]
            manager._build_dispatch_index()
            event = MessageEvent(
                {
                    'post_type': 'message',
                    'message_type': 'group',
                    'self_id': '10001',
                    'user_id': '20002',
                    'group_id': '30003',
                    'message': [{'type': 'text', 'data': {'text': 'hello'}}],
                }
            )
            await manager.dispatch(event)

        self.assertEqual(called, ['b'])


class EmbeddedQQStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_online_status_updates_real_qq_nickname(self):
        class Adapter:
            def unregister_local_bot(self, _bot_id):
                return None

            def register_local_bot(self, bot_id, action):
                self.bot_id = bot_id
                self.action = action

        manager = object.__new__(EmbeddedQQManager)
        manager.app = SimpleNamespace(adapter=Adapter(), submit_event=lambda _event: None)
        manager.bots = {'1231': EmbeddedBot(bot_id='1231', nickname='1231')}
        manager._save_accounts = lambda: None

        handled = await manager.handle_event(
            {
                'bot_id': '1231',
                'runtime': {
                    'status': 'online',
                    'loginUin': '76200874',
                    'nickname': '测试昵称',
                },
            }
        )

        self.assertTrue(handled)
        self.assertEqual(manager.bots['1231'].uin, '76200874')
        self.assertEqual(manager.bots['1231'].nickname, '测试昵称')
        self.assertEqual(manager.app.adapter.bot_id, '76200874')


class EmbeddedQQPortTests(unittest.TestCase):
    def test_bridge_ports_start_at_30010_and_remain_unique(self):
        manager = object.__new__(EmbeddedQQManager)
        first = EmbeddedBot(bot_id='first')
        second = EmbeddedBot(bot_id='second')
        manager.bots = {'first': first, 'second': second}

        def config_value(_name, path, default=None):
            return 30010 if path == 'embedded_qq.bridge_port_start' else default

        with patch('core.embedded_qq.cfg.get', side_effect=config_value):
            self.assertEqual(manager._assign_bridge_port(first), 30010)
            self.assertEqual(manager._assign_bridge_port(second), 30011)
            self.assertEqual(manager._assign_bridge_port(first), 30010)

    def test_duplicate_persisted_port_is_reassigned(self):
        manager = object.__new__(EmbeddedQQManager)
        first = EmbeddedBot(bot_id='first', bridge_port=30010)
        second = EmbeddedBot(bot_id='second', bridge_port=30010)
        manager.bots = {'first': first, 'second': second}

        def config_value(_name, path, default=None):
            return 30010 if path == 'embedded_qq.bridge_port_start' else default

        with patch('core.embedded_qq.cfg.get', side_effect=config_value):
            self.assertEqual(manager._assign_bridge_port(second), 30011)


class EmbeddedQQBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_start_port_is_skipped_and_listener_is_released(self):
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            occupied.bind(('127.0.0.1', 30010))
            occupied.listen(1)
        except OSError:
            occupied.close()
            self.skipTest('本机端口 30010 已被其他进程占用')

        manager = object.__new__(EmbeddedQQManager)
        bot = EmbeddedBot(bot_id='probe')
        manager.bots = {'probe': bot}
        manager._bridge_runners = {}
        manager._save_accounts = lambda: None

        def config_value(_name, path, default=None):
            return 30010 if path == 'embedded_qq.bridge_port_start' else default

        try:
            with patch('core.embedded_qq.cfg.get', side_effect=config_value):
                await manager._start_bridge(bot)
            self.assertEqual(bot.bridge_port, 30011)

            _reader, writer = await asyncio.open_connection('127.0.0.1', 30011)
            writer.close()
            await writer.wait_closed()

            await manager._stop_bridge(bot.bot_id)
            with self.assertRaises((OSError, asyncio.TimeoutError)):
                await asyncio.wait_for(
                    asyncio.open_connection('127.0.0.1', 30011),
                    timeout=1,
                )
        finally:
            await manager._stop_bridge(bot.bot_id)
            occupied.close()


class ExtRouteCompatibilityTests(unittest.TestCase):
    def test_falls_back_when_authorize_request_is_unavailable(self):
        request = SimpleNamespace(method='GET')
        with (
            patch.object(panel_api.auth, 'authorize_request', None),
            patch.object(panel_api.auth, 'validate_token', return_value=False),
        ):
            denied = panel_api._authorize_ext_request(request)

        self.assertEqual(denied.status, 401)

    def test_fallback_allows_valid_legacy_session(self):
        request = SimpleNamespace(method='GET')
        with (
            patch.object(panel_api.auth, 'authorize_request', None),
            patch.object(panel_api.auth, 'validate_token', return_value=True),
        ):
            denied = panel_api._authorize_ext_request(request)

        self.assertIsNone(denied)


if __name__ == '__main__':
    unittest.main()
