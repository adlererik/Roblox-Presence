"""Temporary, token-protected viewing of one report held in memory.

Loopback by default. A specific private-network address must be requested for
another device. No directory listing, file lookup, credentials or access logs.
"""

import hmac
import ipaddress
import os
import pwd
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
from urllib.parse import urlsplit

from .config import ConfigError, listen_address


def drop_privileges():
    """The CLI has finished reading private state before the viewer can listen."""
    if os.geteuid() != 0:
        return
    caller = os.environ.get("SUDO_UID", "")
    if not caller.isdecimal() or int(caller) == 0:
        raise ConfigError("Run the viewer as a regular user or through sudo from that user's terminal")
    identity = pwd.getpwuid(int(caller))
    os.setgroups([])
    os.setgid(identity.pw_gid)
    os.setuid(identity.pw_uid)


def validate_options(port, lifetime):
    if type(port) is not int or not (port == 0 or 1024 <= port <= 65535):
        raise ConfigError("--port must be 0 (choose a free port) or between 1024 and 65535")
    if type(lifetime) is not int or not 60 <= lifetime <= 3600:
        raise ConfigError("--minutes must be between 1 and 60")


class ReportServer(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 8
    request_timeout = 3

    def server_bind(self):
        TCPServer.server_bind(self)
        # HTTPServer normally reverse-resolves the bind IP here. A private
        # report must not delay monitor startup waiting for a DNS/PTR lookup.
        self.server_name, self.server_port = self.socket.getsockname()[:2]

    def __init__(self, content, address="127.0.0.1", port=0, lifetime=600, *, clock=time.monotonic):
        address = listen_address(address)
        validate_options(port, lifetime)
        self.address_family = socket.AF_INET6 if ":" in address else socket.AF_INET
        self.content = content.encode("utf-8")
        self.clock, self.expires = clock, clock() + lifetime
        self.token_path = "/" + secrets.token_hex(32) + "/"
        self.allowed_hosts = {address, "localhost", "127.0.0.1", "::1"}
        super().__init__((address, port), ReportHandler)
        self.timeout = 0.5

    @property
    def url(self):
        address, port = self.server_address[:2]
        host = "[" + address + "]" if ":" in address else address
        return f"http://{host}:{port}{self.token_path}"

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.request_timeout)
        return connection, address

    def process_request(self, request, client_address):
        # A socket timeout alone restarts on every byte. An absolute deadline
        # also bounds a client slowly dribbling headers past the link's expiry.
        def interrupt():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = min(self.request_timeout, max(0.1, self.expires - self.clock()))
        timer = threading.Timer(deadline, interrupt)
        timer.daemon = True
        timer.start()
        try:
            super().process_request(request, client_address)
        finally:
            timer.cancel()

    def handle_error(self, request, client_address):
        pass  # Never log private URLs, remote input, or report content.

    def serve_until_expiry(self):
        while self.clock() < self.expires:
            self.handle_request()
            time.sleep(0.1)  # Bound request churn in this small, single-request viewer.


class ReportHandler(BaseHTTPRequestHandler):
    server_version = "RobloxPresenceReport"
    sys_version = ""

    def log_message(self, *args):
        pass

    def _respond(self, status, body=b"", content_type="text/plain; charset=utf-8", *, head=False, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Connection", "close")
        for key, value in headers:
            self.send_header(key, value)
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if not head:
            self.wfile.write(body)
        self.close_connection = True

    def valid_host(self):
        hosts = self.headers.get_all("Host", [])
        try:
            host = urlsplit("http://" + hosts[0]) if len(hosts) == 1 else None
            valid_host = (host is not None and host.hostname in self.server.allowed_hosts
                          and not host.username and not host.password and not host.path
                          and not host.query and not host.fragment and host.port is not None)
        except ValueError:
            valid_host = False
        return valid_host

    def _report(self, *, head=False):
        if not self.valid_host():
            return self._respond(403, b"Host not permitted.\n", head=head)
        if self.server.clock() >= self.server.expires:
            return self._respond(410, b"This report link expired. Generate a fresh graph.\n", head=head)
        if not hmac.compare_digest(self.path.encode("utf-8"), self.server.token_path.encode("ascii")):
            return self._respond(404, b"Report not found.\n", head=head)
        return self._respond(200, self.server.content, "text/html; charset=utf-8", head=head)

    def do_GET(self):
        self._report()

    def do_HEAD(self):
        self._report(head=True)

    def do_POST(self):
        self._respond(405, b"Only GET and HEAD are supported.\n")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST


def serve(content, address="127.0.0.1", port=0, minutes=10):
    address = listen_address(address)
    validate_options(port, minutes * 60)
    drop_privileges()
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        server = ReportServer(content, address, port, minutes * 60)
    except OSError:
        raise ConfigError("Cannot start the viewer at this address/port; choose this computer's private address and a free port") from None
    with server:
        print("Open graph (temporary browser link):", flush=True)
        print(server.url, flush=True)
        print(f"The link expires in {minutes} minutes. Keep this terminal open; Ctrl+C closes the viewer.", flush=True)
        if ipaddress.ip_address(address).is_loopback:
            print("This link works on this computer, or through your existing SSH port forwarding.", flush=True)
        else:
            print("Open on a device on the same trusted home network or existing private VPN.\n"
                  "This is HTTP: the secret link limits access but does not encrypt network traffic. Keep it private.", flush=True)
        try:
            server.serve_until_expiry()
        except KeyboardInterrupt:
            pass
    print("Viewer closed. Your saved HTML report is still available.", flush=True)


def file_link(path):
    """A valid URL, including spaces, Unicode and terminal-control characters."""
    return path.resolve().as_uri()


def print_file_link(path):
    print("Open saved graph (on the computer holding this file):")
    print(file_link(path))
    # Sudo may strip SSH_*; a headless sudo invocation still needs this distinction.
    print("For a phone or an SSH client, use graph --listen SERVER_PRIVATE_ADDRESS\n"
          "to get a temporary browser link, or download the file first.")
