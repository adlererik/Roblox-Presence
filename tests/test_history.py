import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from roblox_presence.__main__ import main
from roblox_presence.config import ConfigError
from roblox_presence.push import message
from roblox_presence.report import export_report, intervals, render, server_zone, snapshot
from roblox_presence.roblox import Roblox
from roblox_presence.state import State
from tests.test_monitor import Fixture, FakeHttp, response
from tests.test_deployment import ROOT, installer


DETAILS = {"username": "ExampleConnection", "display_name": "Example Player", "game_name": "Example Adventure", "presence_type": "in_game"}


class HistoryTests(Fixture):
    def test_offline_is_dated_at_first_sample_only_after_confirmation(self):
        state = self.db()
        state.observe(True, 1000)
        state.observe(False, 1015)
        self.assertEqual(state.db.execute("SELECT kind FROM history ORDER BY id DESC LIMIT 1").fetchone()[0], "pending")
        state.observe(False, 1030)
        rows = list(state.db.execute("SELECT kind,event,event_at,observed_at FROM history ORDER BY id"))
        self.assertEqual(tuple(rows[1]), ("offline", None, None, 1015))
        self.assertEqual(tuple(rows[2]), ("offline", "offline", 1015, 1030))
        self.assertEqual(intervals([dict(r) for r in state.db.execute("SELECT * FROM history ORDER BY id")], 1040, 60),
                         [(1000, 1015, "online"), (1015, 1030, "offline")])

    def test_failure_never_invents_a_logout_or_fills_a_gap(self):
        state = self.db()
        state.observe(True, 1000)
        state.observe(True, 1015)
        state.observe(False, 1030)
        state.failed("network_error", 1045)
        state.observe(True, 1100)
        state.observe(True, 1115)
        rows = [dict(r) for r in state.db.execute("SELECT * FROM history ORDER BY id")]
        self.assertFalse(any(r["event"] == "offline" for r in rows))
        self.assertEqual(intervals(rows, 1120, 60), [(1000, 1015, "online"), (1100, 1115, "online")])

    def test_downtime_does_not_draw_a_continuous_online_bar(self):
        rows = [{"observed_at": t, "kind": "online"} for t in (1000, 1015, 2000, 2015)]
        self.assertEqual(intervals(rows, 2100, 60), [(1000, 1015, "online"), (2000, 2015, "online")])

    def test_history_retention_preserves_provider_and_current_scope(self):
        state = self.db()
        state.observe(True, 1000, details=DETAILS)
        event = state.next_event(1000)
        state.retry(event, "ntfy_rate_limited", 1000, 600)
        state.observe(True, 1000 + 16 * 86400)
        state.next_event(1000 + 16 * 86400)
        self.assertEqual(state.db.execute("SELECT COUNT(*) FROM history").fetchone()[0], 1)
        self.assertEqual(state.status()["stable_online"], 1)
        self.assertEqual(state.status()["push_retry_at"], 1600)

    def make_v1(self):
        self.config.state_dir.mkdir()
        db = sqlite3.connect(self.config.state_dir / "state.sqlite3")
        db.executescript("""
        CREATE TABLE monitor(scope TEXT PRIMARY KEY,created_at REAL NOT NULL,stable_online INTEGER,offline_samples INTEGER NOT NULL DEFAULT 0,session_id TEXT,last_attempt REAL,last_success REAL,last_error TEXT,outage_started REAL,outage_alerted INTEGER NOT NULL DEFAULT 0,push_last_success REAL,push_last_error TEXT,worker_heartbeat REAL,push_retry_at REAL NOT NULL DEFAULT 0);
        CREATE TABLE outbox(id TEXT PRIMARY KEY,scope TEXT NOT NULL,kind TEXT NOT NULL,session_id TEXT,created_at REAL NOT NULL,expires_at REAL NOT NULL,due_at REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'pending',completed_at REAL,error TEXT);
        PRAGMA user_version=1;
        """)
        db.execute("INSERT INTO monitor(scope,created_at,stable_online,session_id,last_success,push_retry_at) VALUES(?,?,?,?,?,?)", (self.config.scope, 1000, 1, "existing-session", 1000, 1600))
        db.execute("INSERT INTO outbox(id,scope,kind,session_id,created_at,expires_at,due_at) VALUES(?,?,?,?,?,?,?)", ("old-event", self.config.scope, "online", "existing-session", 1000, 1300, 1100))
        db.commit()
        db.close()

    def test_v1_migration_preserves_state_pending_event_and_backoff(self):
        self.make_v1()
        state = self.db()
        self.assertEqual(state.db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(state.status()["push_retry_at"], 1600)
        self.assertFalse(state.observe(True, 1015))
        self.assertEqual(state.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)
        self.assertEqual(state.db.execute("SELECT COUNT(*) FROM history").fetchone()[0], 1)

    def test_failed_migration_rolls_back_all_columns_and_can_be_retried(self):
        self.make_v1()
        db = sqlite3.connect(self.config.state_dir / "state.sqlite3")
        alters = [0]
        def authorize(action, *args):
            if action == sqlite3.SQLITE_ALTER_TABLE:
                alters[0] += 1
                if alters[0] == 2:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        db.set_authorizer(authorize)
        with patch("roblox_presence.state.sqlite3.connect", return_value=db), self.assertRaises(sqlite3.DatabaseError):
            State(self.config, 1010)
        with contextlib.closing(sqlite3.connect(self.config.state_dir / "state.sqlite3")) as reader:
            columns = [r[1] for r in reader.execute("PRAGMA table_info(monitor)")]
            self.assertNotIn("offline_since", columns)
            self.assertEqual(reader.execute("PRAGMA user_version").fetchone()[0], 1)
        state = self.db()
        self.assertEqual(state.status()["push_retry_at"], 1600)

    def test_snapshot_is_read_only_scoped_and_does_not_read_credentials(self):
        state = self.db()
        now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc).timestamp()
        state.observe(False, now)
        self.cookie.unlink()
        self.topic.unlink()
        before = state.db.total_changes
        data = snapshot(self.config, now + 1, ZoneInfo("UTC"))
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(state.db.total_changes, before)
        self.assertEqual(data["rows"][0]["event"], "first_offline")

    def test_new_install_does_not_claim_old_history(self):
        self.db()
        data = snapshot(self.config, 2000, ZoneInfo("UTC"))
        text = render(data, 2000, ZoneInfo("UTC"), "UTC")
        self.assertIn("No recorded activity yet", text)
        self.assertEqual(text.count('class="daylabel"'), 14)
        self.assertIn("0%", text)

    def test_graph_command_end_to_end_without_credentials_or_state_changes(self):
        import time
        state = self.db()
        now = time.time()
        state.observe(True, now - 30, details=DETAILS)
        state.observe(False, now - 15)
        state.observe(False, now)
        config = json.loads((ROOT / "config.example.json").read_text())
        config.update(observer_user_id=11, target_user_id=22, state_dir=str(self.config.state_dir))
        config["cookie_file"] = str(self.root / "absent-cookie")
        path = self.root / "config.json"
        path.write_text(json.dumps(config))
        output = self.root / "report.html"
        before = state.db.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        with patch.dict(os.environ, TZ="Europe/Paris"), contextlib.redirect_stdout(io.StringIO()) as console:
            self.assertEqual(main(["graph", "--file-only", "--config", str(path), "--output", str(output)]), 0)
        text = output.read_text()
        self.assertIn(output.resolve().as_uri(), console.getvalue())
        self.assertIn("Example Player", text)
        self.assertIn("Server time:", text)
        self.assertIn("Europe/Paris", text)
        self.assertNotIn("TEST_OBSERVER_SESSION", text)
        self.assertNotIn(self.topic.read_text(), text)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(state.db.execute("SELECT COUNT(*) FROM history").fetchone()[0], before)


