import dataclasses
import io
import json
import logging
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from roblox_presence.config import Config, ConfigError, cookie, load, secret
from roblox_presence.http import Http, NoRedirect, Response, ServiceError, retry_after
from roblox_presence.monitor import Monitor, delay
from roblox_presence.push import Push
from roblox_presence.roblox import Roblox, parse_presence
from roblox_presence.state import State, process_lock, read_health


def response(obj, status=200, headers=None):
    return Response(status, headers or {}, json.dumps(obj).encode())


class FakeHttp:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cookie = self.root / "cookie"
        self.topic = self.root / "topic"
        self.cookie.write_text("TEST_OBSERVER_SESSION")
        self.topic.write_text("rp-" + "a" * 48)
        self.cookie.chmod(0o600)
        self.topic.chmod(0o600)
        self.config = Config(11, 22, str(self.cookie), "ntfy", "https://ntfy.sh", str(self.topic),
                             None, None, self.root / "state")
        self.state = None

    def tearDown(self):
        if self.state:
            self.state.close()
        self.temp.cleanup()

    def db(self):
        self.state = State(self.config, 1000)
        return self.state


class PresenceTests(Fixture):
    def test_all_presence_types(self):
        for status, expected in ((0, False), (1, True), (2, True), (3, True)):
            self.assertEqual(parse_presence({"userPresences": [{"userId": 22, "userPresenceType": status}]}, 22), expected)

    def test_missing_wrong_duplicate_and_future_types_are_unknown(self):
        for data in ({}, {"userPresences": None}, {"userPresences": []},
                     {"userPresences": [{"userId": 33, "userPresenceType": 0}]},
                     {"userPresences": [{"userId": 22, "userPresenceType": 4}]},
                     {"userPresences": [{"userId": 22, "userPresenceType": True}]},
                     {"userPresences": [{"userId": 22, "userPresenceType": 1}] * 2}):
            with self.subTest(data=data), self.assertRaises(ServiceError):
                parse_presence(data, 22)

    def test_identity_verified_before_every_poll(self):
        http = FakeHttp([response({"id": 11}), response({"userPresences": [{"userId": 22, "userPresenceType": 2}]})])
        self.assertTrue(Roblox(self.config, http).poll())
        self.assertEqual(http.calls[0][1], "https://users.roblox.com/v1/users/authenticated")
        self.assertEqual(json.loads(http.calls[1][2]["body"]), {"userIds": [22]})
        self.assertEqual(http.calls[0][2]["headers"]["Cookie"], ".ROBLOSECURITY=TEST_OBSERVER_SESSION")

    def test_wrong_observer_never_queries_presence(self):
        http = FakeHttp([response({"id": 99})])
        with self.assertRaisesRegex(ServiceError, "observer_mismatch"):
            Roblox(self.config, http).poll()
        self.assertEqual(len(http.calls), 1)

    def test_expired_cookie_never_becomes_offline(self):
        http = FakeHttp([response({"errors": [{"message": "TEST_OBSERVER_SESSION"}]}, 401)])
        with self.assertRaisesRegex(ServiceError, "authentication_failed") as error:
            Roblox(self.config, http).poll()
        self.assertNotIn("TEST_OBSERVER_SESSION", str(error.exception))
        self.assertEqual(len(http.calls), 1)

    def test_csrf_challenge_retried_once_on_same_endpoint(self):
        http = FakeHttp([response({"id": 11}), response({}, 403, {"x-csrf-token": "token"}),
                         response({"userPresences": [{"userId": 22, "userPresenceType": 1}]})])
        self.assertTrue(Roblox(self.config, http).poll())
        self.assertEqual(http.calls[-1][2]["headers"]["X-CSRF-Token"], "token")
        self.assertEqual(http.calls[-1][1], http.calls[-2][1])

    def test_second_csrf_failure_stops(self):
        http = FakeHttp([response({"id": 11}), response({}, 403, {"x-csrf-token": "token"}),
                         response({}, 403, {"x-csrf-token": "another"})])
        with self.assertRaises(ServiceError):
            Roblox(self.config, http).poll()
        self.assertEqual(len(http.calls), 3)

    def test_rate_limit_honors_retry_after(self):
        http = FakeHttp([response({}, 429, {"retry-after": "600"})])
        with self.assertRaises(ServiceError) as err:
            Roblox(self.config, http).poll()
        self.assertEqual(err.exception.retry_after, 600)

    def test_target_validation(self):
        for data in ({"id": 22, "isBanned": True}, {"id": 99}):
            with self.assertRaises(ServiceError):
                Roblox(self.config, FakeHttp([response(data)])).validate_target()


