#!/usr/bin/env python3
"""Prepare an isolated first systemd installation. Default is a no-write dry run.

Applying never installs packages, reloads systemd, enables a unit, or starts services.
Existing monitor paths are refused rather than overwritten.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from roblox_presence.config import ConfigError, load
from roblox_presence import __version__


def source_files(source):
    files = [source / "README.md", source / "config.example.json", source / "config.direct.example.json",
             source / "roblox", source / "robox"]
    for folder, suffix in (("roblox_presence", "*.py"), ("docs", "*.md")):
        files.extend((source / folder).glob(suffix))
    return files


def command_links(root, apply=False):
    """Reserve only our two explicitly requested CLI names; refuse collisions."""
    for name in ("roblox", "robox"):
        path = root / "usr/local/bin" / name
        target = "/opt/roblox-presence/current/" + name
        if path.exists() or path.is_symlink():
            if not path.is_symlink() or os.readlink(path) != target:
                raise ConfigError("An unrelated command already uses roblox or robox; it was preserved")
        elif apply:
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            for parent in missing:
                parent.chmod(0o755)
            path.symlink_to(target)


def plan(source, config, root=Path("/")):
    if config.push_provider != "ntfy":
        raise ConfigError("This deployment installer is configured for the selected free ntfy provider")
    destinations = {"app": root / "opt/roblox-presence", "config": root / "etc/roblox-presence",
                    "unit": root / "etc/systemd/system/roblox-presence.service"}
    if any(p.exists() or p.is_symlink() for p in destinations.values()):
        raise ConfigError("Reserved monitor paths already exist; first-install script will not overwrite them")
    command_links(root)
    required = [source / "roblox_presence/__main__.py", source / "deploy/roblox-presence.service"]
    if any(not p.is_file() or p.is_symlink() for p in source_files(source) + required):
        raise ConfigError("Source release is incomplete")
    return destinations


def install(source, config, root=Path("/"), apply=False):
    destinations = plan(source, config, root)
    result = {"apply": apply, "paths": {key: str(path) for key, path in destinations.items()},
              "service_started": False, "packages_installed": False}
    if not apply:
        return result
    if root == Path("/") and os.geteuid() != 0:
        raise ConfigError("Applying a system installation requires root")
    if root == Path("/") and not Path("/run/systemd/system").is_dir():
        raise ConfigError("This installer targets systemd; use the direct configuration with another supervisor")
    values = config.credentials()  # Check all source credentials before any writes.
    if len(values["topic"]) < 32 and not config.push_token_file:
        raise ConfigError("Use a random topic of at least 32 characters, or authenticated ntfy")
    os.umask(0o077)
    app, etc, unit = destinations["app"], destinations["config"], destinations["unit"]
    app.mkdir(mode=0o755)
    etc.mkdir(mode=0o700)
    release = app / "releases" / __version__
    release.mkdir(mode=0o755, parents=True)
    # Explicit allowlist; the source tree's .local/, Git history, and caches never copy.
    for src in source_files(source):
        if src.is_symlink():
            raise ConfigError("Release source may not contain symlinks")
        dest = release / src.relative_to(source)
        dest.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        dest.chmod(0o755 if src.name in ("roblox", "robox") else 0o644)
    # chmod parents created under umask 0077, including releases/.
    for directory, _, _ in os.walk(app):
        Path(directory).chmod(0o755)
    (app / "current").symlink_to("releases/" + __version__)
    command_links(root, apply=True)
    for key in ("roblox_cookie", "topic", "token"):
        if key in values:
            name = {"topic": "ntfy_topic", "token": "ntfy_token"}.get(key, key)
            path = etc / name
            with path.open("x") as stream:
                stream.write(values[key] + "\n")
            path.chmod(0o600)
    obj = {"observer_user_id": config.observer_user_id, "target_user_id": config.target_user_id,
           "cookie_file": "credential:roblox_cookie", "state_dir": "/var/lib/roblox-presence",
           "push": {"provider": "ntfy", "base_url": config.push_base_url,
                    "topic_file": "credential:ntfy_topic"},
           "poll_seconds": config.poll_seconds, "offline_confirmations": config.offline_confirmations,
           "timeout_seconds": config.timeout_seconds, "alert_ttl_seconds": config.alert_ttl_seconds,
           "outage_alert_seconds": config.outage_alert_seconds, "notify_on_startup": config.notify_on_startup,
           "graph_listen_address": config.graph_listen_address}
    content = (source / "deploy/roblox-presence.service").read_text()
    if config.push_token_file:
        obj["push"]["token_file"] = "credential:ntfy_token"
        content = content.replace("LoadCredential=ntfy_topic:/etc/roblox-presence/ntfy_topic\n",
                                  "LoadCredential=ntfy_topic:/etc/roblox-presence/ntfy_topic\n"
                                  "LoadCredential=ntfy_token:/etc/roblox-presence/ntfy_token\n")
    (etc / "config.json").write_text(json.dumps(obj, indent=2) + "\n")
    unit.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects a concurrent administrator's unit.
    with unit.open("x") as stream:
        stream.write(content)
    unit.chmod(0o644)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Local configuration referencing protected source credential files")
    parser.add_argument("--apply", action="store_true", help="Copy this monitor's files only; leave unit disabled")
    parser.add_argument("--root", type=Path, default=Path("/"), help="Alternate filesystem root for an isolated installation test")
    args = parser.parse_args()
    try:
        print(json.dumps(install(SOURCE, load(args.config), args.root.resolve(), args.apply), indent=2))
    except (ConfigError, OSError):
        print("Installation refused or incomplete. Check dedicated paths and protected credentials; no service was started.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
