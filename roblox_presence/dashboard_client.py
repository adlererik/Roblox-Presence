"""Unprivileged dashboard commands. Direct private-IP HTTP, no proxy or redirects."""

import http.client
import json
import os
import re
import stat
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .config import ConfigError, listen_address


def client_path():
    return Path.home() / ".config/roblox-presence/dashboard.json"


def validate_url(url):
    try:
        parsed = urlsplit(url)
        address = listen_address(parsed.hostname)
        valid = (parsed.scheme == "http" and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment and parsed.port is not None
                 and 1024 <= parsed.port <= 65535 and re.fullmatch(r"/[0-9a-f]{64}/", parsed.path))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ConfigError("Invalid private dashboard URL in client settings")
    host = "[" + address + "]" if ":" in address else address
    if url != f"http://{host}:{parsed.port}{parsed.path}":
        raise ConfigError("Use the exact numeric private dashboard URL")
    return parsed


def load_client(path=None):
    try:
        fd = os.open(path or client_path(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077
                    or info.st_uid != os.geteuid() or info.st_size > 4096):
                raise ConfigError("Dashboard client settings must be your own private regular file (0600)")
            obj = json.load(stream)
        if not isinstance(obj, dict) or set(obj) != {"url"}:
            raise ConfigError("Invalid dashboard client settings")
        validate_url(obj["url"])
        return obj["url"]
    except (OSError, ValueError, TypeError):
        raise ConfigError("Cannot read private dashboard client settings; ask the administrator to enable the dashboard") from None


def request(url, route, *, csrf=None):
    parsed = validate_url(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        body, headers = None, {}
        if csrf is not None:
            body = urlencode({"csrf": csrf}).encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded",
                       "Origin": "http://" + parsed.netloc}
        connection.request("POST" if csrf is not None else "GET", parsed.path + route, body, headers)
        response = connection.getresponse()
        data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024 or response.status not in (200, 303):
            if response.status == 429:
                raise ConfigError("Please wait ten seconds between graph requests")
            raise ConfigError("Dashboard request failed; check this monitor's service and private-network access")
        # Deliberately do not follow Location; never forward the secret to another site.
        return data
    except (OSError, http.client.HTTPException):
        raise ConfigError("Cannot reach the dashboard; check the monitor and your private-network connection") from None
    finally:
        connection.close()


def state(url):
    try:
        obj = json.loads(request(url, "state"))
        if not isinstance(obj, dict) or not isinstance(obj.get("csrf"), str):
            raise ValueError
        return obj
    except (ValueError, TypeError):
        raise ConfigError("Dashboard returned invalid status") from None


def generate(url, *, download=False):
    request(url, "generate", csrf=state(url)["csrf"])
    if not download:
        return None
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = state(url)
        if not result.get("generating"):
            if result.get("error"):
                raise ConfigError("Graph generation failed; the previous snapshot was kept")
            return request(url, "report").decode("utf-8")
        time.sleep(0.5)
    raise ConfigError("Graph is still being generated. Open your dashboard link to view progress")


def command(args, url):
    if args.command == "status":
        health = state(url)["monitor"]
        print(json.dumps(health, indent=2))
        return 0 if health.get("healthy") else 1
    if args.command == "graph":
        if args.listen or args.port or args.minutes != 10:
            raise ConfigError("Persistent dashboard address is set during installation; omit temporary-viewer options")
        content = generate(url, download=bool(args.file_only or args.output))
        if content is not None:
            from .report import export_report
            from .viewer import file_link
            output = export_report(content, args.output)
            print("Saved graph (file link works on this computer):")
            print(file_link(output))
        else:
            print("Graph requested. Open the page to see progress and the new snapshot.")
    print("Open your private dashboard (bookmark this link; no terminal needs to stay open):")
    print(url)
    print("The URL stays the same. The saved graph remains until you generate another. Keep the URL private.")
    return 0
