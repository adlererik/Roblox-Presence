"""Atomic presence transitions and a durable, bounded notification outbox."""

import fcntl
import json
import os
import sqlite3
import stat
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .config import ConfigError
from .roblox import clean_text


def preserve_sqlite_owner(path, owner):
    """Root diagnostics can create WAL sidecars even with SQLite mode=ro.

    Return any such regular files to the existing database owner, keeping 0600,
    so a subsequent unprivileged monitor start can still use its own database.
    """
    if os.geteuid() != 0 or owner.st_uid == 0:
        return
    for suffix in ("-wal", "-shm"):
        try:
            fd = os.open(str(path) + suffix, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            continue
        try:
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0:
                os.fchmod(fd, 0o600)
                os.fchown(fd, owner.st_uid, owner.st_gid)
        finally:
            os.close(fd)


@contextmanager
def process_lock(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "monitor.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConfigError("A monitor instance is already running for this state directory") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class State:
    def __init__(self, config, now):
        self.config, self.lock = config, threading.RLock()
        self.maintenance_at = 0.0
        config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(config.state_dir / "state.sqlite3", timeout=5,
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2):
            self.db.close()
            raise ConfigError("Unsupported state schema; preserve the state directory")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS monitor (
                scope TEXT PRIMARY KEY, created_at REAL NOT NULL,
                stable_online INTEGER, offline_samples INTEGER NOT NULL DEFAULT 0,
                session_id TEXT, last_attempt REAL, last_success REAL, last_error TEXT,
                outage_started REAL, outage_alerted INTEGER NOT NULL DEFAULT 0,
                push_last_success REAL, push_last_error TEXT, worker_heartbeat REAL,
                push_retry_at REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
                session_id TEXT, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                due_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending', completed_at REAL, error TEXT
            );
            CREATE INDEX IF NOT EXISTS outbox_due ON outbox(scope, status, due_at);
        """)
        try:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                if version < 2:
                    # Additive migration: preserve sessions, pending deliveries and retry floors.
                    for definition in ("offline_since REAL", "details TEXT NOT NULL DEFAULT '{}'",
                                       "game_notified INTEGER NOT NULL DEFAULT 0"):
                        self.db.execute("ALTER TABLE monitor ADD COLUMN " + definition)
                    self.db.execute("ALTER TABLE outbox ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
                self.db.execute("CREATE TABLE IF NOT EXISTS history ("
                                "id INTEGER PRIMARY KEY, scope TEXT NOT NULL, observed_at REAL NOT NULL, "
                                "kind TEXT NOT NULL, event TEXT, event_at REAL)")
                self.db.execute("CREATE INDEX IF NOT EXISTS history_time ON history(scope,observed_at)")
                self.db.execute("PRAGMA user_version=2")
                self.db.execute("INSERT OR IGNORE INTO monitor(scope,created_at) VALUES (?,?)",
                                (config.scope, now))
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _row(self):
        return dict(self.db.execute("SELECT * FROM monitor WHERE scope=?",
                                    (self.config.scope,)).fetchone())

    def _event(self, kind, now, session=None, details=None):
        ttl = self.config.alert_ttl_seconds if kind in ("online", "playing") else 3600
        self.db.execute("INSERT INTO outbox(id,scope,kind,session_id,created_at,expires_at,due_at,details) "
                        "VALUES(?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, self.config.scope, kind,
                                                 session, now, now + ttl, now, json.dumps(details or {})))

    def _sample(self, now, kind, event=None, event_at=None):
        self.db.execute("INSERT INTO history(scope,observed_at,kind,event,event_at) VALUES(?,?,?,?,?)",
                        (self.config.scope, now, kind, event, event_at))

    def observe(self, online, now, *, details=None):
        """One verified observation. Return whether a new online event was committed."""
        if type(online) is not bool:
            raise ValueError("Observation must be a boolean")
        details = {key: clean_text((details or {}).get(key), limit) for key, limit in
                   (("username", 40), ("display_name", 80), ("game_name", 160), ("presence_type", 20))}
        if not online:
            details["game_name"] = ""
        with self.lock, self.db:
            old = self._row()
            stable, samples, session = old["stable_online"], old["offline_samples"], old["session_id"]
            offline_since, game_notified = old["offline_since"], old["game_notified"]
            event, event_at = None, None
            kind = "online" if online else "pending"
            queued = False
            if old["last_success"] is None or now - old["last_success"] > max(60, 3 * self.config.poll_seconds):
                samples, offline_since = 0, None
            previous_details = json.loads(old["details"])
            for key in ("username", "display_name"):
                details[key] = details[key] or previous_details.get(key, "")
            if online:
                samples, offline_since = 0, None
                if stable != 1:
                    session = uuid.uuid4().hex
                    event, event_at = ("first_online" if stable is None else "online"), now
                    game_notified = int(bool(details["game_name"]))
                    if stable is not None or self.config.notify_on_startup:
                        self._event("online", now, session, details)
                        queued = True
                    else:
                        game_notified = 1  # Silent startup also silences its game follow-up.
                elif details["game_name"] and not game_notified:
                    pending = self.db.execute("SELECT id FROM outbox WHERE scope=? AND session_id=? "
                                              "AND kind='online' AND status='pending' AND expires_at>?",
                                              (self.config.scope, session, now)).fetchone()
                    if pending:
                        self.db.execute("UPDATE outbox SET details=? WHERE id=?",
                                        (json.dumps({**details, "observed_at": now}), pending[0]))
                    else:
                        self._event("playing", now, session, details)
                        queued = True
                    game_notified = 1
                stable = 1
            else:
                if not samples:
                    offline_since = now
                samples = min(samples + 1, self.config.offline_confirmations)
                if stable is None or samples >= self.config.offline_confirmations:
                    if stable != 0:
                        event = "first_offline" if stable is None else "offline"
                        event_at = offline_since
                    kind = "offline"
                    # Backdate only the consecutive, verified offline candidates.
                    # A failed check resets offline_since, so an outage cannot close a session.
                    if stable != 0:
                        self.db.execute("UPDATE history SET kind='offline' WHERE scope=? AND kind='pending' "
                                        "AND observed_at>=?", (self.config.scope, offline_since))
                    stable, session = 0, None
                    game_notified = 0
                    self.db.execute("UPDATE outbox SET status='cancelled',completed_at=? "
                                    "WHERE scope=? AND kind IN ('online','playing') AND status='pending'",
                                    (now, self.config.scope))
                elif stable == 0:
                    kind = "offline"
            self._sample(now, kind, event, event_at)
            if old["outage_alerted"]:
                self._event("recovery", now)
            self.db.execute("UPDATE outbox SET status='cancelled',completed_at=? "
                            "WHERE scope=? AND kind='outage' AND status='pending'", (now, self.config.scope))
            self.db.execute("UPDATE monitor SET stable_online=?,offline_samples=?,session_id=?,"
                            "offline_since=?,details=?,game_notified=?,"
                            "last_attempt=?,last_success=?,last_error=NULL,outage_started=NULL,outage_alerted=0 "
                            "WHERE scope=?", (stable, samples, session, offline_since, json.dumps(details),
                                             game_notified, now, now, self.config.scope))
            return queued

    def failed(self, code, now):
        with self.lock, self.db:
            self._sample(now, "unknown")
            old = self._row()
            started = old["outage_started"] if old["outage_started"] is not None else now
            alerted = old["outage_alerted"]
            if not alerted and now - started >= self.config.outage_alert_seconds:
                self._event("outage", now)
                alerted = 1
            # A failed request is unknown, never an offline observation.
            self.db.execute("UPDATE monitor SET last_attempt=?,last_error=?,offline_samples=0,offline_since=NULL,"
                            "outage_started=?,outage_alerted=? WHERE scope=?",
                            (now, code, started, alerted, self.config.scope))

    def next_event(self, now):
        with self.lock, self.db:
            row = self._row()
            heartbeat = row["worker_heartbeat"]
            if heartbeat is None or now < heartbeat or now - heartbeat >= 5:
                self.db.execute("UPDATE monitor SET worker_heartbeat=? WHERE scope=?", (now, self.config.scope))
            if now < self.maintenance_at or now - self.maintenance_at >= 60:
                self.db.execute("UPDATE outbox SET status='expired',completed_at=? "
                                "WHERE status='pending' AND expires_at<=?", (now, now))
                self.db.execute("DELETE FROM outbox WHERE completed_at<?", (now - 7 * 86400,))
                # Fifteen days cover fourteen local calendar dates across DST changes.
                self.db.execute("DELETE FROM history WHERE observed_at<?", (now - 15 * 86400,))
                self.maintenance_at = now
            if now < row["push_retry_at"]:
                return None
            row = self.db.execute("SELECT * FROM outbox WHERE scope=? AND status='pending' AND due_at<=? AND expires_at>? "
                                  "ORDER BY CASE kind WHEN 'online' THEN 0 ELSE 1 END,created_at LIMIT 1",
                                  (self.config.scope, now, now)).fetchone()
            return dict(row) if row else None

    def eligible(self, event, now):
        with self.lock:
            row = self.db.execute("SELECT status,expires_at FROM outbox WHERE id=?", (event["id"],)).fetchone()
            if not row or row["status"] != "pending" or row["expires_at"] <= now:
                return False
            if event["kind"] in ("online", "playing"):
                monitor = self._row()
                return (monitor["stable_online"] == 1 and monitor["offline_samples"] == 0
                        and monitor["session_id"] == event["session_id"]
                        and monitor["last_success"] is not None
                        and now - monitor["last_success"] <= max(60, 3 * self.config.poll_seconds)
                        and monitor["last_error"] is None)
            return True

    def delivered(self, event, now):
        with self.lock, self.db:
            latest = self.db.execute("SELECT details FROM outbox WHERE id=?", (event["id"],)).fetchone()
            monitor = self._row()
            if (event["kind"] == "online" and latest and latest["details"] != event.get("details", "{}")
                    and monitor["stable_online"] == 1 and monitor["session_id"] == event["session_id"]):
                details = json.loads(latest["details"])
                if details.get("game_name"):
                    # The worker may already have copied the old message before
                    # the poller enriched it. Don't lose the first visible game.
                    self._event("playing", now, event["session_id"], details)
            self.db.execute("UPDATE outbox SET status='sent',completed_at=?,error=NULL WHERE id=?",
                            (now, event["id"]))
            self.db.execute("UPDATE monitor SET push_last_success=?,push_last_error=NULL,push_retry_at=0 WHERE scope=?",
                            (now, self.config.scope))

    def retry(self, event, code, now, delay):
        with self.lock, self.db:
            self.db.execute("UPDATE outbox SET attempts=attempts+1,error=?,due_at=? "
                            "WHERE id=? AND status='pending'", (code, now + delay, event["id"]))
            self.db.execute("UPDATE monitor SET push_last_error=?,push_retry_at=? WHERE scope=?",
                            (code, now + delay, self.config.scope))

    def status(self):
        with self.lock:
            row = self._row()
            row.pop("session_id")
            row["pending_notifications"] = self.db.execute(
                "SELECT COUNT(*) FROM outbox WHERE scope=? AND status='pending'", (self.config.scope,)).fetchone()[0]
            return row

    def write_health(self, now):
        data = self.status()
        data["updated_at"] = now
        temporary = self.config.state_dir / "health.json.tmp"
        temporary.write_text(json.dumps(data, sort_keys=True) + "\n")
        os.chmod(temporary, 0o600)
        temporary.replace(self.config.state_dir / "health.json")


def read_health(config, now):
    try:
        data = json.loads((config.state_dir / "health.json").read_text())
    except (OSError, ValueError):
        raise ConfigError("No monitor health file is available yet") from None
    if not isinstance(data, dict) or data.get("scope") != config.scope:
        raise ConfigError("Health file does not match this configuration")
    stale = max(60, 3 * config.poll_seconds)
    last = data.get("last_success")
    data["healthy"] = bool(last is not None and 0 <= now - last <= stale
                           and 0 <= now - data.get("updated_at", 0) <= 15
                           and 0 <= now - (data.get("worker_heartbeat") or 0) <= 60
                           and not data.get("last_error") and not data.get("push_last_error"))
    return data
