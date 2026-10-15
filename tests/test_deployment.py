import importlib.util
import contextlib
import io
import dataclasses
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from roblox_presence.config import ConfigError, load
from roblox_presence import __version__

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("presence_installer", ROOT / "deploy/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
preflight_spec = importlib.util.spec_from_file_location("presence_preflight", ROOT / "deploy/preflight.py")
preflight = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(preflight)
package_spec = importlib.util.spec_from_file_location("presence_package", ROOT / "tools/package.py")
packager = importlib.util.module_from_spec(package_spec)
package_spec.loader.exec_module(packager)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "system"
        (self.root / "opt").mkdir(parents=True)
        (self.root / "etc/systemd/system").mkdir(parents=True)
        self.cookie = self.base / "cookie"
        self.topic = self.base / "topic"
        self.cookie.write_text("TEST_OBSERVER_COOKIE")
        self.topic.write_text("rp-" + "f" * 48)
        self.cookie.chmod(0o600)
        self.topic.chmod(0o600)
        obj = json.loads((ROOT / "config.example.json").read_text())
        obj["cookie_file"] = str(self.cookie)
        obj["push"]["topic_file"] = str(self.topic)
        obj["state_dir"] = str(self.base / "source-state")
        self.config_file = self.base / "config.json"
        self.config_file.write_text(json.dumps(obj))
        self.config = load(self.config_file)

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_creates_nothing_and_does_not_need_cookie(self):
        self.cookie.unlink()
        result = installer.install(ROOT, self.config, self.root)
        self.assertFalse(result["service_started"])
        self.assertFalse((self.root / "opt/roblox-presence").exists())
        self.assertFalse((self.root / "etc/roblox-presence").exists())

    def test_apply_install_is_isolated_and_disabled_with_no_systemctl(self):
        sentinel = self.root / "etc/systemd/system/production.service"
        sentinel.write_text("production-is-untouched")
        before = sentinel.read_bytes()
        result = installer.install(ROOT, self.config, self.root, apply=True)
        self.assertFalse(result["service_started"])
        self.assertEqual(sentinel.read_bytes(), before)
        current = self.root / "opt/roblox-presence/current"
        self.assertTrue((current / "roblox_presence/__main__.py").is_file())
        self.assertFalse((current / ".local").exists())
        self.assertFalse((current / ".git").exists())
        target_config = load(self.root / "etc/roblox-presence/config.json")
        self.assertEqual(target_config.cookie_file, "credential:roblox_cookie")
        self.assertEqual((self.root / "etc/roblox-presence/roblox_cookie").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "etc/roblox-presence").stat().st_mode & 0o777, 0o700)
        self.assertEqual(current.parent.stat().st_mode & 0o777, 0o755)
        self.assertFalse((self.root / "etc/systemd/system/multi-user.target.wants").exists())

    def test_existing_monitor_paths_refused_without_overwrite(self):
        path = self.root / "etc/systemd/system/roblox-presence.service"
        path.write_text("keep-existing-unit")
        with self.assertRaises(ConfigError):
            installer.install(ROOT, self.config, self.root, apply=True)
        self.assertEqual(path.read_text(), "keep-existing-unit")
        self.assertFalse((self.root / "opt/roblox-presence").exists())

    def test_service_reads_private_config_through_its_credential_directory(self):
        installer.install(ROOT, self.config, self.root, apply=True)
        unit = (self.root / "etc/systemd/system/roblox-presence.service").read_text()
        credentials = self.base / "service-credentials"
        credentials.mkdir(mode=0o700)
        for line in unit.splitlines():
            if line.startswith("LoadCredential="):
                name, source = line.removeprefix("LoadCredential=").split(":", 1)
                destination = credentials / name
                shutil.copyfile(self.root / source.lstrip("/"), destination)
                destination.chmod(0o400)
        command = shlex.split(next(line.removeprefix("ExecStart=")
                                 for line in unit.splitlines() if line.startswith("ExecStart=")))
        config_argument = command[command.index("--config") + 1]
        # Reading /etc directly would fail for DynamicUser inside the root-only directory.
        self.assertTrue(config_argument.startswith("%d/"))
        config_path = Path(config_argument.replace("%d", str(credentials)))
        self.assertTrue(config_path.is_file())
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(credentials)}):
            config = dataclasses.replace(load(config_path), state_dir=self.root / "var/lib/roblox-presence")
            self.assertEqual(config.credentials()["roblox_cookie"], "TEST_OBSERVER_COOKIE")
            self.assertEqual(config.credentials()["topic"], "rp-" + "f" * 48)
        command[0] = sys.executable
        command[command.index("--config") + 1] = str(config_path)
        command[-1] = "validate"
        result = subprocess.run(command, cwd=self.root / "opt/roblox-presence/current",
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_credential_refused_before_files_are_written(self):
        self.cookie.unlink()
        with self.assertRaises(ConfigError):
            installer.install(ROOT, self.config, self.root, apply=True)
        self.assertFalse((self.root / "opt/roblox-presence").exists())

    def test_unit_has_no_other_application_commands(self):
        unit = (ROOT / "deploy/roblox-presence.service").read_text()
        for expected in ("DynamicUser=yes", "ProtectSystem=strict", "WatchdogSec=90s", "CPUQuota=5%",
                         "MemoryMax=128M", "SocketBindDeny=any", "LoadCredential=roblox_cookie:"):
            self.assertIn(expected, unit)
        commands = [line for line in unit.splitlines() if line.startswith("Exec")]
        self.assertEqual(len(commands), 1)
        self.assertIn("-m roblox_presence", commands[0])

    def test_preflight_without_systemd_reports_runtime_support(self):
        with patch.object(preflight.shutil, "which", return_value=None), \
                patch.object(preflight.platform, "system", return_value="Linux"), \
                patch.object(preflight.subprocess, "run") as run_command:
            result = preflight.inspect()
        self.assertTrue(result["supported"])
        self.assertFalse(result["systemd_install_supported"])
        self.assertEqual(result["init_system"], "other")
        self.assertEqual(result["running_services"], [])
        run_command.assert_not_called()

    def test_preflight_detects_openrc_without_using_systemctl(self):
        with patch.object(preflight.shutil, "which", side_effect=lambda name: "/sbin/rc-service" if name == "rc-service" else None), \
                patch.object(preflight.platform, "system", return_value="Linux"), \
                patch.object(preflight.subprocess, "run") as run_command:
            result = preflight.inspect()
        self.assertTrue(result["supported"])
        self.assertEqual(result["init_system"], "openrc")
        run_command.assert_not_called()

    def test_direct_configuration_uses_file_credentials_without_systemd(self):
        direct = load(ROOT / "config.direct.example.json")
        self.assertFalse(direct.cookie_file.startswith("credential:"))
        self.assertFalse(direct.push_topic_file.startswith("credential:"))

    def test_openrc_example_shell_syntax_and_dedicated_paths(self):
        script = ROOT / "deploy/roblox-presence.openrc"
        subprocess.run(["sh", "-n", str(script)], check=True, capture_output=True)
        content = script.read_text()
        self.assertIn('supervisor="supervise-daemon"', content)
        self.assertIn('command_user="roblox-presence:roblox-presence"', content)
        self.assertIn('pidfile="/run/roblox-presence.pid"', content)
        self.assertIn("TERM/45", content)

    def test_cli_prepare_validate_and_cookie_fail_without_secret_logging(self):
        setup = self.base / "setup"
        subprocess.run([sys.executable, "-m", "roblox_presence", "init", "--directory", str(setup),
                        "--observer-id", "11", "--target-id", "22", "--without-cookie"],
                       cwd=ROOT, capture_output=True, check=True)
        validation = subprocess.run([sys.executable, "-m", "roblox_presence", "--config",
                                     str(setup / "config.json"), "validate"], cwd=ROOT, capture_output=True)
        self.assertEqual(validation.returncode, 0)
        check = subprocess.run([sys.executable, "-m", "roblox_presence", "--config",
                                str(setup / "config.json"), "check"], cwd=ROOT, capture_output=True)
        self.assertEqual(check.returncode, 2)
        self.assertIn(b"Cannot read a credential file", check.stderr)
        repeated = subprocess.run([sys.executable, "-m", "roblox_presence", "init", "--directory", str(setup),
                                   "--observer-id", "11", "--target-id", "22", "--without-cookie"],
                                  cwd=ROOT, capture_output=True)
        self.assertEqual(repeated.returncode, 2)

    def test_packaging_excludes_private_runtime_files(self):
        # Test the actual produced source archive rather than just its filter code.
        subprocess.run([sys.executable, "tools/package.py"], cwd=ROOT, capture_output=True, check=True)
        archive = ROOT / f"dist/roblox-presence-{__version__}.tar.gz"
        first = hashlib.sha256(archive.read_bytes()).hexdigest()
        subprocess.run([sys.executable, "tools/package.py"], cwd=ROOT, capture_output=True, check=True)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), first)
        with tarfile.open(archive) as tar:
            names = tar.getnames()
            self.assertIn("roblox-presence/roblox_presence/monitor.py", names)
            self.assertIn("roblox-presence/deploy/install.py", names)
            self.assertIn("roblox-presence/deploy/roblox-presence.openrc", names)
            self.assertIn("roblox-presence/config.direct.example.json", names)
            self.assertIn("roblox-presence/.gitignore", names)
            self.assertIn("roblox-presence/docs/GETTING_STARTED.md", names)
            for name in names:
                self.assertFalse(any(part in name.split("/") for part in (".local", ".git", "__pycache__", "credentials")))
                self.assertFalse(name.endswith("sqlite3"))
                self.assertFalse(tar.getmember(name).issym())
            cookie = ROOT / ".local/roblox_cookie"
            if cookie.exists():
                value = cookie.read_bytes().strip()
                for item in tar.getmembers():
                    self.assertFalse(value in tar.extractfile(item).read(),
                                     "A protected credential was included in the release")

    def test_untracked_private_canary_does_not_enter_release(self):
        private = ROOT / ".local"
        existed = private.exists()
        private.mkdir(mode=0o700, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=private, prefix="package-private-") as folder:
                canary = b"PACKAGE_PRIVATE_CANARY_NOT_A_REAL_CREDENTIAL_" + Path(folder).name.encode()
                (Path(folder) / "private-session").write_bytes(canary)
                subprocess.run([sys.executable, "tools/package.py"], cwd=ROOT, capture_output=True, check=True)
                with tarfile.open(ROOT / f"dist/roblox-presence-{__version__}.tar.gz") as archive:
                    for member in archive:
                        self.assertNotIn(".local", Path(member.name).parts)
                        self.assertFalse(canary in archive.extractfile(member).read(),
                                         "An ignored private canary entered the release")
        finally:
            if not existed:
                private.rmdir()

    def test_packaging_refuses_source_symlinks_to_private_files(self):
        for name in ("README.md", ".gitignore", "config.example.json", "config.direct.example.json", "roblox", "robox"):
            (self.base / name).write_text("generic source fixture")
        (self.base / "docs").mkdir()
        (self.base / "docs/linked.md").symlink_to(self.cookie)
        with patch.object(packager, "ROOT", self.base), self.assertRaisesRegex(ValueError, "symlinks"):
            packager.package()



