"""Viewer tests use loopback sockets and synthetic HTML, never real history."""

import contextlib
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
from urllib.parse import unquote, urlsplit

from roblox_presence.config import ConfigError, listen_address, load
from roblox_presence.__main__ import main
from roblox_presence.viewer import ReportServer, drop_privileges, file_link, serve
from tests.test_monitor import Fixture
from tests import test_deployment as deployment
upgrader = deployment.upgrader


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000]
        self.report = '<!doctype html><html><body>EXAMPLE PRIVATE REPORT</body></html>'
        self.server = ReportServer(self.report, clock=lambda: self.now[0])

    def tearDown(self):
        self.server.server_close()

    def request(self, path=None, method="GET", host=None):
        worker = threading.Thread(target=self.server.handle_request)
        worker.start()
        connection = http.client.HTTPConnection(*self.server.server_address[:2], timeout=3)
        try:
            connection.request(method, path or self.server.token_path, headers={"Host": host} if host else {})
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        return result

    def test_default_link_is_clickable_loopback_and_contains_only_this_report(self):
        parsed = urlsplit(self.server.url)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.hostname, "127.0.0.1")
        self.assertEqual(parsed.port, self.server.server_port)
        self.assertEqual(len(parsed.path.strip('/')), 64)
        status, headers, body = self.request(parsed.path)
        self.assertEqual(status, 200)
        self.assertEqual(body.decode(), self.report)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_listener_startup_never_waits_for_reverse_dns(self):
        with patch('socket.getfqdn', side_effect=AssertionError('No DNS lookup expected')):
            with ReportServer(self.report) as other:
                self.assertGreater(other.server_port, 1024)

    def test_missing_wrong_tokens_and_traversal_never_serve_files(self):
        for path in ('/', '/wrong/', '/../../config.json', '/%2e%2e/cookie', self.server.token_path+'?extra=1'):
            with self.subTest(path='synthetic path'):
                status, _, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b'PRIVATE REPORT', body)

    def test_foreign_host_and_write_methods_are_refused(self):
        self.assertEqual(self.request(host='untrusted.invalid:1234')[0], 403)
        for method in ('POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'):
            status, headers, body = self.request(method=method)
            self.assertEqual(status, 405)
            self.assertEqual(headers['Allow'], 'GET, HEAD')
            self.assertNotIn(b'PRIVATE REPORT', body)
        self.assertEqual(self.request(host='localhost:12345')[0], 200)

    def test_head_has_correct_length_but_no_body(self):
        status, headers, body = self.request(method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(int(headers['Content-Length']), len(self.report.encode()))
        self.assertEqual(body, b'')

    def test_link_expiry_stops_disclosure_and_ends_the_viewer(self):
        self.now[0] = 1601
        status, _, body = self.request()
        self.assertEqual(status, 410)
        self.assertNotIn(b'PRIVATE REPORT', body)
        self.server.serve_until_expiry()  # Returns immediately with no further requests.

    def test_tokens_are_independent_and_no_private_urls_are_logged(self):
        with ReportServer(self.report) as other:
            self.assertNotEqual(self.server.token_path, other.token_path)
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.request()
            self.request('/wrong/')
        self.assertEqual(errors.getvalue(), '')

    def test_slow_incomplete_headers_cannot_keep_the_viewer_blocked(self):
        self.server.request_timeout = 0.2
        worker = threading.Thread(target=self.server.handle_request)
        worker.start()
        connection = socket.create_connection(self.server.server_address[:2], timeout=1)
        try:
            connection.sendall(b'GET / HTTP/1.1\r\nX-Slow: ')
            for _ in range(15):
                time.sleep(0.03)
                if not worker.is_alive():
                    break
                try:
                    connection.sendall(b'x')
                except OSError:
                    break
            worker.join(1)
            self.assertFalse(worker.is_alive())
        finally:
            connection.close()
            worker.join(2)

    def test_private_bind_addresses_only_and_invalid_options_fail_before_bind(self):
        for value in ('0.0.0.0', '::', '8.8.8.8', '169.254.1.2', 'example.invalid', '::1%lo', None, True):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                listen_address(value)
        for value in ('127.0.0.1', '::1', '10.12.34.56', '172.20.1.2', '192.168.50.10', 'fd00::1'):
            self.assertEqual(listen_address(value), value)
        for kwargs in ({'port': -1}, {'port': 80}, {'port': 65536}, {'lifetime': 0}, {'lifetime': 3601}):
            with self.assertRaises(ConfigError):
                ReportServer(self.report, **kwargs)

    def test_file_link_escapes_spaces_unicode_and_url_characters(self):
        path = Path('/example folder/report ü #?.html')
        link = file_link(path)
        self.assertTrue(link.startswith('file:///'))
        self.assertIn('%20', link)
        self.assertIn('%23', link)
        self.assertIn('%3F', link)
        self.assertEqual(unquote(urlsplit(link).path), str(path))

    def test_root_viewer_drops_supplementary_groups_gid_and_uid_before_listening(self):
        actions = []
        with patch('roblox_presence.viewer.os.geteuid', return_value=0), \
             patch.dict(os.environ, SUDO_UID='12345'), \
             patch('roblox_presence.viewer.pwd.getpwuid', return_value=SimpleNamespace(pw_uid=12345, pw_gid=23456)), \
             patch('roblox_presence.viewer.os.setgroups', side_effect=lambda v: actions.append(('groups', v))), \
             patch('roblox_presence.viewer.os.setgid', side_effect=lambda v: actions.append(('gid', v))), \
             patch('roblox_presence.viewer.os.setuid', side_effect=lambda v: actions.append(('uid', v))):
            drop_privileges()
        self.assertEqual(actions, [('groups', []), ('gid', 23456), ('uid', 12345)])
        with patch('roblox_presence.viewer.os.geteuid', return_value=0), patch.dict(os.environ, SUDO_UID='0'), self.assertRaises(ConfigError):
            drop_privileges()


class ViewerConfigTests(Fixture):
    def test_configuration_defaults_to_loopback_and_validates_saved_address(self):
        obj = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
        path = self.root / 'config.json'
        path.write_text(json.dumps(obj))
        self.assertEqual(load(path).graph_listen_address, '127.0.0.1')
        obj['graph_listen_address'] = '10.12.34.56'
        path.write_text(json.dumps(obj))
        self.assertEqual(load(path).graph_listen_address, '10.12.34.56')
        obj['graph_listen_address'] = '0.0.0.0'
        path.write_text(json.dumps(obj))
        with self.assertRaises(ConfigError):
            load(path)

    def test_graph_cli_serves_saved_snapshot_with_config_or_one_off_address(self):
        state = self.db()
        state.observe(False, time.time())
        obj = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
        obj.update(observer_user_id=11, target_user_id=22, state_dir=str(self.config.state_dir),
                   graph_listen_address='10.12.34.56')
        path, output = self.root / 'config.json', self.root / 'report.html'
        path.write_text(json.dumps(obj))
        self.cookie.unlink()  # Generating or viewing a report never needs the session.
        self.topic.unlink()
        for options, address in (([], '10.12.34.56'), (['--listen', '127.0.0.1', '--minutes', '2'], '127.0.0.1')):
            with patch('roblox_presence.viewer.serve') as viewer, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['graph', '--config', str(path), '--output', str(output), *options]), 0)
            content, selected, port, minutes = viewer.call_args.args
            self.assertEqual(content, output.read_text())
            self.assertEqual(selected, address)
            self.assertEqual(port, 0)
            self.assertEqual(minutes, 2 if options else 10)
        self.assertEqual(load(path).graph_listen_address, '10.12.34.56')


class ViewerUpgradeTests(unittest.TestCase):
    setUp = deployment.UpgradeTests.setUp
    tearDown = deployment.UpgradeTests.tearDown
    old_install = deployment.UpgradeTests.old_install

    def test_selected_private_address_is_saved_with_backup_and_no_other_service_change(self):
        app = self.old_install()
        path = self.root / 'etc/roblox-presence/config.json'
        before = path.read_bytes()
        calls = []
        def control(*args):
            calls.append(args)
            return 'active\n' if args[0] == 'is-active' else ''
        with patch.object(upgrader, 'production_snapshot', return_value={}), \
             patch.object(upgrader, 'systemctl', side_effect=control), \
             patch.object(upgrader, 'read_health', return_value={'healthy': True, 'last_success': 9999999999, 'updated_at': 9999999999}), \
             contextlib.redirect_stdout(io.StringIO()):
            upgrader.apply_upgrade(root=self.root, graph_listen='10.12.34.56')
        self.assertEqual(load(path).graph_listen_address, '10.12.34.56')
        self.assertEqual(next((app/'backups').glob('*/config.json')).read_bytes(), before)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(calls, [('is-active', 'roblox-presence.service'), ('stop', 'roblox-presence.service'), ('start', 'roblox-presence.service')])