class StateTests(Fixture):
    def test_transition_once_with_game_changes(self):
        state = self.db()
        self.assertFalse(state.observe(False, 1000))
        self.assertTrue(state.observe(True, 1015))
        self.assertFalse(state.observe(True, 1030))
        self.assertEqual(state.status()["pending_notifications"], 1)

    def test_restart_does_not_duplicate_online(self):
        self.db().observe(True, 1000)
        self.state.close()
        self.state = State(self.config, 1010)
        self.assertFalse(self.state.observe(True, 1015))
        self.assertEqual(self.state.status()["pending_notifications"], 1)

    def test_startup_can_be_silent(self):
        self.config = dataclasses.replace(self.config, notify_on_startup=False)
        state = self.db()
        self.assertFalse(state.observe(True, 1000))
        state.observe(False, 1015)
        state.observe(False, 1030)
        self.assertTrue(state.observe(True, 1045))

    def test_offline_glitch_does_not_rearm(self):
        state = self.db()
        state.observe(True, 1000)
        state.observe(False, 1015)
        self.assertFalse(state.observe(True, 1030))
        self.assertEqual(state.status()["pending_notifications"], 1)

    def test_unknown_resets_offline_candidate_and_preserves_online(self):
        state = self.db()
        state.observe(True, 1000)
        state.observe(False, 1015)
        state.failed("network_error", 1030)
        self.assertEqual(state.status()["stable_online"], 1)
        state.observe(False, 1045)
        self.assertEqual(state.status()["stable_online"], 1)
        state.observe(False, 1060)
        self.assertEqual(state.status()["stable_online"], 0)

    def test_long_gap_resets_offline_candidate(self):
        state = self.db()
        state.observe(True, 1000)
        state.observe(False, 1015)
        state.observe(False, 1200)
        self.assertEqual(state.status()["stable_online"], 1)

    def test_confirmed_offline_cancels_pending_then_new_session_notifies(self):
        state = self.db()
        state.observe(True, 1000)
        old = state.next_event(1000)
        state.observe(False, 1015)
        self.assertFalse(state.eligible(old, 1015))
        state.observe(False, 1030)
        self.assertIsNone(state.next_event(1030))
        self.assertTrue(state.observe(True, 1045))
        self.assertNotEqual(state.next_event(1045)["session_id"], old["session_id"])

    def test_stale_and_failed_observations_pause_online_delivery(self):
        state = self.db()
        state.observe(True, 1000)
        event = state.next_event(1000)
        self.assertFalse(state.eligible(event, 1100))
        state.failed("network_error", 1010)
        self.assertFalse(state.eligible(event, 1010))
        state.observe(True, 1015)
        self.assertTrue(state.eligible(event, 1015))

    def test_notification_expires(self):
        state = self.db()
        state.observe(True, 1000)
        self.assertIsNone(state.next_event(1300))

    def test_delivery_acknowledgement_persists(self):
        state = self.db()
        state.observe(True, 1000)
        event = state.next_event(1000)
        state.delivered(event, 1001)
        self.assertIsNone(state.next_event(1002))
        self.assertEqual(state.status()["push_last_success"], 1001)

    def test_provider_retry_floor_survives_restart_and_new_event(self):
        state = self.db()
        state.observe(True, 1000)
        event = state.next_event(1000)
        state.retry(event, "ntfy_rate_limited", 1000, 600)
        self.state.close()
        self.state = State(self.config, 1010)
        self.state.failed("network_error", 1010)
        self.state.failed("network_error", 1400)
        self.assertIsNone(self.state.next_event(1500))
        self.assertIsNotNone(self.state.next_event(1600))

    def test_outage_alert_once_then_recovery(self):
        state = self.db()
        state.failed("roblox_authentication_failed", 1000)
        state.failed("roblox_authentication_failed", 1300)
        state.failed("roblox_authentication_failed", 1400)
        event = state.next_event(1400)
        self.assertEqual(event["kind"], "outage")
        state.delivered(event, 1400)
        state.observe(False, 1415)
        self.assertEqual(state.next_event(1415)["kind"], "recovery")

    def test_scopes_do_not_reuse_previous_accounts_state(self):
        state = self.db()
        state.observe(True, 1000)
        self.state.close()
        self.config = dataclasses.replace(self.config, target_user_id=33)
        self.state = State(self.config, 1010)
        self.assertIsNone(self.state.status()["stable_online"])
        self.assertIsNone(self.state.next_event(1010))

    def test_process_lock_prevents_duplicate_workers(self):
        with process_lock(self.config.state_dir):
            with self.assertRaises(ConfigError):
                with process_lock(self.config.state_dir):
                    pass

    def test_future_schema_is_preserved_and_refused(self):
        state = self.db()
        state.db.execute("PRAGMA user_version=999")
        self.state.close()
        self.state = None
        with self.assertRaises(ConfigError):
            State(self.config, 1010)

    def test_health_detects_failure_and_staleness(self):
        state = self.db()
        state.observe(True, 1000)
        state.next_event(1000)
        state.write_health(1000)
        self.assertTrue(read_health(self.config, 1001)["healthy"])
        self.assertFalse(read_health(self.config, 1020)["healthy"])
        state.failed("roblox_authentication_failed", 1002)
        state.write_health(1002)
        self.assertFalse(read_health(self.config, 1003)["healthy"])


