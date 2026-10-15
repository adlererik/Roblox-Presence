"""Persist Roblox's session rotation in protected state, without logging secrets."""

import hashlib
import json
import os
import re
import secrets
import stat
from http.cookies import CookieError, SimpleCookie

from .config import ConfigError, cookie
from .http import ServiceError


def valid_value(value):
    return (isinstance(value, str) and 0 < len(value) <= 16384
            and all(32 <= ord(c) <= 126 for c in value)
            and not any(c in value for c in ";,\" "))


class Session:
    def __init__(self, config):
        self.config = config
        self.path = config.state_dir / f"session-{config.observer_user_id}.json"
        self.source_digest = None

    def value(self):
        original = cookie(self.config.cookie_file)
        self.source_digest = hashlib.sha256(original.encode()).hexdigest()
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return original
        except OSError:
            raise ConfigError("Cannot read protected session state") from None
        try:
            with os.fdopen(fd, "r") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 20480:
                    raise ConfigError("Session state must be a protected regular file")
                data = json.loads(stream.read(20481))
            if (not isinstance(data, dict) or set(data) != {"source_digest", "value"}
                    or not valid_value(data.get("value"))
                    or not isinstance(data.get("source_digest"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", data["source_digest"])):
                raise ConfigError("Invalid protected session state")
        except (OSError, ValueError, UnicodeError):
            raise ConfigError("Cannot read protected session state") from None
        # A newly supplied source credential takes precedence over an old cache.
        return data["value"] if data["source_digest"] == self.source_digest else original

    def update(self, response):
        headers = response.set_cookies or ((response.headers["set-cookie"],)
                                          if response.headers.get("set-cookie") else ())
        rotated = None
        for header in headers:
            # Ignore other cookies rather than retaining browser/session metadata.
            if not header.lstrip().startswith(".ROBLOSECURITY="):
                continue
            try:
                jar = SimpleCookie()
                jar.load(header)
                item = jar.get(".ROBLOSECURITY")
                if item is None or not valid_value(item.value):
                    raise ValueError()
                if item["domain"] and item["domain"].lstrip(".").lower() != "roblox.com":
                    raise ValueError()
                if item["max-age"] and int(item["max-age"]) <= 0:
                    raise ValueError()
            except (CookieError, ValueError):
                raise ServiceError("roblox_invalid_session_rotation") from None
            rotated = item.value
        if rotated is not None:
            self._save(rotated)
        return rotated

    def _save(self, value):
        if self.source_digest is None:
            raise ConfigError("Session source has not been checked")
        self.config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = self.path.with_name("." + self.path.name + "." + secrets.token_hex(8))
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump({"source_digest": self.source_digest, "value": value}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(self.path)
            directory_fd = os.open(self.config.state_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            raise ConfigError("Cannot preserve rotated session credential") from None
        finally:
            temp.unlink(missing_ok=True)
