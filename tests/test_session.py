import io
import json
import unittest
from email.message import Message

from roblox_presence.config import ConfigError
from roblox_presence.http import Http, Response, ServiceError
from roblox_presence.roblox import Roblox
from roblox_presence.session import Session
from tests.test_monitor import Fixture, FakeHttp, response


class SessionTests(Fixture):
    def rotation(self, value="TEST_ROTATED_SESSION", **attrs):
        header = ".ROBLOSECURITY=" + value + "; Domain=.roblox.com; Path=/; Secure; HttpOnly"
        return Response(200, {}, b'{"id":11}', (header,))

    def test_rotated_cookie_used_for_presence_and_survives_restart(self):
        http = FakeHttp([self.rotation(), response({"userPresences": [{"userId": 22, "userPresenceType": 1}]})])
        self.assertTrue(Roblox(self.config, http).poll())
        self.assertEqual(http.calls[0][2]["headers"]["Cookie"], ".ROBLOSECURITY=TEST_OBSERVER_SESSION")
        self.assertEqual(http.calls[1][2]["headers"]["Cookie"], ".ROBLOSECURITY=TEST_ROTATED_SESSION")
        self.assertEqual(Session(self.config).value(), "TEST_ROTATED_SESSION")
        self.assertEqual(Session(self.config).path.stat().st_mode & 0o777, 0o600)

    def test_deployment_exports_current_rotated_credential(self):
        session = Session(self.config); session.value(); session.update(self.rotation())
        self.assertEqual(self.config.credentials()["roblox_cookie"], "TEST_ROTATED_SESSION")

    def test_new_source_credential_overrides_cached_session(self):
        session = Session(self.config); session.value(); session.update(self.rotation())
        self.cookie.write_text("NEW_OPERATOR_SESSION")
        self.assertEqual(Session(self.config).value(), "NEW_OPERATOR_SESSION")

    def test_source_changed_during_request_does_not_adopt_old_cookie_for_new_source(self):
        session = Session(self.config); session.value()
        self.cookie.write_text("NEW_OPERATOR_SESSION")
        session.update(self.rotation())
        self.assertEqual(Session(self.config).value(), "NEW_OPERATOR_SESSION")

    def test_wrong_observer_does_not_save_rotation(self):
        wrong = Response(200, {}, b'{"id":99}', self.rotation().set_cookies)
        with self.assertRaisesRegex(ServiceError, "observer_mismatch"):
            Roblox(self.config, FakeHttp([wrong])).poll()
        self.assertFalse(Session(self.config).path.exists())

    def test_presence_response_rotation_is_preserved(self):
        presence = Response(200, {}, b'{"userPresences":[{"userId":22,"userPresenceType":0}]}', self.rotation().set_cookies)
        self.assertFalse(Roblox(self.config, FakeHttp([response({"id":11}), presence])).poll())
        self.assertEqual(Session(self.config).value(), "TEST_ROTATED_SESSION")

    def test_csrf_response_rotation_used_in_retry(self):
        challenge = Response(403, {"x-csrf-token":"TEST_CSRF"}, b'{}', self.rotation().set_cookies)
        http = FakeHttp([response({"id":11}), challenge, response({"userPresences":[{"userId":22,"userPresenceType":1}]})])
        self.assertTrue(Roblox(self.config, http).poll())
        self.assertEqual(http.calls[1][2]["headers"]["Cookie"], ".ROBLOSECURITY=TEST_OBSERVER_SESSION")
        self.assertEqual(http.calls[2][2]["headers"]["Cookie"], ".ROBLOSECURITY=TEST_ROTATED_SESSION")

    def test_other_cookies_are_not_retained(self):
        session = Session(self.config); session.value()
        self.assertIsNone(session.update(Response(200, {}, b'{}', ("OTHER_COOKIE=OTHER_VALUE",))))
        self.assertFalse(session.path.exists())

    def test_malformed_wrong_domain_and_deletion_are_safe_errors(self):
        for header in ('.ROBLOSECURITY=; Max-Age=0', '.ROBLOSECURITY=secret; Domain=evil.invalid',
                       '.ROBLOSECURITY="bad value"; Domain=.roblox.com', '.ROBLOSECURITY=secret; Max-Age=0'):
            session = Session(self.config); session.value()
            with self.assertRaisesRegex(ServiceError, "invalid_session_rotation") as error:
                session.update(Response(200, {}, b'{}', (header,)))
            self.assertNotIn("secret", str(error.exception))
            self.assertFalse(session.path.exists())

    def test_world_readable_and_symlink_cache_refused(self):
        session = Session(self.config); session.value(); session.update(self.rotation())
        session.path.chmod(0o644)
        with self.assertRaises(ConfigError): Session(self.config).value()
        session.path.unlink(); session.path.symlink_to(self.cookie)
        with self.assertRaises(ConfigError): Session(self.config).value()

    def test_invalid_cache_does_not_echo_contents(self):
        session = Session(self.config); self.config.state_dir.mkdir()
        session.path.write_text('{"PRIVATE_TEST_SESSION":')
        session.path.chmod(0o600)
        with self.assertRaises(ConfigError) as error: session.value()
        self.assertNotIn("PRIVATE_TEST_SESSION", str(error.exception))

    def test_transport_keeps_all_set_cookie_headers(self):
        headers = Message()
        headers.add_header("Set-Cookie", ".ROBLOSECURITY=TEST_ROTATED_SESSION; Domain=.roblox.com")
        headers.add_header("Set-Cookie", "OTHER_COOKIE=other")
        class Stream(io.BytesIO):
            code = 200
        class Opener:
            def open(self, *args, **kwargs):
                stream = Stream(b'{"id":11}'); stream.headers = headers; return stream
        result = Http(opener=Opener()).request("GET", "https://users.roblox.com/v1/users/authenticated")
        self.assertEqual(len(result.set_cookies), 2)
        session = Session(self.config); session.value(); session.update(result)
        self.assertEqual(session.value(), "TEST_ROTATED_SESSION")


if __name__ == "__main__":
    unittest.main()
