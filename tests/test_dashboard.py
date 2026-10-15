"""Synthetic dashboard tests: no account login, live notifications or private data."""

import contextlib
import dataclasses
import http.client
import io
import json
import os
import socket
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

from roblox_presence.__main__ import main
from roblox_presence.config import ConfigError, load
from roblox_presence.dashboard import DashboardServer, stop
from roblox_presence.dashboard_client import generate, load_client, request, state, validate_url
from roblox_presence.report import server_zone, stamp
from tests.test_monitor import Fixture
from tests import test_deployment as deployment
import dashboard_setup as setup


class DashboardTests(Fixture):
    def setUp(self):
        super().setUp()
        self.now = time.time()
        self.db().observe(False, self.now - 120)
        self.state.observe(True, self.now - 90, details={'username': 'ExampleConnection'})
        self.state.observe(False, self.now - 30)
        self.state.observe(False, self.now - 15)
        self.state.next_event(self.now)
        self.state.write_health(self.now)
        self.config = dataclasses.replace(self.config, dashboard_port=8765)
        self.key = '0123456789abcdef' * 4
        self.start_server()
        self.client = self.root / 'dashboard-client.json'
        self.client.write_text(json.dumps({'url': self.server.url}))
        self.client.chmod(0o600)

    def start_server(self, port=0):
        self.server = DashboardServer(self.config, self.key, port=port)
        self.server.timeout = 0.05
        self.server.thread = threading.Thread(target=self.server.run, daemon=True)
        self.server.thread.start()

    def tearDown(self):
        stop(self.server)
        if self.server.job:
            self.server.job.join(5)
        super().tearDown()

    def http(self, route='', method='GET', body=None, headers=None):
        url = urlsplit(self.server.url)
        conn = http.client.HTTPConnection(url.hostname, url.port, timeout=3)
        try:
            conn.request(method, url.path + route, body, headers or {})
            result = conn.getresponse()
            return result.status, dict(result.getheaders()), result.read()
        finally:
            conn.close()

    def test_phone_button_generates_report_and_keeps_link_and_snapshot(self):
        url = self.server.url
        self.assertIn(b'Generate new graph', self.http()[2])
        self.assertIsNone(self.server.generated_at)
        generate(url)
        self.server.job.join(5)
        self.assertIsNone(self.server.error)
        status, headers, body = self.http()
        self.assertEqual(status, 200)
        self.assertIn(b'The past 14 days', body)
        self.assertIn(b"form-action 'self'", body)
        self.assertIn(b'Bookmark this page', body)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.server.url, url)
        report = self.http('report')[2]
        self.state.observe(True, self.now)
        self.server.clock = lambda: time.monotonic() + 86400 * 30
        self.assertEqual(self.http('report')[2], report)  # No expiry or implicit regeneration.
        self.assertNotIn(self.key.encode(), report)
        self.assertEqual(self.server.report_path.stat().st_mode & 0o777, 0o600)

    def test_exact_observed_online_and_confirmed_offline_seconds_are_in_graph(self):
        self.cookie.unlink()
        self.topic.unlink()
        report = generate(self.server.url, download=True).encode()
        zone, _ = server_zone()
        self.assertIn(stamp(self.now - 90, zone).encode(), report)
        self.assertIn(stamp(self.now - 30, zone).encode(), report)
        self.assertIn(b'Seen online', report)
        self.assertIn(b'Seen offline', report)
        self.assertIn(b'Confirmed', report)
        self.assertIn(b'These are observation times', report)
        self.assertNotIn(b'TEST_OBSERVER_SESSION', report)

    def test_saved_graph_and_secret_url_survive_service_restart(self):
        generate(self.server.url, download=True)
        url, content, old_csrf = self.server.url, self.http('report')[2], self.server.csrf
        port = self.server.server_port
        stop(self.server)
        self.start_server(port)
        self.assertEqual(self.server.url, url)
        self.assertEqual(self.http('report')[2], content)
        self.assertNotEqual(self.server.csrf, old_csrf)

    def test_generation_is_protected_from_cross_site_and_missing_or_duplicate_forms(self):
        for headers, body in [
            ({'Content-Type': 'application/x-www-form-urlencoded'}, 'csrf=wrong'),
            ({'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://other.invalid'}, urlencode({'csrf': self.server.csrf})),
            ({'Content-Type': 'application/x-www-form-urlencoded', 'Sec-Fetch-Site': 'cross-site'}, urlencode({'csrf': self.server.csrf})),
            ({'Content-Type': 'application/x-www-form-urlencoded'}, 'csrf='+self.server.csrf+'&csrf='+self.server.csrf),
            ({'Content-Type': 'application/json'}, '{}')]:
            self.assertIn(self.http('generate', 'POST', body, headers)[0], (400, 403))
        self.assertEqual(self.http('generate')[0], 405)
        self.assertIsNone(self.server.job)

    def test_browser_fetch_form_accepts_charset_and_returns_json_without_a_redirect(self):
        body = urlencode({'csrf': self.server.csrf})
        status, headers, result = self.http('generate', 'POST', body,
            {'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8',
             'Origin':'http://'+urlsplit(self.server.url).netloc, 'Accept':'application/json'})
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(result), {'generating':True})
        self.assertNotIn('Location', headers)
        self.server.job.join(5)
        self.assertIn(b'The past 14 days', self.http('report')[2])

    def test_paths_methods_host_and_health_never_disclose_credentials_or_account_ids(self):
        for route in ('../config.json', 'cookie', '?query=1', 'report?x=1'):
            self.assertEqual(self.http(route)[0], 404)
        self.assertEqual(self.http(headers={'Host': 'foreign.invalid:1234'})[0], 403)
        self.assertEqual(self.http(method='DELETE')[0], 405)
        data = self.http('state')[2]
        self.assertNotIn(b'scope', data)
        self.assertNotIn(b'cookie', data)
        self.assertNotIn(b'TEST_OBSERVER_SESSION', data)
        self.assertEqual(set(json.loads(data)['monitor']), {'healthy','stable_online','last_success','updated_at','last_error','push_last_error','pending_notifications'})

    def test_failed_or_repeated_generation_keeps_old_graph_and_does_not_change_monitor_state(self):
        original = generate(self.server.url, download=True)
        self.assertFalse(self.server.generate())
        self.server.last_requested = float('-inf')
        before = self.state.db.total_changes
        original_config = self.server.config
        self.server.config = dataclasses.replace(original_config, state_dir=self.root/'missing-state')
        try:
            generate(self.server.url)
            self.server.job.join(5)
        finally:
            self.server.config = original_config
        self.assertTrue(self.server.error)
        self.assertEqual(self.http('report')[2].decode(), original)
        self.assertNotIn(b'TEST_OBSERVER_SESSION', self.http()[2])
        self.assertEqual(self.state.db.total_changes, before)

    def test_regular_user_graph_dashboard_status_and_file_export_never_load_monitor_config(self):
        with patch('roblox_presence.__main__.load') as private_config, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['graph', '--client', str(self.client), '--file-only', '--output', str(self.root/'copy.html')]), 0)
            self.assertEqual(main(['dashboard', '--client', str(self.client)]), 0)
            self.assertEqual(main(['status', '--client', str(self.client)]), 0)
            with patch('roblox_presence.dashboard_client.client_path', return_value=self.client):
                self.assertEqual(main(['dashboard']), 0)
        private_config.assert_not_called()
        self.assertIn(self.server.url, output.getvalue())
        self.assertEqual((self.root/'copy.html').read_bytes(), self.http('report')[2])
        self.assertEqual(load_client(self.client), self.server.url)
        self.client.chmod(0o644)
        with self.assertRaises(ConfigError):
            load_client(self.client)

    def test_client_refuses_public_or_malformed_urls_and_never_follows_redirects(self):
        for url in ('http://8.8.8.8:8765/'+self.key+'/', 'http://0.0.0.0:8765/'+self.key+'/',
                    'https://127.0.0.1:8765/'+self.key+'/', self.server.url+'?query=1',
                    'http://user:password@127.0.0.1:8765/'+self.key+'/', 'http://example.invalid/secret'):
            with self.assertRaises(ConfigError):
                validate_url(url)
        with patch('roblox_presence.dashboard_client.http.client.HTTPConnection') as connection:
            connection.return_value.getresponse.return_value.status = 303
            connection.return_value.getresponse.return_value.read.return_value = b''
            request(self.server.url, 'generate', csrf=self.server.csrf)
            self.assertEqual(connection.return_value.request.call_count, 1)