class DetailTests(Fixture):
    def test_names_visible_game_are_durable_and_cookie_free(self):
        state = self.db()
        state.observe(True, 1000, details=DETAILS)
        self.state.close()
        self.state = State(self.config, 1005)
        event = self.state.next_event(1005)
        title, body = message(event)
        self.assertIn("Example Player (@ExampleConnection)", title)
        self.assertIn("Example Adventure", body)
        self.assertNotIn("TEST_OBSERVER_SESSION", json.dumps(event))
        self.assertIn("server time", body)

    def test_game_followup_once_per_session_and_survives_restart(self):
        state = self.db()
        state.observe(True, 1000, details={"username": "ExampleConnection"})
        event = state.next_event(1000)
        state.delivered(event, 1001)
        self.assertTrue(state.observe(True, 1015, details=DETAILS))
        followup = state.next_event(1015)
        self.assertEqual(followup["kind"], "playing")
        state.delivered(followup, 1016)
        self.state.close()
        self.state = State(self.config, 1020)
        self.assertFalse(self.state.observe(True, 1030, details={**DETAILS, "game_name": "Another Adventure"}))
        self.assertIsNone(self.state.next_event(1030))
        self.state.observe(False, 1045)
        self.state.observe(False, 1060)
        self.assertTrue(self.state.observe(True, 1075, details=DETAILS))

    def test_pending_online_enriched_without_extra_notification(self):
        state = self.db()
        state.observe(True, 1000)
        self.assertFalse(state.observe(True, 1015, details=DETAILS))
        self.assertEqual(state.status()["pending_notifications"], 1)
        self.assertIn("Example Adventure", message(state.next_event(1015))[1])
        self.assertEqual(json.loads(state.next_event(1015)["details"])["observed_at"], 1015)

    def test_first_game_is_not_lost_when_an_old_online_message_is_in_flight(self):
        state = self.db()
        state.observe(True, 1000)
        in_flight = state.next_event(1000)
        state.observe(True, 1015, details=DETAILS)
        state.delivered(in_flight, 1016)
        followup = state.next_event(1016)
        self.assertEqual(followup["kind"], "playing")
        self.assertEqual(json.loads(followup["details"])["observed_at"], 1015)
        self.assertIn("Example Adventure", message(followup)[1])
        state.delivered(followup, 1017)
        state.observe(True, 1030, details=DETAILS)
        self.assertIsNone(state.next_event(1030))

    def test_silent_startup_does_not_send_game_followup(self):
        import dataclasses
        self.config = dataclasses.replace(self.config, notify_on_startup=False)
        state = self.db()
        state.observe(True, 1000)
        self.assertFalse(state.observe(True, 1015, details=DETAILS))
        self.assertIsNone(state.next_event(1015))

    def test_game_followup_cancelled_offline_and_paused_during_unknown(self):
        state = self.db()
        state.observe(True, 1000)
        state.delivered(state.next_event(1000), 1001)
        state.observe(True, 1015, details=DETAILS)
        event = state.next_event(1015)
        state.failed("network_error", 1020)
        self.assertFalse(state.eligible(event, 1020))
        state.observe(False, 1035)
        state.observe(False, 1050)
        self.assertFalse(state.eligible(event, 1050))

    def test_type_and_game_privacy_are_respected(self):
        for kind, location, expected in ((0, "Old Adventure", ""), (1, "Website", ""), (2, None, ""), (2, "Playing", ""), (2, "Adventure", "Adventure"), (3, "Studio place", "")):
            source = Roblox(self.config, FakeHttp([response({"id": 11}), response({"userPresences": [{"userId": 22, "userPresenceType": kind, "lastLocation": location}]})]))
            source.poll()
            self.assertEqual(source.details["game_name"], expected)
        title, body = message({"kind": "online", "created_at": 1000, "details": {"presence_type": "in_game"}})
        self.assertIn("not shared its name", body)

    def test_profile_failure_does_not_change_presence_and_obeys_retry_floor(self):
        http = FakeHttp([response({}, 429, {"retry-after": "900"})])
        source = Roblox(self.config, http)
        source.details = {"presence_type": "in_game", "game_name": "Example Adventure"}
        with patch("roblox_presence.roblox.time.monotonic", return_value=1000):
            self.assertEqual(source.notification_details()["game_name"], "Example Adventure")
        with patch("roblox_presence.roblox.time.monotonic", return_value=1800):
            source.notification_details()
        self.assertEqual(source.profile_retry_at, 1900)
        self.assertEqual(len(http.calls), 1)
        self.assertNotIn("Cookie", http.calls[0][2].get("headers", {}))


