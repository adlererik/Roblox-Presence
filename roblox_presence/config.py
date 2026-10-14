"""Strict configuration and file-based credentials. No secrets in CLI arguments."""

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(Exception):
    pass


def secret(reference: str) -> str:
    if reference.startswith("credential:"):
        name = reference.split(":", 1)[1]
        directory = os.environ.get("CREDENTIALS_DIRECTORY")
        if not directory or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
            raise ConfigError("Systemd credential is unavailable")
        path = Path(directory) / name
    else:
        path = Path(reference)
        if not path.is_absolute():
            raise ConfigError("Credential file paths must be absolute")
    # Open first, then check the actual descriptor to avoid symlink/check races.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ConfigError("Credential files must be regular files with mode 0600 or 0400")
            value = stream.read(16385).strip()
    except (OSError, UnicodeError):
        raise ConfigError("Cannot read a credential file") from None
    if not value or len(value) > 16384 or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise ConfigError("Credential file must contain a nonempty single printable ASCII value")
    return value


def cookie(reference: str) -> str:
    value = secret(reference)
    if any(c in value for c in ";,\" "):
        raise ConfigError("Roblox cookie file must contain the cookie value only")
    return value


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a nonempty string")
    return value.strip()


def keys(obj, allowed, name):
    if not isinstance(obj, dict) or set(obj) - allowed:
        raise ConfigError(f"Invalid or unknown keys in {name}")


def reference(value, name):
    value = text(value, name)
    if not value.startswith("credential:") and not Path(value).is_absolute():
        raise ConfigError(f"{name} must be an absolute path or credential:name")
    if value.startswith("credential:") and not re.fullmatch(r"credential:[a-zA-Z0-9_-]+", value):
        raise ConfigError(f"Invalid {name} credential name")
    return value


def https_base(value):
    value = text(value, "push.base_url").rstrip("/")
    u = urlsplit(value)
    try:
        valid_port = u.port is None or 1 <= u.port <= 65535
    except ValueError:
        valid_port = False
    if (u.scheme != "https" or not u.hostname or u.username or u.password
            or u.query or u.fragment or u.path not in ("", "/") or not valid_port):
        raise ConfigError("push.base_url must be an HTTPS origin without credentials, query, or path")
    return value


@dataclass(frozen=True)
class Config:
    observer_user_id: int
    target_user_id: int
    cookie_file: str
    push_provider: str
    push_base_url: str
    push_topic_file: str | None
    push_token_file: str | None
    push_user_file: str | None
    state_dir: Path
    poll_seconds: int = 15
    offline_confirmations: int = 2
    timeout_seconds: int = 8
    alert_ttl_seconds: int = 300
    outage_alert_seconds: int = 300
    notify_on_startup: bool = True

    @property
    def scope(self):
        return f"{self.observer_user_id}:{self.target_user_id}"

    def credentials(self):
        values = {"roblox_cookie": cookie(self.cookie_file)}
        for name, ref in (("topic", self.push_topic_file), ("token", self.push_token_file),
                          ("user", self.push_user_file)):
            if ref:
                values[name] = secret(ref)
        if "topic" in values and not re.fullmatch(r"[-_A-Za-z0-9]{1,64}", values["topic"]):
            raise ConfigError("Invalid ntfy topic in credential file")
        return values


def load(path: str | Path) -> Config:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigError("Cannot read valid JSON configuration") from None
    keys(obj, {"observer_user_id", "target_user_id", "cookie_file", "push", "state_dir",
               "poll_seconds", "offline_confirmations", "timeout_seconds", "alert_ttl_seconds",
               "outage_alert_seconds", "notify_on_startup"}, "configuration")
    push = obj.get("push")
    keys(push, {"provider", "base_url", "topic_file", "token_file", "user_file"}, "push")
    provider = push.get("provider", "ntfy")
    if provider not in ("ntfy", "pushover"):
        raise ConfigError("push.provider must be ntfy or pushover")
    if provider == "ntfy":
        if push.get("user_file"):
            raise ConfigError("push.user_file is for Pushover only")
        base_url = https_base(push.get("base_url", "https://ntfy.sh"))
        topic_file = reference(push.get("topic_file"), "push.topic_file")
        token_file = reference(push["token_file"], "push.token_file") if push.get("token_file") else None
        user_file = None
    else:
        if push.get("topic_file") or push.get("base_url"):
            raise ConfigError("Pushover uses its fixed official endpoint")
        base_url, topic_file = "https://api.pushover.net", None
        token_file = reference(push.get("token_file"), "push.token_file")
        user_file = reference(push.get("user_file"), "push.user_file")
    observer = integer(obj.get("observer_user_id"), "observer_user_id", 1, 2**63 - 1)
    target = integer(obj.get("target_user_id"), "target_user_id", 1, 2**63 - 1)
    if observer == target:
        raise ConfigError("observer_user_id and target_user_id must identify different accounts")
    state_dir = Path(text(obj.get("state_dir"), "state_dir"))
    if not state_dir.is_absolute():
        raise ConfigError("state_dir must be absolute")
    startup = obj.get("notify_on_startup", True)
    if type(startup) is not bool:
        raise ConfigError("notify_on_startup must be a boolean")
    return Config(observer, target, reference(obj.get("cookie_file"), "cookie_file"),
                  provider, base_url, topic_file, token_file, user_file, state_dir,
                  integer(obj.get("poll_seconds", 15), "poll_seconds", 10, 300),
                  integer(obj.get("offline_confirmations", 2), "offline_confirmations", 2, 10),
                  integer(obj.get("timeout_seconds", 8), "timeout_seconds", 1, 30),
                  integer(obj.get("alert_ttl_seconds", 300), "alert_ttl_seconds", 30, 3600),
                  integer(obj.get("outage_alert_seconds", 300), "outage_alert_seconds", 60, 3600),
                  startup)
