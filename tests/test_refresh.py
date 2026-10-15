import dataclasses
import importlib.util
import json
from pathlib import Path

from roblox_presence.config import ConfigError
from roblox_presence.http import Response
from roblox_presence.session import Session
from tests.test_monitor import Fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('refresh', ROOT / 'deploy/refresh_cookie.py')
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class RefreshTests(Fixture):
    def setUp(self):
        super().setUp()
        self.system = self.root / 'system'
        self.etc = self.system / 'etc/roblox-presence'
        self.etc.mkdir(parents=True, mode=0o700)
        obj = json.loads((ROOT / 'config.example.json').read_text())
        obj.update(observer_user_id=11, target_user_id=22)
        (self.etc / 'config.json').write_text(json.dumps(obj))
        self.target = self.etc / 'roblox_cookie'
        self.target.write_text('OLD_INSTALLED_SESSION')
        self.target.chmod(0o600)

    def test_refresh_copies_current_rotated_value_without_touching_state(self):
        session = Session(self.config); session.value()
        session.update(Response(200, {}, b'{}', ('.ROBLOSECURITY=CURRENT_ROTATED_SESSION; Domain=.roblox.com',)))
        sentinel = self.config.state_dir / 'state.sqlite3'
        sentinel.write_bytes(b'preserve durable transitions')
        refresh.refresh(self.config, self.system, apply=True)
        self.assertEqual(self.target.read_text(), 'CURRENT_ROTATED_SESSION\n')
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(sentinel.read_bytes(), b'preserve durable transitions')

    def test_dry_run_does_not_need_source_cookie_or_overwrite_destination(self):
        self.cookie.unlink()
        refresh.refresh(self.config, self.system)
        self.assertEqual(self.target.read_text(), 'OLD_INSTALLED_SESSION')

    def test_different_installation_cannot_be_overwritten(self):
        with self.assertRaises(ConfigError):
            refresh.refresh(dataclasses.replace(self.config, observer_user_id=33), self.system, apply=True)
        self.assertEqual(self.target.read_text(), 'OLD_INSTALLED_SESSION')

    def test_symlink_and_group_readable_destination_are_refused(self):
        self.target.chmod(0o640)
        with self.assertRaises(ConfigError):
            refresh.refresh(self.config, self.system, apply=True)
        self.target.unlink(); self.target.symlink_to(self.cookie)
        with self.assertRaises(ConfigError):
            refresh.refresh(self.config, self.system, apply=True)
        self.assertEqual(self.cookie.read_text(), 'TEST_OBSERVER_SESSION')