class TransportTests(unittest.TestCase):
    def test_retry_after_numeric_date_invalid(self):
        self.assertEqual(retry_after({"retry-after": "120"}), 120)
        self.assertEqual(retry_after({"retry-after": "Thu, 01 Jan 1970 00:02:00 GMT"}, 0), 120)
        self.assertIsNone(retry_after({"retry-after": "bad"}))

    def test_backoff_is_bounded_and_obeys_server_floor(self):
        self.assertEqual(delay(100000, jitter=lambda a, b: 1), 300)
        self.assertEqual(delay(1, minimum=600, jitter=lambda a, b: 1), 600)

    def test_redirects_are_refused(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))

    def test_network_exception_text_is_not_exposed(self):
        class Opener:
            def open(self, *args, **kwargs):
                raise URLError("SECRET_COOKIE_IN_URL")
        with self.assertRaises(ServiceError) as error:
            Http(opener=Opener()).request("GET", "https://users.roblox.com")
        self.assertEqual(str(error.exception), "network_error")

    def test_response_size_bound(self):
        class Stream(io.BytesIO):
            code, headers = 200, {}
        class Opener:
            def open(self, *args, **kwargs):
                return Stream(b"x" * 131073)
        with self.assertRaisesRegex(ServiceError, "response_too_large"):
            Http(opener=Opener()).request("GET", "https://users.roblox.com")

    def test_malformed_json_is_unknown(self):
        for body in (b"not-json", b"[]", b"\xff"):
            with self.assertRaises(ServiceError):
                Response(200, {}, body).json()


class PushTests(Fixture):
    def test_ntfy_requires_provider_ack_not_just_http_200(self):
        for ack in ({}, {"event": "message", "id": "x", "topic": "wrong"}):
            with self.assertRaises(ServiceError):
                Push(self.config, FakeHttp([response(ack)])).send({"kind": "online", "created_at": 1000})

    def test_ntfy_content_is_minimal_without_session_data(self):
        http = FakeHttp([response({"event": "message", "id": "accepted", "topic": self.topic.read_text()})])
        Push(self.config, http).send({"kind": "online", "created_at": 1000})
        payload = json.loads(http.calls[0][2]["body"])
        self.assertEqual(payload["priority"], 4)
        self.assertNotIn("TEST_OBSERVER_SESSION", str(http.calls))
        self.assertEqual(set(payload), {"topic", "title", "message", "priority", "tags", "click"})

    def test_ntfy_token_sent_only_to_push_host(self):
        token = self.root / "token"
        token.write_text("PUSH_TOKEN")
        token.chmod(0o600)
        config = dataclasses.replace(self.config, push_token_file=str(token))
        http = FakeHttp([response({"event": "message", "id": "accepted", "topic": self.topic.read_text()})])
        Push(config, http).send({"kind": "test", "created_at": 1000})
        self.assertEqual(http.calls[0][2]["headers"]["Authorization"], "Bearer PUSH_TOKEN")
        self.assertNotIn("Cookie", http.calls[0][2]["headers"])


