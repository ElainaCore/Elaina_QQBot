from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.runtime.qlinux.manager import QLinuxManager


class _App:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    async def ingest_event(self, payload: dict, **kwargs):
        del payload, kwargs
        return True


class _RPC:
    def __init__(self, manager: QLinuxManager | None = None):
        self.alive = True
        self.calls: list[tuple[str, dict]] = []
        self.stopped = False
        self.manager = manager

    async def call(self, method: str, params: dict, timeout: float = 60):
        del timeout
        self.calls.append((method, params))
        if method == 'bot.stop' and self.manager is not None:
            self.manager._on_runner_event({
                'event': 'bot.offline',
                'bot_id': params['bot_id'],
            })
        return {'started': True} if method.startswith('bot.login.') else {'stopped': True}

    async def stop(self):
        self.stopped = True
        self.alive = False


class QLinuxRestartTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = QLinuxManager(_App(Path(self.temp_dir.name)))

    def tearDown(self):
        self.temp_dir.cleanup()

    async def test_shutdown_logs_out_and_preserves_only_online_resume_intent(self):
        self.manager._accounts = {
            'online': {'bot_id': 'online', 'status': 'online'},
            'stopped': {'bot_id': 'stopped', 'status': 'stopped'},
        }
        rpc = _RPC(self.manager)
        self.manager._rpc = rpc

        await self.manager.shutdown()

        self.assertEqual(
            {('bot.stop', 'online'), ('bot.stop', 'stopped')},
            {(method, params['bot_id']) for method, params in rpc.calls},
        )
        self.assertEqual('resume_pending', self.manager._accounts['online']['status'])
        self.assertEqual('stopped', self.manager._accounts['stopped']['status'])
        self.assertTrue(rpc.stopped)
        self.assertIsNone(self.manager._rpc)

    async def test_duplicate_login_is_rejected_until_current_login_finishes(self):
        self.manager._accounts = {
            'bot': {'bot_id': 'bot', 'status': 'online'},
        }
        rpc = _RPC()
        self.manager._rpc = rpc

        first = await self.manager.login_qr('bot')
        second = await self.manager.login_qr('bot')

        self.assertTrue(first['started'])
        self.assertEqual({'started': False, 'already_running': True}, second)
        self.assertEqual(1, len(rpc.calls))

        self.manager._on_runner_event({
            'event': 'login.completed',
            'bot_id': 'bot',
            'success': False,
            'error': 'expired',
        })
        await self.manager.login_qr('bot')
        self.assertEqual(2, len(rpc.calls))

    async def test_create_account_uses_fixed_linux_runner_contract(self):
        rpc = _RPC()
        self.manager._rpc = rpc

        account = await self.manager.create_account('bot')

        self.assertEqual(('bot.create', {'bot_id': 'bot'}), rpc.calls[0])
        self.assertNotIn('protocol', account)

    def test_qr_event_marks_failed_resume_as_waiting_for_scan(self):
        self.manager._accounts = {
            'bot': {'bot_id': 'bot', 'status': 'login_failed'},
        }

        self.manager._on_runner_event({
            'event': 'qr.code',
            'bot_id': 'bot',
            'png_base64': 'png',
            'url': 'https://example.test/qr',
        })

        self.assertEqual('waiting_scan', self.manager._accounts['bot']['status'])
        self.assertEqual('png', self.manager.get_qr_image('bot')['png_base64'])


if __name__ == '__main__':
    unittest.main()