upgrade_spec = importlib.util.spec_from_file_location("presence_upgrader", ROOT / "deploy/upgrade.py")
upgrader = importlib.util.module_from_spec(upgrade_spec)
upgrade_spec.loader.exec_module(upgrader)


class UpgradeTests(unittest.TestCase):
    setUp = DeploymentTests.setUp
    tearDown = DeploymentTests.tearDown
    # Reuse installation fixtures; the extra assertions exercise a real SQLite backup
    # and release switch with only service-control operations mocked.
    def old_install(self):
        installer.install(ROOT, self.config, self.root, apply=True)
        app = self.root / "opt/roblox-presence"
        (app / ("releases/" + __version__)).rename(app / "releases/0.1.0")
        (app / "current").unlink()
        (app / "current").symlink_to("releases/0.1.0")
        path = self.root / "etc/roblox-presence/config.json"
        obj = json.loads(path.read_text())
        obj["state_dir"] = str(self.root / "var/lib/roblox-presence")
        path.write_text(json.dumps(obj))
        from roblox_presence.state import State
        state = State(load(path), 1000)
        state.observe(True, 1000)
        state.close()
        return app

    def test_upgrade_dry_run_collision_and_private_copy(self):
        app = self.old_install()
        unit = (self.root / "etc/systemd/system/roblox-presence.service").read_bytes()
        path = self.root / "usr/local/bin/robox"
        path.unlink()
        path.write_text("unrelated-command")
        with self.assertRaises(ConfigError):
            upgrader.prepare(root=self.root)
        self.assertEqual(path.read_text(), "unrelated-command")
        path.unlink()
        with patch.object(upgrader, "systemctl") as ctl:
            upgrader.prepare(root=self.root)
            self.assertFalse((app / ("releases/" + __version__)).exists())
            target = upgrader.prepare(root=self.root, apply=True)
            self.assertFalse((target / ".local").exists())
            self.assertTrue((target / "robox").stat().st_mode & 0o100)
            ctl.assert_not_called()
        self.assertEqual((self.root / "etc/systemd/system/roblox-presence.service").read_bytes(), unit)
        self.assertEqual(os.readlink(app / "current"), "releases/0.1.0")

    def test_upgrade_backups_state_preserves_credentials_and_selects_only_monitor(self):
        app = self.old_install()
        cookie = (self.root / "etc/roblox-presence/roblox_cookie").read_bytes()
        production = {"unrelated.service": {"MainPID": "123", "ExecMainStartTimestampMonotonic": "456"}}
        calls = []
        def control(*args):
            calls.append(args)
            return "active\n" if args[0] == "is-active" else ""
        with patch.object(upgrader, "production_snapshot", return_value=production), \
             patch.object(upgrader, "systemctl", side_effect=control), \
             patch.object(upgrader, "read_health", return_value={"healthy": True, "last_success": 9999999999, "updated_at": 9999999999}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(upgrader.apply_upgrade(root=self.root), 0)
        self.assertEqual(calls, [("is-active", "roblox-presence.service"), ("stop", "roblox-presence.service"), ("start", "roblox-presence.service")])
        self.assertEqual(os.readlink(app / "current"), "releases/" + __version__)
        self.assertEqual((self.root / "etc/roblox-presence/roblox_cookie").read_bytes(), cookie)
        backups = list((app / "backups").glob("*/state.sqlite3"))
        self.assertEqual(len(backups), 1)
        import sqlite3
        with contextlib.closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute("SELECT stable_online FROM monitor").fetchone()[0], 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        state_dir = self.root / "var/lib/roblox-presence"
        self.assertFalse((state_dir / "state.sqlite3-shm").exists())
        self.assertFalse((state_dir / "state.sqlite3-wal").exists())

if __name__ == "__main__":
    unittest.main()
