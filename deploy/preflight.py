#!/usr/bin/env python3
"""Read-only server compatibility and collision check. Safe to run unprivileged."""

import json
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def inspect():
    version, services, service_state = None, [], {}
    systemd_running = Path("/run/systemd/system").is_dir() and shutil.which("systemctl") is not None
    if shutil.which("systemctl"):
        result = subprocess.run(["systemctl", "--version"], capture_output=True, text=True)
        try:
            version = int(result.stdout.splitlines()[0].split()[1]) if result.returncode == 0 else None
        except (ValueError, IndexError):
            pass
    if systemd_running:
        active = subprocess.run(["systemctl", "list-units", "--type=service", "--state=running",
                                 "--no-legend", "--plain", "--no-pager"], capture_output=True, text=True,
                                check=True).stdout
        services = sorted(line.split()[0] for line in active.splitlines() if line.strip())
        if services:
            details = subprocess.run(["systemctl", "show", *services, "--property=Id,MainPID,ActiveState,"
                                      "SubState,ExecMainStartTimestampMonotonic"], capture_output=True,
                                      text=True, check=True).stdout
            for block in details.strip().split("\n\n"):
                fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
                if fields.get("Id"):
                    service_state[fields["Id"]] = fields
    paths = ["/opt/roblox-presence", "/etc/roblox-presence",
             "/etc/systemd/system/roblox-presence.service", "/etc/init.d/roblox-presence"]
    collisions = [p for p in paths if Path(p).exists()]
    runtime_supported = platform.system() == "Linux" and sys.version_info >= (3, 11)
    init_system = "systemd" if systemd_running else "openrc" if shutil.which("rc-service") else "other"
    return {"hostname": platform.node(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "systemd": version,
            "supported": runtime_supported, "init_system": init_system,
            "systemd_install_supported": runtime_supported and systemd_running and version is not None and version >= 250,
            "disk_free_bytes": shutil.disk_usage("/").free,
            "paths_already_present": collisions,
            "running_services": services, "service_state": service_state}


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2))
