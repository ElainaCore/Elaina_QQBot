from __future__ import annotations

import asyncio
import datetime
import gzip
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.foundation.config import Config
from core.plugins.manager import PluginManager
from core.plugins.web_pages import match_route
from core.runtime.application import _tune_gc
from core.runtime.embedded.manager import EmbeddedQQManager
from core.runtime.event_dispatcher import EventDispatcher
from core.runtime.extensions.hook import HookManager
from core.services.logs import LogService
from web.setup import _make_spa_handler


class LogServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_batch_queue_flush_and_retention(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = LogService(
                temp_dir,
                insert_interval=3600,
                retention_days=1,
                max_queue_entries=3,
                max_batch_size=2,
            )
            await service.start()
            try:
                self.assertTrue(service.add_nowait('framework', {'content': 'one'}))
                self.assertTrue(service.add_nowait('framework', {'content': 'two'}))
                self.assertTrue(service.add_nowait('framework', {'content': 'three'}))
                self.assertFalse(service.add_nowait('framework', {'content': 'overflow'}))
                self.assertEqual(service.stats, {'queued': 3, 'dropped': 1, 'limit': 3})

                rows = await service.query('framework', 'SELECT content FROM log ORDER BY id')
                self.assertEqual([row['content'] for row in rows], ['one', 'two', 'three'])
                self.assertEqual(service.stats['queued'], 0)

                old = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
                await service.add('framework', {'timestamp': old, 'content': 'old'}, durable=True)
                await service.cleanup()
                rows = await service.query('framework', "SELECT content FROM log WHERE content = 'old'")
                self.assertEqual(rows, [])
            finally:
                await service.shutdown()


class ConfigTests(unittest.TestCase):
    def test_invalid_reload_preserves_last_good_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, 'settings.yaml')
            path.write_text('owner:\n  ids: [123]\n', encoding='utf-8')
            config = Config()
            config.init(temp_dir)
            self.assertEqual(config.get('settings', 'owner.ids'), [123])

            path.write_text('- invalid-root\n', encoding='utf-8')
            self.assertFalse(config.reload('settings'))
            self.assertEqual(config.get('settings', 'owner.ids'), [123])


class HookTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_does_not_block_following_hook(self):
        manager = HookManager(default_timeout=0.01)
        calls = []

        async def slow():
            await asyncio.sleep(0.2)

        async def fast():
            calls.append('fast')

        manager.register('event', slow, owner='slow')
        manager.register('event', fast, owner='fast', priority=200)
        await asyncio.wait_for(manager.emit('event'), timeout=0.1)
        self.assertEqual(calls, ['fast'])


class EventDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_returns_after_enqueue_before_plugin_work_starts(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def processor(event):
            started.set()
            await release.wait()

        dispatcher = EventDispatcher(processor)
        self.assertTrue(await asyncio.wait_for(dispatcher.submit('conversation', object()), timeout=0.1))
        self.assertEqual(dispatcher.pending_count, 1)
        await asyncio.wait_for(started.wait(), timeout=0.1)
        release.set()
        await dispatcher.shutdown()


class EmbeddedControlQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_red_packet_command_uses_priority_queue_with_startup_fallback(self):
        manager = EmbeddedQQManager.__new__(EmbeddedQQManager)
        manager.bots = {
            'bot': SimpleNamespace(process=SimpleNamespace(returncode=None)),
        }
        manager._control_queues = {}
        manager._priority_control_queues = {}
        manager._priority_control_pollers = set()
        manager._control_futures = {}

        call = asyncio.create_task(
            manager._control_call(
                'bot',
                {'type': 'grab_red_packet', 'bill_no': 'bill'},
                timeout=0.5,
            )
        )
        await asyncio.sleep(0)
        self.assertTrue(manager._control_queue('bot').empty())
        command = await manager.next_control_command('bot', timeout=0.1)
        self.assertEqual(command['type'], 'grab_red_packet')
        self.assertTrue(
            manager.resolve_control_command(
                'bot',
                {
                    'request_id': command['request_id'],
                    'result': {'status': 'ok', 'data': {'ok': True}},
                },
            )
        )
        self.assertEqual((await call)['data'], {'ok': True})


class PluginReloadTests(unittest.IsolatedAsyncioTestCase):
    def _plugin_source(self, version: int) -> str:
        return f'''from core.plugins import handler, register_route

VERSION = {version}

@handler(r"^v{version}$")
async def command(event, match):
    return None

@register_route("GET", "/api/ext/demo")
async def route(request):
    return None
'''

    async def test_reload_commits_success_and_rolls_back_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir, 'plugins')
            plugin_dir = plugins_dir / 'demo'
            plugin_dir.mkdir(parents=True)
            entry = plugin_dir / 'main.py'
            helper = plugin_dir / '_helper.py'
            entry.write_text(self._plugin_source(1), encoding='utf-8')
            helper.write_text('VALUE = 1\n', encoding='utf-8')

            manager = PluginManager(str(plugins_dir))
            await manager.load('demo')
            try:
                original_plugin = manager.plugins['demo']
                original_route = match_route('GET', '/api/ext/demo')
                self.assertEqual(original_plugin.module.VERSION, 1)

                entry.write_text('this is invalid python', encoding='utf-8')
                with self.assertRaises(RuntimeError):
                    await manager.reload('demo')
                self.assertIs(manager.plugins['demo'], original_plugin)
                self.assertIs(match_route('GET', '/api/ext/demo')['handler'], original_route['handler'])

                entry.write_text(self._plugin_source(2), encoding='utf-8')
                await manager.reload('demo')
                self.assertEqual(manager.plugins['demo'].module.VERSION, 2)
                self.assertIsNot(match_route('GET', '/api/ext/demo')['handler'], original_route['handler'])

                manager._snapshot_all_mtimes()
                helper_path = str(helper)
                self.assertIn(helper_path, manager._file_mtimes)
                old_stat = helper.stat()
                helper.write_text('VALUE = 2\n', encoding='utf-8')
                os.utime(helper, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000))
                self.assertIn('demo', manager._detect_changed_plugins())
            finally:
                await manager.shutdown()


class StaticAssetTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_version_changes_when_lazy_asset_changes(self):
        class Request:
            def __init__(self):
                self.match_info = {'path': 'index.html'}
                self.headers = {'Accept-Encoding': 'gzip'}
                self.query = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            assets = root / 'assets'
            assets.mkdir()
            index = root / 'index.html'
            main = assets / 'main.js'
            lazy = assets / 'lazy.js'
            index.write_text('<script src="assets/main.js"></script>', encoding='utf-8')
            main.write_text('import "./lazy.js"', encoding='utf-8')
            lazy.write_text('export const value = 1', encoding='utf-8')
            handler = _make_spa_handler(temp_dir)

            first = gzip.decompress((await handler(Request())).body)
            old_stat = lazy.stat()
            lazy.write_text('export const value = 2', encoding='utf-8')
            os.utime(lazy, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000))
            second = gzip.decompress((await handler(Request())).body)

            self.assertNotEqual(first, second)
            self.assertIn(b'assets/main.js?v=', second)


class GCTests(unittest.TestCase):
    def test_gc_tuning_keeps_reloadable_objects_collectable(self):
        import gc

        _tune_gc()
        self.assertEqual(gc.get_threshold(), (700, 10, 10))


if __name__ == '__main__':
    unittest.main()