class ReportTests(unittest.TestCase):
    def data(self, zone="UTC", day="2026-10-15T12:00:00+00:00"):
        now = datetime.fromisoformat(day).timestamp()
        rows = [{"observed_at": now - 7200, "kind": "online", "event": "online", "event_at": now - 7200},
                {"observed_at": now - 7185, "kind": "online", "event": None, "event_at": None},
                {"observed_at": now - 7170, "kind": "offline", "event": "offline", "event_at": now - 7170}]
        return now, ZoneInfo(zone), {"rows": rows, "details": DETAILS}

    def test_report_escapes_api_text_and_has_no_remote_assets(self):
        now, zone, data = self.data()
        data["details"] = {"display_name": '<script>alert("x")</script>'}
        result = render(data, now, zone, "UTC")
        self.assertNotIn('<script>alert', result)
        self.assertIn('&lt;script&gt;', result)
        self.assertNotIn('src="http', result)
        self.assertNotIn('href="http', result)
        self.assertIn("connect-src 'none'", result)
        self.assertIn("script-src 'sha256-", result)
        self.assertEqual(result.count('class="daylabel"'), 14)

    def test_dst_fall_and_spring_have_correct_local_times_and_day_axes(self):
        for day, first, second in (("2026-10-25T12:00:00+00:00", "2026-10-25T00:30:00+00:00", "2026-10-25T01:30:00+00:00"),
                                   ("2026-03-29T12:00:00+00:00", "2026-03-29T00:30:00+00:00", "2026-03-29T01:30:00+00:00")):
            now, zone, data = self.data("Europe/Paris", day)
            data["rows"][0].update(observed_at=datetime.fromisoformat(first).timestamp(), event_at=datetime.fromisoformat(first).timestamp())
            data["rows"] = [data["rows"][0], {"observed_at": datetime.fromisoformat(second).timestamp(), "kind": "offline", "event": "offline", "event_at": datetime.fromisoformat(second).timestamp()}]
            text = render(data, now, zone, "Europe/Paris")
            self.assertIn("UTC+0200", text)
            self.assertIn("UTC+0100", text)
            self.assertIn("clock change", text)
            self.assertEqual(intervals(data["rows"], now, 60), [])

    def test_private_atomic_export_refresh_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.html"
            with patch.dict(os.environ, {}, clear=True):
                export_report("old", output)
                export_report("new", output)
                self.assertEqual(output.read_text(), "new")
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                target = Path(folder) / "keep.html"
                target.write_text("keep")
                output.unlink()
                output.symlink_to(target)
                with self.assertRaises(ConfigError):
                    export_report("overwrite", output)
                self.assertEqual(target.read_text(), "keep")

    def test_timezone_uses_explicit_server_override_not_browser(self):
        with patch.dict(os.environ, TZ="Europe/Paris"):
            zone, label = server_zone()
            self.assertEqual(label, "Europe/Paris")
        with patch.dict(os.environ, TZ="Not/A_Zone"), self.assertRaises(ConfigError):
            server_zone()

    def test_cli_help_all_commands_both_spellings_no_config_needed(self):
        for name in ("robox", "roblox"):
            result = subprocess.run([str(ROOT / name), "--help"], cwd="/tmp", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for command in ("graph", "check", "status", "test-push", "run", "subscription", "init", "resolve", "set-cookie", "validate", "help"):
                self.assertIn(command, result.stdout)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["help"]), 0)
        self.assertIn("14-day graph", output.getvalue())
