#!/usr/bin/env python3
"""Guarded update of this monitor only. Dry run unless --apply is supplied.

Preserves credentials, unit configuration and durable state. Saves a private
SQLite backup before switching releases. Never restarts unrelated services.
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import command_links, source_files
from roblox_presence import __version__
from roblox_presence.config import ConfigError, listen_address, load
from roblox_presence.state import read_health, preserve_sqlite_owner

UNIT = "roblox-presence.service"


def systemctl(*args):
    return subprocess.run(["systemctl", *args], check=True, capture_output=True,
                          text=True, timeout=30).stdout


def production_snapshot():
    units = [line.split()[0] for line in systemctl("list-units", "--type=service", "--state=running",
                                                 "--no-legend", "--plain").splitlines() if line.strip()]
    result = {}
    for unit in units:
        if unit != UNIT:
            values = systemctl("show", unit, "--property=MainPID,ExecMainStartTimestampMonotonic,ActiveState")
            result[unit] = dict(line.split("=", 1) for line in values.splitlines() if "=" in line)
    return result


def prepare(source=SOURCE, root=Path("/"), apply=False):
    app = root / "opt/roblox-presence"
    current = app / "current"
    unit = root / "etc/systemd/system" / UNIT
    config = root / "etc/roblox-presence/config.json"
    target = app / "releases" / __version__
    if (app.is_symlink() or (app / "releases").is_symlink() or config.is_symlink()
            or not current.is_symlink() or not unit.is_file() or unit.is_symlink() or not config.is_file()
            or not current.resolve().is_relative_to((app / "releases").resolve())):
        raise ConfigError("Expected isolated installation was not found; no update was applied")
    if target.exists() or target.is_symlink():
        raise ConfigError("This release already exists; preserve it and inspect the installed version")
    command_links(root)
    files = source_files(source)
    if any(not p.is_file() or p.is_symlink() for p in files):
        raise ConfigError("Source release is incomplete or contains symlinks")
    if not apply:
        return target
    try:
        target.mkdir(mode=0o755)
        for src in files:
            dest = target / src.relative_to(source)
            dest.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            dest.chmod(0o755 if src.name in ("roblox", "robox") else 0o644)
        for directory, _, _ in os.walk(target):
            Path(directory).chmod(0o755)
    except Exception:
        # No service or current symlink has changed yet; preserve partial files for inspection.
        raise ConfigError("Release copy failed before service activation; inspect the prepared release") from None
    return target


def apply_upgrade(graph=False, *, root=Path("/"), graph_listen=None, dashboard=False,
                  dashboard_user=None, dashboard_port=8765):
    if root == Path("/") and (os.geteuid() != 0 or not Path("/run/systemd/system").is_dir()):
        raise ConfigError("Apply from a root terminal on the systemd server hosting this monitor")
    os.umask(0o077)
    config = load(root / "etc/roblox-presence/config.json")
    if graph_listen is not None:
        graph_listen = listen_address(graph_listen)
    if config.state_dir != root / "var/lib/roblox-presence":
        raise ConfigError("Unexpected state path; inspect this installation before updating")
    dashboard_plan = None
    if dashboard:
        import dashboard_setup
        dashboard_plan = dashboard_setup.plan(config, user=dashboard_user, address=graph_listen,
                                              port=dashboard_port, root=root)
    prepare(root=root)  # All collision / source checks before touching the running monitor.
    before = production_snapshot()
    target = prepare(root=root, apply=True)
    app = target.parents[1]
    current = app / "current"
    previous = os.readlink(current)
    was_active = systemctl("is-active", UNIT).strip() == "active"
    if not was_active:
        raise ConfigError("Monitor must be running before this guarded update")
    # Only our service is stopped. Dashboard opt-in reloads its new unit drop-in;
    # no package operation, proxy or firewall edit is performed.
    backup_folder = app / "backups" / ("before-" + __version__ + "-" + str(time.time_ns()))
    backup_folder.mkdir(mode=0o700, parents=True)
    (app / "backups").chmod(0o700)
    config_path = root / "etc/roblox-presence/config.json"
    prepared_config = None
    if graph_listen is not None or dashboard_plan:
        original_config = config_path.read_bytes()
        updated_config = json.loads(original_config)
        if graph_listen is not None:
            updated_config["graph_listen_address"] = graph_listen
        if dashboard_plan:
            updated_config = dashboard_setup.updated_config(updated_config, dashboard_plan)
        prepared_config = config_path.with_name("config-" + __version__ + ".new")
        fd = os.open(prepared_config, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(updated_config, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        (backup_folder / "config.json").write_bytes(original_config)
        (backup_folder / "config.json").chmod(0o600)
    if dashboard_plan:
        if dashboard_plan['dropin'].exists():
            (backup_folder / 'dashboard.conf').write_bytes(dashboard_plan['dropin'].read_bytes())
        dashboard_setup.apply_files(dashboard_plan)
    systemctl("stop", UNIT)
    changed = False
    try:
        original = config.state_dir / "state.sqlite3"
        if not original.is_file() or original.is_symlink():
            raise ConfigError("Expected state database is missing or unsafe; original service was preserved")
        if original.is_file():
            owner = original.stat()
            # A read/write handle closes/checkpoints its temporary sidecars;
            # a root mode=ro handle can leave root-owned WAL/SHM behind.
            try:
                with closing(sqlite3.connect(original.resolve().as_uri() + "?mode=rw", uri=True)) as src, \
                        closing(sqlite3.connect(backup_folder / "state.sqlite3")) as dst:
                    src.backup(dst)
            finally:
                preserve_sqlite_owner(original, owner)
            (backup_folder / "state.sqlite3").chmod(0o600)
        (backup_folder / "previous-release.txt").write_text(previous + "\n")
        temporary = app / "current.new"
        if temporary.exists() or temporary.is_symlink():
            raise ConfigError("A pending release switch exists; inspect it before retrying")
        temporary.symlink_to("releases/" + __version__)
        temporary.replace(current)
        changed = True
        if prepared_config is not None:
            prepared_config.replace(config_path)
        command_links(root, apply=True)
        if dashboard_plan:
            systemctl("daemon-reload")  # Reload definitions; restart only this monitor below.
        started = time.time()
        systemctl("start", UNIT)
        deadline = time.monotonic() + 55
        health = {}
        while time.monotonic() < deadline:
            try:
                health = read_health(config, time.time())
                if health["healthy"] and health.get("last_success", 0) >= started and health.get("updated_at", 0) >= started:
                    break
            except ConfigError:
                pass
            time.sleep(1)
        else:
            raise ConfigError("Updated monitor has not passed health checks; preserve the backup and ask for inspection")
    except Exception:
        if not changed:
            if prepared_config is not None:
                prepared_config.unlink(missing_ok=True)
            systemctl("start", UNIT)  # Old code and DB untouched if switch never happened.
        # After activation, don't restore an old database automatically: that could
        # erase new observations and acknowledgements or replay accepted notifications.
        raise
    after = production_snapshot()
    unchanged = all(after.get(name) == value for name, value in before.items())
    result = {"version": __version__, "healthy": True, "production_services_unchanged": unchanged,
              "history_recording_enabled": True, "backup_saved": True}
    if dashboard_plan:
        dashboard_setup.verify(dashboard_plan['url'])
        result.update(dashboard_enabled=True, operator_client_saved=True,
                      private_dashboard_url=dashboard_plan['url'])
        if graph:
            from roblox_presence.dashboard_client import generate
            generate(dashboard_plan['url'])
    elif graph:
        from roblox_presence.report import export_report, render, server_zone, snapshot
        now = time.time()
        zone, label = server_zone()
        result["graph_file"] = str(export_report(render(snapshot(config, now, zone), now, zone, label, config.poll_seconds)))
        from roblox_presence.viewer import file_link
        result["graph_file_url"] = file_link(Path(result["graph_file"]))
        result["open_in_phone_browser"] = "Run sudo robox graph for a temporary browser link"
    print(json.dumps(result, indent=2))
    if not unchanged:
        raise ConfigError("A production service changed during the update; inspect its status before proceeding")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Back up state, switch code and restart this monitor only")
    parser.add_argument("--graph", action="store_true", help="Also save a private HTML graph in the sudo caller's home")
    parser.add_argument("--graph-listen", help="Save this specific private server IP for phone/computer graph links")
    parser.add_argument("--dashboard", action="store_true", help="Enable the persistent private page and commands without sudo")
    parser.add_argument("--dashboard-user", help="Non-root operator for the dashboard (default: sudo caller)")
    parser.add_argument("--dashboard-port", type=int, default=8765, help="Free fixed dashboard port (default: 8765)")
    args = parser.parse_args()
    try:
        if args.apply:
            return apply_upgrade(args.graph, graph_listen=args.graph_listen, dashboard=args.dashboard,
                                 dashboard_user=args.dashboard_user, dashboard_port=args.dashboard_port)
        if args.graph_listen is not None:
            listen_address(args.graph_listen)
        prepare()
        if args.dashboard:
            import dashboard_setup
            dashboard_setup.plan(load('/etc/roblox-presence/config.json'), user=args.dashboard_user,
                                 address=args.graph_listen, port=args.dashboard_port)
        print("Update can be prepared for " + __version__ + ". Dry run: no files or services changed.")
        return 0
    except (ConfigError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, ConfigError) else "Update did not complete. Preserve files and ask for inspection; no unrelated service was selected.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