class DashboardSetupTests(unittest.TestCase):
    setUp = deployment.UpgradeTests.setUp
    tearDown = deployment.UpgradeTests.tearDown
    old_install = deployment.UpgradeTests.old_install
    # This class adds setup assertions to the isolated fixture, not a live root deployment.
    def test_dashboard_setup_is_private_and_unit_allowance_is_limited_to_selected_port(self):
        app = self.old_install()
        home = self.base/'operator-home'
        home.mkdir(mode=0o700)
        identity = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(home))
        config = load(self.root/'etc/roblox-presence/config.json')
        prepared = setup.plan(config, address='10.12.34.56', root=self.root, identity=identity, check_port=False)
        setup.apply_files(prepared)
        self.assertEqual(prepared['key_path'].stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_client(home/'.config/roblox-presence/dashboard.json'), prepared['url'])
        content = prepared['dropin'].read_text()
        self.assertIn('SocketBindAllow=ipv4:tcp:8765', content)
        self.assertIn('LoadCredential=dashboard_key:', content)
        self.assertNotIn('SocketBindDeny=', content)  # Existing deny-all is retained.
        self.assertIn('SocketBindDeny=any', (self.root/'etc/systemd/system/roblox-presence.service').read_text())
        self.assertEqual(os.readlink(app/'current'), 'releases/0.1.0')

    def test_occupied_port_or_foreign_dropin_is_refused_before_changes(self):
        self.old_install()
        config = load(self.root/'etc/roblox-presence/config.json')
        identity = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(self.base))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaises(ConfigError):
                setup.plan(config, root=self.root, identity=identity, port=listener.getsockname()[1])
        directory = self.root/'etc/systemd/system/roblox-presence.service.d'
        directory.mkdir()
        (directory/'dashboard.conf').write_text('administrator custom file')
        with self.assertRaises(ConfigError):
            setup.plan(config, root=self.root, identity=identity, check_port=False)
        self.assertFalse((self.root/'etc/roblox-presence/dashboard_key').exists())

    def test_dashboard_upgrade_backs_up_config_and_restarts_only_monitor_with_client_ready(self):
        self.old_install()
        home = self.base/'operator-home'
        home.mkdir(mode=0o700)
        identity = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(home))
        original_plan = setup.plan
        def fixture_plan(*args, **kwargs):
            return original_plan(*args, **kwargs, identity=identity, check_port=False)
        calls = []
        def control(*args):
            calls.append(args)
            return 'active\n' if args[0] == 'is-active' else ''
        with patch.object(setup, 'plan', side_effect=fixture_plan), \
             patch.object(setup, 'verify') as verify, \
             patch.object(deployment.upgrader, 'systemctl', side_effect=control), \
             patch.object(deployment.upgrader, 'production_snapshot', return_value={}), \
             patch.object(deployment.upgrader, 'read_health', return_value={'healthy':True,'last_success':9999999999,'updated_at':9999999999}), \
             contextlib.redirect_stdout(io.StringIO()):
            deployment.upgrader.apply_upgrade(root=self.root, graph_listen='10.12.34.56', dashboard=True)
        self.assertEqual(calls, [('is-active','roblox-presence.service'), ('stop','roblox-presence.service'),
                                 ('daemon-reload',), ('start','roblox-presence.service')])
        installed = load(self.root/'etc/roblox-presence/config.json')
        self.assertEqual(installed.dashboard_port, 8765)
        self.assertEqual(installed.dashboard_key_file, 'credential:dashboard_key')
        verify.assert_called_once_with(load_client(home/'.config/roblox-presence/dashboard.json'))
        self.assertTrue(list((self.root/'opt/roblox-presence/backups').glob('*/config.json')))


class DashboardIsolationTests(Fixture):
    def test_dashboard_start_failure_does_not_prevent_presence_checks(self):
        from roblox_presence.monitor import Monitor
        state = self.db()
        monitor = Monitor(self.config, state, SimpleNamespace(), SimpleNamespace())
        def poll():
            monitor.shutdown_requested = True
            monitor.stop.set()
            return False
        monitor.source.poll = poll
        with patch('roblox_presence.dashboard.start', side_effect=OSError('TEST_OBSERVER_SESSION')), \
             patch('roblox_presence.monitor.systemd_notify'):
            monitor.run()
        self.assertIsNotNone(state.status()['last_success'])
