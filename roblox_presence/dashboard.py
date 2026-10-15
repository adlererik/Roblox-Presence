"""Opt-in private dashboard, supervised with the unprivileged monitor.

Only a saved report and a small command API are exposed. No file browser,
credential endpoint, access logging, or external resources.
"""

import hmac
import base64
import hashlib
import html
import json
import logging
import os
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

from .config import ConfigError, secret
from .report import render, server_zone, snapshot
from .state import read_health
from .viewer import ReportHandler, ReportServer

MAX_REPORT = 32 * 1024 * 1024
CONTROL_SCRIPT = """document.getElementById('generate-form').addEventListener('submit',async function(event){
event.preventDefault();const button=this.querySelector('button'),status=document.getElementById('generation-status');
button.disabled=true;status.textContent='Requesting a new graph…';
try{const response=await fetch('generate',{method:'POST',body:new URLSearchParams(new FormData(this)),
headers:{Accept:'application/json'},redirect:'error'});
if(!response.ok)throw new Error();window.location.reload();}
catch(error){status.textContent='Could not request a graph. Wait ten seconds, then refresh this page and try again.';button.disabled=false;}
});"""


def generate_snapshot(config, now):
    # A fresh interpreter inherits no SQLite handles, locks, credential environment
    # or report key. malloc avoids large reserved arenas defeating RLIMIT_AS.
    environment = {'PATH': os.defpath, 'PYTHONMALLOC': 'malloc', 'PYTHONIOENCODING': 'utf-8',
                   'PYTHONUTF8': '1', 'LANG': 'C', 'LC_ALL': 'C'}
    for key in ('TZ',):
        if key in os.environ:
            environment[key] = os.environ[key]
    data = {'observer_user_id': config.observer_user_id, 'target_user_id': config.target_user_id,
            'state_dir': str(config.state_dir), 'poll_seconds': config.poll_seconds, 'now': now}
    worker = subprocess.Popen([sys.executable, '-B', '-m', 'roblox_presence.report_worker'],
                              cwd=Path(__file__).resolve().parents[1], env=environment,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        payload, _ = worker.communicate(json.dumps(data).encode(), timeout=60)
        if worker.returncode != 0 or not payload or len(payload) > MAX_REPORT:
            raise ConfigError("Graph worker did not complete")
        return payload.decode('utf-8')
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.communicate()


def saved_report(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return "", None
    with os.fdopen(fd, "r") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > MAX_REPORT):
            raise ConfigError("Saved dashboard report has unsafe permissions or size")
        return stream.read(), info.st_mtime


def save_report(path, content):
    if len(content.encode()) > MAX_REPORT:
        raise ConfigError("Report is too large; the previous snapshot was kept")
    temporary = path.with_name(".dashboard-" + secrets.token_hex(12))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class DashboardServer(ReportServer):
    allow_reuse_address = True  # Restart our listener without waiting for TIME_WAIT.

    def __init__(self, config, key, *, port=None):
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ConfigError("Dashboard key must be 256 random bits in hexadecimal")
        self.config = config
        self.report_path = config.state_dir / "dashboard-report.html"
        content, generated_at = saved_report(self.report_path)
        super().__init__(content, config.graph_listen_address,
                         config.dashboard_port if port is None else port, lifetime=3600)
        self.expires = float("inf")
        self.token_path = "/" + key + "/"
        self.RequestHandlerClass = DashboardHandler
        self.csrf = secrets.token_hex(32)
        self.generated_at, self.error = generated_at, None
        self.lock, self.stopping = threading.Lock(), threading.Event()
        self.job = None
        self.last_requested = float("-inf")

    def state(self):
        try:
            health = read_health(self.config, time.time())
            health = {key: health.get(key) for key in ("healthy", "stable_online", "last_success",
                      "updated_at", "last_error", "push_last_error", "pending_notifications")}
        except ConfigError:
            health = {"healthy": False, "last_error": "health_unavailable"}
        with self.lock:
            return {"csrf": self.csrf, "generating": bool(self.job and self.job.is_alive()),
                    "error": self.error, "generated_at": self.generated_at, "monitor": health}

    def generate(self):
        with self.lock:
            if self.job and self.job.is_alive():
                return True
            if time.monotonic() - self.last_requested < 10:
                return False
            self.last_requested, self.error = time.monotonic(), None
            self.job = threading.Thread(target=self._generate, name="graph-generation", daemon=True)
            self.job.start()
            return True

    def _generate(self):
        try:
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 19)
            except OSError:
                pass
            now = time.time()
            content = generate_snapshot(self.config, now)
            save_report(self.report_path, content)
            with self.lock:
                self.content, self.generated_at = content.encode(), now
        except Exception:
            with self.lock:
                self.error = "Graph generation failed. The previous snapshot was kept; check monitor health."
            logging.getLogger("roblox_presence").warning("dashboard_generation_failed")

    def page(self):
        state = self.state()
        with self.lock:
            content = self.content.decode()
        status = ("Generating a new graph… This page refreshes while it is working."
                  if state["generating"] else state["error"] or
                  "Saved snapshot. Generate a new graph to include newer activity.")
        toolbar = (f'<section class="panel" aria-label="Graph controls"><h2>Your private activity page</h2>'
                   f'<p role="status" id="generation-status">{html.escape(status)}</p><form id="generate-form" method="post" action="generate">'
                   f'<input type="hidden" name="csrf" value="{self.csrf}">'
                   '<button class="reset" type="submit">Generate new graph</button></form>'
                   '<p><a href="report" download="roblox-presence.html">Download saved graph</a></p>'
                   '<p class="note">Bookmark this page. The link stays the same and needs no terminal. '
                   'Keep it private; use your trusted home network or existing private VPN/SSH.</p></section>')
        if not content:
            content = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                       '<meta name="viewport" content="width=device-width,initial-scale=1">'
                       '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                       'style-src \'unsafe-inline\'; form-action \'none\'; base-uri \'none\'">'
                       '<title>Roblox Presence · Activity</title><style>body{font:18px system-ui;'
                       'max-width:65rem;margin:2rem auto;padding:0 1rem;background:#f4f7fb;color:#17253a}'
                       'button{padding:1rem;font:inherit;cursor:pointer}.note{font-size:.9rem}</style>'
                       '</head><body><main><p>No graph saved yet. Use the button above to create one.</p>'
                       '</main></body></html>')
        content = content.replace("form-action 'none'", "form-action 'self'").replace('<main>', '<main>' + toolbar, 1)
        control_hash = base64.b64encode(hashlib.sha256(CONTROL_SCRIPT.encode()).digest()).decode()
        policy = "'sha256-" + control_hash + "'"
        if 'script-src ' in content:
            content = re.sub(r"script-src ([^;]+)", lambda match: match[0] + ' ' + policy, content, count=1)
        else:
            content = content.replace("form-action 'self'", "script-src " + policy + "; connect-src 'self'; form-action 'self'", 1)
        content = content.replace("connect-src 'none'", "connect-src 'self'")
        content = content.replace('</body>', '<script>' + CONTROL_SCRIPT + '</script></body>', 1)
        if state["generating"]:
            content = content.replace('</head>', '<meta http-equiv="refresh" content="2"></head>', 1)
        return content.encode()

    def run(self):
        while not self.stopping.is_set():
            self.handle_request()
            self.stopping.wait(0.1)