class IntegrationTests(Fixture):
    def test_offline_online_provider_failure_restart_retry_without_duplicate(self):
        clock = [1000]
        source_http = FakeHttp([response({"id": 11}), response({"userPresences": [{"userId": 22, "userPresenceType": 0}]}),
                                response({"id": 11}), response({"userPresences": [{"userId": 22, "userPresenceType": 2}]})])
        push_http = FakeHttp([response({}, 503), response({"event": "message", "id": "accepted", "topic": self.topic.read_text()})])
        state = self.db()
        monitor = Monitor(self.config, state, Roblox(self.config, source_http), Push(self.config, push_http),
                          clock=lambda: clock[0], monotonic=lambda: clock[0])
        monitor.poll_once()
        self.assertFalse(monitor.deliver_once())
        clock[0] = 1015
        monitor.poll_once()
        self.assertFalse(monitor.deliver_once())
        self.state.close()
        self.state = State(self.config, 1017)
        monitor = Monitor(self.config, self.state, None, Push(self.config, push_http),
                          clock=lambda: clock[0], monotonic=lambda: clock[0])
        clock[0] = 1017
        self.assertFalse(monitor.deliver_once())
        clock[0] = 1022
        self.assertTrue(monitor.deliver_once())
        self.assertFalse(monitor.deliver_once())
        self.assertEqual(len(push_http.calls), 2)

    def test_logs_never_include_upstream_error_body(self):
        state = self.db()
        http = FakeHttp([response({"errors": [{"message": "TEST_OBSERVER_SESSION"}]}, 401)])
        monitor = Monitor(self.config, state, Roblox(self.config, http), None, clock=lambda: 1000)
        with self.assertLogs("roblox_presence", level=logging.WARNING) as logs:
            monitor.poll_once()
        self.assertNotIn("TEST_OBSERVER_SESSION", str(logs.output))
        self.assertIsNone(state.status()["stable_online"])

    def test_worker_shuts_down_cleanly(self):
        import threading
        state = self.db()
        class Source:
            def poll(self):
                return False
        monitor = Monitor(self.config, state, Source(), None)
        monitor.shutdown_requested = True
        errors = []
        def start():
            try:
                monitor.run()
            except Exception as exc:
                errors.append(exc)
        with patch("roblox_presence.monitor.systemd_notify"):
            thread = threading.Thread(target=start)
            thread.start()
            deadline = time.monotonic() + 2
            while state.status()["last_success"] is None and time.monotonic() < deadline:
                time.sleep(0.01)
            monitor.stop.set()
            monitor.wake.set()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])


class ConfigTests(Fixture):
    def example(self):
        data = json.loads((Path(__file__).resolve().parents[1] / "config.example.json").read_text())
        data.update(observer_user_id=11, target_user_id=22, cookie_file=str(self.cookie), state_dir=str(self.config.state_dir))
        data["push"]["topic_file"] = str(self.topic)
        return data

    def write_config(self, data):
        path = self.root / "config.json"
        path.write_text(json.dumps(data))
        return path

    def test_valid_config_and_credentials(self):
        config = load(self.write_config(self.example()))
        self.assertEqual(config.credentials()["roblox_cookie"], "TEST_OBSERVER_SESSION")

    def test_config_rejects_invalid_ids_unsafe_urls_and_typoes(self):
        for field, value in (("observer_user_id", True), ("target_user_id", 0), ("poll_seconds", 1),
                             ("notify_on_startup", "false"), ("cookie_file", "relative"), ("typo", 1)):
            data = self.example()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                load(self.write_config(data))
        for url in ("http://ntfy.sh", "https://token@ntfy.sh", "https://ntfy.sh/topic", "https://ntfy.sh?token=secret"):
            data = self.example()
            data["push"]["base_url"] = url
            with self.subTest(url=url), self.assertRaises(ConfigError):
                load(self.write_config(data))

    def test_public_credential_permissions_refused(self):
        self.cookie.chmod(0o644)
        with self.assertRaises(ConfigError):
            secret(str(self.cookie))

    def test_symlink_credential_refused(self):
        link = self.root / "link"
        link.symlink_to(self.cookie)
        with self.assertRaises(ConfigError):
            secret(str(link))

    def test_directory_and_fifo_credentials_refused_without_blocking(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        for path in (self.root, fifo):
            with self.assertRaises(ConfigError):
                secret(str(path))

    def test_cookie_value_only_no_header_injection(self):
        for value in ("a\nb", "Cookie: x=y; other=z", "a\rb"):
            self.cookie.write_text(value)
            with self.assertRaises(ConfigError):
                cookie(str(self.cookie))

    def test_systemd_credentials_resolve(self):
        with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(self.root)):
            self.assertEqual(secret("credential:cookie"), "TEST_OBSERVER_SESSION")

    def test_missing_secret_is_safe_error(self):
        with self.assertRaises(ConfigError) as exc:
            secret(str(self.root / "missing-super-secret"))
        self.assertNotIn("missing-super-secret", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
