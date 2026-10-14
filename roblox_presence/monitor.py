"""Independent polling and delivery loops, graceful shutdown, bounded backoff."""

import logging
import random
import signal
import socket
import threading
import time

from .config import ConfigError
from .http import Http, ServiceError
from .push import Push
from .roblox import Roblox
from .state import State, process_lock

LOG = logging.getLogger("roblox_presence")


def delay(failures, base=15, cap=300, minimum=None, jitter=random.uniform):
    seconds = min(cap, base * 2 ** min(max(0, failures - 1), 12))
    # Retry-After is a floor; jitter never causes an early retry.
    return max(seconds * jitter(1, 1.1), minimum or 0)


def systemd_notify(value):
    import os
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return
    if path.startswith("@"):
        path = "\0" + path[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(path)
        sock.sendall(value.encode())


class Monitor:
    def __init__(self, config, state, source, push, *, clock=time.time, monotonic=time.monotonic):
        self.config, self.state, self.source, self.push = config, state, source, push
        self.clock, self.monotonic = clock, monotonic
        self.stop, self.wake = threading.Event(), threading.Event()
        self.poll_failures, self.push_failures = 0, 0
        self.next_push_at = 0.0

    def poll_once(self):
        try:
            online = self.source.poll()
        except (ServiceError, ConfigError) as exc:
            code = exc.code if isinstance(exc, ServiceError) else "roblox_credential_unavailable"
            self.state.failed(code, self.clock())
            self.wake.set()
            self.poll_failures += 1
            LOG.warning("presence_check_failed code=%s", code)
            return delay(self.poll_failures, base=self.config.poll_seconds,
                         minimum=getattr(exc, "retry_after", None))
        queued = self.state.observe(online, self.clock())
        if self.poll_failures:
            LOG.info("presence_checks_recovered")
        self.poll_failures = 0
        if queued:
            LOG.info("online_transition_queued")
        self.wake.set()
        return self.config.poll_seconds

    def deliver_once(self):
        now = self.clock()
        event = self.state.next_event(now)
        if self.monotonic() < self.next_push_at or event is None or not self.state.eligible(event, now):
            return False
        try:
            self.push.send(event)
        except (ServiceError, ConfigError) as exc:
            code = exc.code if isinstance(exc, ServiceError) else "push_credential_unavailable"
            self.push_failures += 1
            retry = delay(self.push_failures, base=5, minimum=getattr(exc, "retry_after", None))
            if getattr(exc, "status", None) in (400, 401, 403, 404):
                retry = max(retry, 300)
            self.next_push_at = self.monotonic() + retry
            self.state.retry(event, code, self.clock(), retry)
            LOG.warning("push_failed code=%s", code)
            return False
        self.state.delivered(event, self.clock())
        self.push_failures, self.next_push_at = 0, 0.0
        LOG.info("push_accepted kind=%s", event["kind"])
        return True

    def delivery_loop(self):
        next_health = 0.0
        try:
            while not self.stop.is_set():
                self.deliver_once()
                if self.monotonic() >= next_health:
                    self.state.write_health(self.clock())
                    next_health = self.monotonic() + 5
                self.wake.wait(0.5)
                self.wake.clear()
        except Exception:
            # Do not print arbitrary exception strings, which may contain credentials.
            LOG.error("delivery_worker_failed")
            self.stop.set()

    def run(self):
        worker = threading.Thread(target=self.delivery_loop, name="push-delivery", daemon=True)
        worker.start()
        systemd_notify("READY=1\nSTATUS=Presence monitor running")
        try:
            while not self.stop.is_set():
                wait = self.poll_once()
                deadline = self.monotonic() + wait
                while not self.stop.is_set() and self.monotonic() < deadline:
                    heartbeat = self.state.status()["worker_heartbeat"]
                    if heartbeat is not None and self.clock() - heartbeat > 60:
                        raise ServiceError("delivery_worker_stalled")
                    systemd_notify("WATCHDOG=1")
                    self.stop.wait(min(10, max(0, deadline - self.monotonic())))
        finally:
            self.stop.set()
            self.wake.set()
            worker.join(timeout=self.config.timeout_seconds + 5)
            systemd_notify("STOPPING=1")
        if worker.is_alive():
            raise ServiceError("delivery_worker_did_not_stop")
        if not getattr(self, "shutdown_requested", False):
            raise ServiceError("monitor_worker_stopped")


def run(config):
    with process_lock(config.state_dir):
        state = State(config, time.time())
        monitor = Monitor(config, state, Roblox(config, Http(config.timeout_seconds)),
                          Push(config, Http(config.timeout_seconds)))

        def shutdown(signum, frame):
            monitor.shutdown_requested = True
            monitor.stop.set()
            monitor.wake.set()

        previous = {s: signal.signal(s, shutdown) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            # Target validation is performed by 'check' before activation; runtime
            # polling validates the observer on every cycle and the result's target ID.
            monitor.run()
        finally:
            if not any(t.name == "push-delivery" and t.is_alive() for t in threading.enumerate()):
                state.close()
            for s, handler in previous.items():
                signal.signal(s, handler)
