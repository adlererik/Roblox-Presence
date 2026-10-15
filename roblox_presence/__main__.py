"""Operator CLI. Secrets are entered interactively or through protected files."""

import argparse
import getpass
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path

from .config import ConfigError, listen_address, load, secret
from .http import Http, ServiceError
from .monitor import run
from .push import Push
from .roblox import Roblox, resolve_username
from .state import read_health
from . import __version__


def write_secret(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value + "\n")


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog=Path(sys.argv[0]).name if Path(sys.argv[0]).name in ("roblox", "robox") else "python3 -m roblox_presence",
                                     description="Roblox Presence Monitor — phone alerts and a private 14-day graph",
                                     epilog="Use COMMAND --help for its options. Dashboard example: robox graph (no sudo). robox and roblox are equivalent.")
    default_config = "/etc/roblox-presence/config.json" if Path(__file__).resolve().is_relative_to(Path("/opt/roblox-presence")) else ".local/config.json"
    parser.add_argument("--config", default=None, help="Private monitor configuration; default: " + default_config)
    parser.add_argument("--client", help="Private dashboard client file; default: ~/.config/roblox-presence/dashboard.json")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True, title="Commands")
    descriptions = {"help": "Show this command list", "validate": "Check configuration without connecting to Roblox",
                    "check": "Check Roblox once and verify the observing account", "status": "Show the running monitor's health",
                    "run": "Run continuously in this terminal (usually handled by the service)",
                    "subscription": "Show your private ntfy subscription address; keep it secret",
                    "test-push": "Send a test notification to your phone", "graph": "Generate a 14-day graph and print its browser link (dashboard: no sudo)",
                    "dashboard": "Show your bookmarked private graph page (no sudo)"}
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description, description=description)
        if name == "graph":
            command.add_argument("--output", help="HTML file (default: roblox-presence.html in your home folder)")
            command.add_argument("--file-only", action="store_true", help="Save and link the HTML file without starting a viewer")
            command.add_argument("--listen", help="This server's private LAN IP for phone/computer viewing; default: config or loopback")
            command.add_argument("--port", type=int, default=0, help="Viewer port; default: choose a free port")
            command.add_argument("--minutes", type=int, default=10, help="Link lifetime, 1–60 minutes (default: 10); keep the terminal open")
    resolve = commands.add_parser("resolve", help="Resolve a Roblox username using the public API")
    resolve.add_argument("username")
    init = commands.add_parser("init", help="Create local configuration and a random ntfy topic")
    init.add_argument("--directory", default=".local")
    init.add_argument("--observer-id", required=True, type=int)
    init.add_argument("--target-id", required=True, type=int)
    init.add_argument("--without-cookie", action="store_true", help="Prepare files without asking for a session yet")
    init.add_argument("--graph-listen", default="127.0.0.1", help="Optional private server IP for clickable graph links on your home network")
    credential = commands.add_parser("set-cookie", help="Enter your own Roblox session value without echo")
    # Both --config FILE graph and graph --config FILE are accepted.
    for command in commands.choices.values():
        command.add_argument("--config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        command.add_argument("--client", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "help":
            parser.print_help()
            return 0
        if args.command in ("graph", "status", "dashboard"):
            from .dashboard_client import client_path, command, load_client
            if args.client or (args.config is None and client_path().exists()) or args.command == "dashboard":
                return command(args, load_client(args.client))
        args.config = args.config or default_config
        if args.command == "resolve":
            print(json.dumps({"user_id": resolve_username(Http(), args.username)}))
            return 0
        if args.command == "init":
            if args.observer_id <= 0 or args.target_id <= 0 or args.observer_id == args.target_id:
                raise ConfigError("Provide distinct, positive Roblox account IDs")
            graph_address = listen_address(args.graph_listen)
            directory = Path(args.directory).resolve()
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            config_path = directory / "config.json"
            if config_path.exists() or (directory / "ntfy_topic").exists():
                raise ConfigError("Local setup already exists; existing secrets were preserved")
            obj = {"observer_user_id": args.observer_id, "target_user_id": args.target_id,
                   "cookie_file": str(directory / "roblox_cookie"), "state_dir": str(directory / "state"),
                   "push": {"provider": "ntfy", "base_url": "https://ntfy.sh",
                            "topic_file": str(directory / "ntfy_topic")},
                   "poll_seconds": 15, "offline_confirmations": 2, "notify_on_startup": True,
                   "graph_listen_address": graph_address}
            write_secret(directory / "ntfy_topic", "rp-" + secrets.token_hex(24))
            config_path.write_text(json.dumps(obj, indent=2) + "\n")
            if not args.without_cookie:
                value = getpass.getpass("Your own Roblox .ROBLOSECURITY cookie value (hidden): ").strip()
                if not value:
                    raise ConfigError("Cookie was not provided; local setup files were retained")
                write_secret(directory / "roblox_cookie", value)
            print("Created protected local setup. Use --config .local/config.json subscription to view the phone topic.")
            return 0
        config = load(args.config)
        if args.command == "validate":
            print("Configuration is structurally valid. Credentials and network access are not tested.")
        elif args.command == "set-cookie":
            if config.cookie_file.startswith("credential:"):
                raise ConfigError("Update the source credential file on the server, then restart only roblox-presence")
            path = Path(config.cookie_file)
            value = getpass.getpass("Your own Roblox .ROBLOSECURITY cookie value (hidden): ").strip()
            if not value or any(ord(c) < 32 or ord(c) > 126 for c in value) or any(c in value for c in ";,\" "):
                raise ConfigError("Provide only a valid single-line cookie value")
            temp = path.with_name(path.name + ".new")
            write_secret(temp, value)
            temp.replace(path)
            print("Cookie saved without displaying it.")
        elif args.command == "subscription":
            if config.push_provider != "ntfy":
                raise ConfigError("subscription is for ntfy only")
            # This command deliberately displays the bearer topic to its operator.
            print(config.push_base_url + "/" + secret(config.push_topic_file))
        elif args.command == "check":
            config.credentials()
            source = Roblox(config, Http(config.timeout_seconds))
            source.validate_target()
            online = source.poll()
            print(json.dumps({"observer_verified": True, "target_verified": True,
                              "visible_status": "online" if online else "offline",
                              "note": "An offline result cannot prove presence visibility; compare during a known online session."}))
        elif args.command == "test-push":
            Push(config, Http(config.timeout_seconds)).send({"kind": "test", "created_at": time.time()})
            print("Provider accepted the test. Confirm receipt on the phone, including with its screen off.")
        elif args.command == "status":
            data = read_health(config, time.time())
            print(json.dumps(data, indent=2))
            return 0 if data["healthy"] else 1
        elif args.command == "graph":
            from .report import export_report, render, server_zone, snapshot
            from .viewer import print_file_link, serve, validate_options
            address = listen_address(args.listen or config.graph_listen_address)
            validate_options(args.port, args.minutes * 60)
            now = time.time()
            zone, label = server_zone()
            data = snapshot(config, now, zone)
            content = render(data, now, zone, label, config.poll_seconds)
            output = export_report(content, args.output)
            print(f"Graph saved: {output}\nTimes use {label} on the server. This is a private snapshot; run graph again to refresh it.")
            if args.file_only:
                print_file_link(output)
            else:
                serve(content, address, args.port, args.minutes)
        elif args.command == "run":
            run(config)
        return 0
    except (ConfigError, ServiceError) as exc:
        # These exception types contain only safe, locally constructed messages.
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("Error: local file or configuration operation failed", file=sys.stderr)
        return 2
    except Exception:
        print("Error: unexpected monitor failure; no credentials were logged", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
