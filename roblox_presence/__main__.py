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

from .config import ConfigError, load, secret
from .http import Http, ServiceError
from .monitor import run
from .push import Push
from .roblox import Roblox, resolve_username
from .state import read_health


def write_secret(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value + "\n")


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Roblox Presence Monitor")
    parser.add_argument("--config", default="config.local.json")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "check", "status", "run", "subscription", "test-push"):
        commands.add_parser(name)
    resolve = commands.add_parser("resolve", help="Resolve a Roblox username using the public API")
    resolve.add_argument("username")
    init = commands.add_parser("init", help="Create local configuration and a random ntfy topic")
    init.add_argument("--directory", default=".local")
    init.add_argument("--observer-id", required=True, type=int)
    init.add_argument("--target-id", required=True, type=int)
    init.add_argument("--without-cookie", action="store_true", help="Prepare files without asking for a session yet")
    credential = commands.add_parser("set-cookie", help="Enter your own Roblox session value without echo")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "resolve":
            print(json.dumps({"user_id": resolve_username(Http(), args.username)}))
            return 0
        if args.command == "init":
            if args.observer_id <= 0 or args.target_id <= 0 or args.observer_id == args.target_id:
                raise ConfigError("Provide distinct, positive Roblox account IDs")
            directory = Path(args.directory).resolve()
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            config_path = directory / "config.json"
            if config_path.exists() or (directory / "ntfy_topic").exists():
                raise ConfigError("Local setup already exists; existing secrets were preserved")
            obj = {"observer_user_id": args.observer_id, "target_user_id": args.target_id,
                   "cookie_file": str(directory / "roblox_cookie"), "state_dir": str(directory / "state"),
                   "push": {"provider": "ntfy", "base_url": "https://ntfy.sh",
                            "topic_file": str(directory / "ntfy_topic")},
                   "poll_seconds": 15, "offline_confirmations": 2, "notify_on_startup": True}
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
