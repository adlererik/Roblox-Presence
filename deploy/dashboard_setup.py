#!/usr/bin/env python3
"""Enable this monitor's private dashboard. Dry run unless --apply is supplied.

One administrator setup grants an operator a private dashboard client file;
everyday graph/status commands need neither sudo nor access to Roblox credentials.
"""

import argparse
import json
import os
import pwd
import secrets
import socket
import sys
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from roblox_presence.config import ConfigError, integer, listen_address, load, secret
from roblox_presence.dashboard import save_report
from roblox_presence.dashboard_client import load_client, validate_url

MARKER = "# Managed by Roblox Presence Monitor: private dashboard\n"


def dropin(port, address):
    family = "ipv6" if ":" in address else "ipv4"
    return (MARKER + "[Service]\n"
            "LoadCredential=dashboard_key:/etc/roblox-presence/dashboard_key\n"
            f"SocketBindAllow={family}:tcp:{port}\nMemoryMax=256M\n")


def plan(config, *, user=None, address=None, port=8765, root=Path('/'), identity=None, check_port=True):
    address = listen_address(address or config.graph_listen_address)
    integer(port, 'dashboard port', 1024, 65535)
    if identity is None:
        try:
            identity = pwd.getpwnam(user) if user else pwd.getpwuid(int(os.environ.get('SUDO_UID', '0')))
        except (KeyError, ValueError):
            raise ConfigError("Select an existing non-root operator with --user") from None
    if identity.pw_uid == 0:
        raise ConfigError("Select a non-root operator with --user or run through that user's sudo terminal")
    home = Path(identity.pw_dir)
    if not home.is_dir() or home.is_symlink() or home.stat().st_uid != identity.pw_uid:
        raise ConfigError("Operator home must be a real directory owned by that operator")
    etc = root / 'etc/roblox-presence'
    if not etc.is_dir() or etc.is_symlink():
        raise ConfigError("Install this monitor first; dashboard setup does not create another monitor")
    key_path = etc / 'dashboard_key'
    key = secret(str(key_path)) if key_path.exists() or key_path.is_symlink() else secrets.token_hex(32)
    host = '[' + address + ']' if ':' in address else address
    url = f'http://{host}:{port}/{key}/'
    validate_url(url)
    directory = root / 'etc/systemd/system/roblox-presence.service.d'
    target = directory / 'dashboard.conf'
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()) or target.is_symlink():
        raise ConfigError("Dashboard unit path is unsafe; existing paths were preserved")
    if target.exists() and (not target.is_file() or target.read_text() != dropin(config.dashboard_port, config.graph_listen_address)):
        raise ConfigError("An existing dashboard drop-in needs inspection; it was preserved")
    if check_port and not (config.dashboard_port == port and config.graph_listen_address == address):
        family = socket.AF_INET6 if ':' in address else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((address, port))
        except OSError:
            raise ConfigError("Dashboard address/port is unavailable. Choose a free port; no existing listener was changed") from None
    return {'identity': identity, 'home': home, 'address': address, 'port': port,
            'key_path': key_path, 'key': key, 'dropin': target, 'url': url}


def write_client(home, url):
    """Called only after dropping to the operator, so home-path races grant no root access."""
    os.umask(0o077)
    for directory in (home / '.config', home / '.config/roblox-presence'):
        if directory.is_symlink():
            raise ConfigError("Operator client directory must not be a symlink")
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.stat()
        if not directory.is_dir() or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ConfigError("Operator client directory is not privately owned")
    path = home / '.config/roblox-presence/dashboard.json'
    if path.exists() or path.is_symlink():
        previous = load_client(path)
        if previous == url:
            return
        save_report(path.with_name('dashboard-before-' + str(time.time_ns()) + '.json'), path.read_text())
    save_report(path, json.dumps({'url': url}, indent=2) + '\n')


def apply_files(prepared):
    path = prepared['key_path']
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(prepared['key'] + '\n')
    target = prepared['dropin']
    target.parent.mkdir(mode=0o755, exist_ok=True)
    target.parent.chmod(0o755)
    save_report(target, dropin(prepared['port'], prepared['address']))
    target.chmod(0o644)
    identity = prepared['identity']
    if os.geteuid() == identity.pw_uid:
        write_client(prepared['home'], prepared['url'])
    elif os.geteuid() == 0:
        child = os.fork()
        if child == 0:
            try:
                os.setgroups([])
                os.setgid(identity.pw_gid)
                os.setuid(identity.pw_uid)
                write_client(prepared['home'], prepared['url'])
            except Exception:
                os._exit(1)
            os._exit(0)
        _, status = os.waitpid(child, 0)
        if status:
            raise ConfigError("Could not save operator client settings. Existing monitor files were preserved for inspection")
    else:
        raise ConfigError("Only the operator or administrator can write this client setup")


def updated_config(obj, prepared):
    obj = dict(obj)
    obj['graph_listen_address'] = prepared['address']
    obj['dashboard'] = {'port': prepared['port'], 'key_file': 'credential:dashboard_key'}
    return obj


def verify(url, timeout=45):
    from roblox_presence.dashboard_client import state
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if state(url)['monitor'].get('healthy'):
                return
        except ConfigError:
            pass
        time.sleep(1)
    raise ConfigError("Dashboard has not passed its private-network/health check. Preserve files and ask for inspection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--listen', help="This server's specific private IP (default: saved graph address)")
    parser.add_argument('--port', type=int, default=8765, help='A free fixed unprivileged port (default: 8765)')
    parser.add_argument('--user', help='Non-root operator (default: the sudo caller)')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ConfigError("One-time dashboard installation needs an administrator; daily commands will not")
        config_path = Path('/etc/roblox-presence/config.json')
        config = load(config_path)
        if not Path('/opt/roblox-presence/current/roblox_presence/dashboard.py').is_file():
            raise ConfigError("Upgrade the monitor code to 0.3.0 or later first")
        prepared = plan(config, user=args.user, address=args.listen, port=args.port)
        if not args.apply:
            print('Dashboard setup can be prepared. Dry run: no files or services changed.')
            return 0
        # Import here to share monitor-only service selection and comparison.
        from upgrade import production_snapshot, systemctl
        before = production_snapshot()
        backup = Path('/opt/roblox-presence/backups') / ('dashboard-' + str(time.time_ns()))
        backup.mkdir(mode=0o700, parents=True)
        save_report(backup / 'config.json', config_path.read_text())
        if prepared['dropin'].exists():
            save_report(backup / 'dashboard.conf', prepared['dropin'].read_text())
        obj = updated_config(json.loads(config_path.read_text()), prepared)
        apply_files(prepared)
        save_report(config_path, json.dumps(obj, indent=2) + '\n')
        systemctl('daemon-reload')
        systemctl('restart', 'roblox-presence.service')
        verify(prepared['url'])
        after = production_snapshot()
        if any(after.get(name) != value for name, value in before.items()):
            raise ConfigError("Another service changed during setup; inspect its status")
        print('Dashboard enabled. Daily commands: robox graph | robox dashboard | robox status')
        print('Bookmark this private URL:')
        print(prepared['url'])
        return 0
    except Exception as exc:
        print(str(exc) if isinstance(exc, ConfigError) else
              'Dashboard setup did not complete. Preserve files for inspection; no unrelated service was selected.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
