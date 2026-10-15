#!/usr/bin/env python3
"""Refresh only the installed credential source; leave service and state alone."""

import argparse
import os
import secrets
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roblox_presence.config import ConfigError, load
from roblox_presence.session import Session


def refresh(source, root=Path('/'), apply=False):
    directory = root / 'etc/roblox-presence'
    if directory.is_symlink():
        raise ConfigError('Installed credential directory must not be a symlink')
    installed = load(directory / 'config.json')
    if installed.scope != source.scope:
        raise ConfigError('Source setup does not match the installed observer and connection')
    destination = directory / 'roblox_cookie'
    info = destination.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ConfigError('Installed credential source must be a protected regular file')
    if root == Path('/') and (info.st_uid != 0 or os.geteuid() != 0):
        raise ConfigError('Refreshing the installed credential source requires root')
    if not apply:
        return
    # A successful check may already have replaced the originally entered value.
    value = Session(source).value()
    temporary = directory / ('.roblox-cookie-' + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(value + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        refresh(load(args.config), apply=args.apply)
        print('Credential source refreshed. Restart only roblox-presence.service.' if args.apply
              else 'Preview passed; no credential or service was changed.')
        return 0
    except (ConfigError, OSError):
        print('Credential refresh refused or incomplete; check matching setup and protected paths. No credential was displayed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
