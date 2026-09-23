from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.runtime.embedded.manager import EmbeddedQQManager
from core.runtime.qlinux.manager import QLinuxManager
from core.runtime.qq.launcher import QQLauncher
from web.tools.qq_versions import _run_job


class LinuxQQRuntimeTests(unittest.TestCase):
    def _launcher(self, root: Path) -> QQLauncher:
        executable = root / 'QQ' / 'qq'
        executable.parent.mkdir(parents=True)
        executable.write_text('#!/bin/sh\n', encoding='utf-8')
        app_dir = executable.parent / 'resources' / 'app'
        app_dir.mkdir(parents=True)
        (app_dir / 'package.json').write_text(json.dumps({'main': 'index.js'}), encoding='utf-8')
        (app_dir / 'index.js').write_text('', encoding='utf-8')
        return QQLauncher(executable, root / 'qq_runtime.mjs')

    def test_wayland_launch_does_not_require_xvfb(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = self._launcher(root)
            with patch('core.runtime.qq.launcher.sys.platform', 'linux'), patch.dict(
                os.environ,
                {'WAYLAND_DISPLAY': 'wayland-0', 'XDG_RUNTIME_DIR': '/run/user/1000'},
                clear=True,
            ):
                command = launcher.command(root / 'account')

            self.assertIn('--ozone-platform=wayland', command)
            self.assertEqual(launcher.launch_env['ELAINAQQ_HEADLESS_RUNTIME'], 'wayland')
            self.assertEqual(launcher.launch_env['WAYLAND_DISPLAY'], '/run/user/1000/wayland-0')

    def test_read_only_install_can_be_copied_to_writable_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = self._launcher(root)
            with patch('core.runtime.qq.launcher.sys.platform', 'linux'):
                source_app_dir = launcher.app_dir()
                source_app_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
                (source_app_dir / 'package.json').chmod(stat.S_IRUSR)
                writable = launcher.writable_runtime(root / 'runtime', force_copy=True)

            self.assertNotEqual(writable.executable, launcher.executable)
            self.assertTrue(writable.executable.is_file())
            with patch('core.runtime.qq.launcher.sys.platform', 'linux'):
                copied_app_dir = writable.app_dir()
                copied_package = copied_app_dir / 'package.json'
                self.assertTrue(copied_package.is_file())
                self.assertTrue(copied_app_dir.stat().st_mode & stat.S_IWUSR)
                self.assertTrue(copied_package.stat().st_mode & stat.S_IWUSR)
                writable.install_loader()
                self.assertTrue((writable.app_dir() / 'elainaqq-loader.cjs').is_file())

    def test_managed_linux_executable_gets_user_execute_permission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / 'opt' / 'QQ' / 'qq'
            executable.parent.mkdir(parents=True)
            executable.write_text('#!/bin/sh\n', encoding='utf-8')
            executable.chmod(stat.S_IRUSR | stat.S_IWUSR)
            from core.runtime.qq.distribution import QQManager

            manager = QQManager.__new__(QQManager)
            with patch('core.runtime.qq.distribution.os.access', return_value=False), patch.object(Path, 'chmod') as chmod:
                found = manager._find_managed_qq(root)

            self.assertEqual(found, executable.resolve())
            chmod.assert_called_once_with(executable.stat().st_mode | stat.S_IXUSR)


class LinuxDisplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_display_is_reused_without_xvfb(self):
        manager = EmbeddedQQManager.__new__(EmbeddedQQManager)
        manager._xvfb_lock = asyncio.Lock()
        manager._xvfb_process = None
        manager._xvfb_display = ''
        with patch('core.runtime.embedded.manager.sys.platform', 'linux'), patch.dict(
            os.environ,
            {'DISPLAY': ':42'},
            clear=True,
        ), patch('core.runtime.embedded.manager.shutil.which', return_value=None):
            display = await manager._ensure_xvfb()

        self.assertEqual(display, ':42')


class QLinuxBindingTests(unittest.IsolatedAsyncioTestCase):
    class Adapter:
        def __init__(self):
            self.local_actions = {}
            self.local_channels = {}
            self.identity_aliases = {}

        def register_local_bot(self, self_id, action, *, channel):
            self.local_actions[str(self_id)] = action
            self.local_channels[str(self_id)] = str(channel)

        def register_identity_alias(self, alias, self_id):
            self.identity_aliases[str(alias)] = str(self_id)

    class App:
        def __init__(self, adapter):
            self.adapter = adapter

        async def ingest_event(self, *_args, **_kwargs):
            return True

    def _manager(self):
        adapter = self.Adapter()
        manager = QLinuxManager.__new__(QLinuxManager)
        manager._app = self.App(adapter)
        manager._accounts = {
            'linux-account': {
                'bot_id': 'linux-account',
                'uin': '',
                'status': 'connecting',
            },
        }
        manager._registered_uins = set()
        manager._login_active = {'linux-account'}
        manager._shutting_down = False
        manager._save_accounts = lambda: None
        manager.handle_action = AsyncMock(return_value={
            'status': 'ok', 'retcode': 0,
            'data': [{'user_id': 10001}], 'message': '', 'wording': '',
        })
        return manager, adapter

    async def test_login_completed_binds_route_before_first_plugin_call(self):
        manager, adapter = self._manager()

        manager._on_runner_event({
            'event': 'login.completed',
            'bot_id': 'linux-account',
            'success': True,
            'uin': '123456789',
        })

        self.assertIn('123456789', adapter.local_actions)
        self.assertEqual(adapter.identity_aliases['linux-account'], '123456789')
        self.assertEqual(manager._accounts['linux-account']['status'], 'online')
        response = await adapter.local_actions['123456789'](
            'get_group_member_list', {'group_id': 538242141, 'no_cache': True}
        )
        self.assertEqual(response['retcode'], 0)
        manager.handle_action.assert_awaited_once_with(
            'linux-account',
            'get_group_member_list',
            {'group_id': 538242141, 'no_cache': True},
        )

    async def test_stale_registration_marker_does_not_hide_missing_handler(self):
        manager, adapter = self._manager()
        manager._accounts['linux-account']['uin'] = '123456789'
        manager._registered_uins.add('123456789')

        self.assertTrue(manager._register_account('linux-account'))
        self.assertIn('123456789', adapter.local_actions)


class InstallJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_installer_package_is_not_reported_as_installed_qq(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / 'qq.deb'
            package.touch()

            class Manager:
                installed_versions = {
                    'linux_x64_deb': {
                        'status': 'install_requires_privilege',
                        'manual_command': 'sudo dpkg -i qq.deb',
                    }
                }

                async def install_qq(self, *_args, **_kwargs):
                    return package

                def get_qq_executable(self, _version_key):
                    return None

            job: dict = {}
            await _run_job(job, Manager(), 'install', 'linux_x64_deb')

        self.assertEqual(job['state'], 'manual')
        self.assertIn('sudo dpkg -i qq.deb', job['manual_command'])
        self.assertFalse(job['success'])


if __name__ == '__main__':
    unittest.main()