class DashboardHandler(ReportHandler):
    def route(self):
        if not self.valid_host():
            return None, 403
        base = self.server.token_path
        if not hmac.compare_digest(self.path[:len(base)].encode(), base.encode()):
            return None, 404
        route = self.path[len(base):]
        return (route, None) if route in ("", "state", "generate", "report") else (None, 404)

    def _get(self, head=False):
        route, error = self.route()
        if error:
            return self._respond(error, b"Page unavailable.\n", head=head)
        if route == "generate":
            return self._respond(405, b"Use the Generate new graph button.\n", head=head)
        if route == "state":
            return self._respond(200, json.dumps(self.server.state()).encode(), "application/json", head=head)
        if route == "report":
            with self.server.lock:
                content = self.server.content
            return self._respond(200 if content else 404, content, "text/html; charset=utf-8", head=head)
        return self._respond(200, self.server.page(), "text/html; charset=utf-8", head=head)

    def do_GET(self):
        self._get()

    def do_HEAD(self):
        self._get(head=True)

    def do_POST(self):
        route, error = self.route()
        if error or route != "generate":
            return self._respond(error or 405, b"Request refused.\n")
        origins = self.headers.get_all("Origin", [])
        if (len(origins) > 1 or (origins and origins[0] != "http://" + self.headers["Host"])
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            return self._respond(403, b"Use this private page to generate a graph.\n")
        lengths = self.headers.get_all("Content-Length", [])
        if (self.headers.get("Transfer-Encoding") or len(lengths) != 1
                or not lengths[0].isdecimal() or not 1 <= int(lengths[0]) <= 256
                or len(self.headers.get_all('Content-Type', [])) != 1
                or self.headers.get_content_type() != "application/x-www-form-urlencoded"):
            return self._respond(400, b"Invalid form.\n")
        try:
            form = parse_qs(self.rfile.read(int(lengths[0])).decode('ascii'), strict_parsing=True)
            valid = (set(form) == {"csrf"} and len(form["csrf"]) == 1
                     and hmac.compare_digest(form["csrf"][0].encode(), self.server.csrf.encode()))
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            return self._respond(403, b"Refresh the page and use Generate new graph.\n")
        if not self.server.generate():
            return self._respond(429, b"Please wait ten seconds between graphs.\n", headers=(("Retry-After", "10"),))
        if self.headers.get('Accept') == 'application/json':
            return self._respond(202, b'{"generating":true}', 'application/json')
        return self._respond(303, headers=(("Location", self.server.token_path),))


def start(config):
    if not config.dashboard_port:
        return None
    server = DashboardServer(config, secret(config.dashboard_key_file))
    server.thread = threading.Thread(target=server.run, name="private-dashboard", daemon=True)
    server.thread.start()
    return server


def stop(server):
    if server is not None:
        server.stopping.set()
        server.thread.join(4)
        server.server_close()
