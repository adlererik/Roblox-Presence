"""Observe a configured connection using the authorized observer's session."""

import json
import time
import unicodedata

from .http import ServiceError, require_success
from .session import Session

USERS = "https://users.roblox.com"
PRESENCE = "https://presence.roblox.com/v1/presence/users"
PRESENCE_NAMES = {0: "offline", 1: "online", 2: "in_game", 3: "in_studio"}


def clean_text(value, limit=160):
    """Bound API display text and remove control / directional formatting characters."""
    if not isinstance(value, str):
        return ""
    return " ".join("".join(c for c in value if not unicodedata.category(c).startswith("C")).split())[:limit]


def parse_presence(data, target_user_id):
    return presence_entry(data, target_user_id)["userPresenceType"] != 0


def presence_entry(data, target_user_id):
    entries = data.get("userPresences")
    if not isinstance(entries, list):
        raise ServiceError("roblox_presence_missing")
    matches = [x for x in entries if isinstance(x, dict) and type(x.get("userId")) is int
               and x["userId"] == target_user_id]
    if len(matches) != 1:
        raise ServiceError("roblox_presence_missing")
    status = matches[0].get("userPresenceType")
    if type(status) is not int or status not in PRESENCE_NAMES:
        raise ServiceError("roblox_presence_unknown")
    return matches[0]


class Roblox:
    def __init__(self, config, http):
        self.config, self.http = config, http
        self.session = Session(config)
        self.details = {}
        self.profile = {}
        self.profile_retry_at = 0

    def validate_target(self):
        data = require_success(self.http.request("GET", f"{USERS}/v1/users/{self.config.target_user_id}"),
                               "roblox")
        if type(data.get("id")) is not int or data["id"] != self.config.target_user_id:
            raise ServiceError("roblox_target_invalid")
        if data.get("isBanned") is True:
            raise ServiceError("roblox_target_banned")
        self.profile = {"username": clean_text(data.get("name"), 40),
                        "display_name": clean_text(data.get("displayName"), 80)}

    def notification_details(self):
        # Optional public profile data never turns a valid presence result into a failure.
        # Retry-After applies to this optional endpoint independently of presence polling.
        now = time.monotonic()
        if now >= self.profile_retry_at:
            self.profile_retry_at = now + 3600
            try:
                self.validate_target()
            except ServiceError as exc:
                self.profile_retry_at = now + max(300, exc.retry_after or 0)
        return {**self.details, **self.profile}

    def poll(self):
        headers = {"Cookie": ".ROBLOSECURITY=" + self.session.value()}
        identity_response = self.http.request("GET", f"{USERS}/v1/users/authenticated", headers=dict(headers))
        identity = require_success(identity_response, "roblox")
        if type(identity.get("id")) is not int or identity["id"] != self.config.observer_user_id:
            raise ServiceError("roblox_observer_mismatch")
        rotated = self.session.update(identity_response)
        if rotated:
            headers["Cookie"] = ".ROBLOSECURITY=" + rotated
        headers["Content-Type"] = "application/json"
        body = json.dumps({"userIds": [self.config.target_user_id]}).encode("utf-8")
        result = self.http.request("POST", PRESENCE, headers=dict(headers), body=body)
        csrf = result.headers.get("x-csrf-token")
        if result.status == 403 and csrf:
            if len(csrf) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in csrf):
                raise ServiceError("roblox_invalid_csrf")
            rotated = self.session.update(result)
            if rotated:
                headers["Cookie"] = ".ROBLOSECURITY=" + rotated
            result = self.http.request("POST", PRESENCE,
                                       headers={**headers, "X-CSRF-Token": csrf}, body=body)
        entry = presence_entry(require_success(result, "roblox"), self.config.target_user_id)
        status = entry["userPresenceType"]
        # lastLocation is the authorized presence description. Never look up hidden
        # locations or retain place/server identifiers. It is only a game in type 2.
        game = clean_text(entry.get("lastLocation")) if status == 2 else ""
        if game.casefold() in {"playing", "game", "in game"}:
            game = ""
        self.details = {"presence_type": PRESENCE_NAMES[status], "game_name": game}
        self.session.update(result)
        return status != 0


def resolve_username(http, username):
    if not isinstance(username, str) or not 3 <= len(username) <= 20:
        raise ServiceError("invalid_username")
    data = require_success(http.request("POST", f"{USERS}/v1/usernames/users",
                                        headers={"Content-Type": "application/json"},
                                        body=json.dumps({"usernames": [username],
                                                         "excludeBannedUsers": True}).encode()), "roblox")
    entries = data.get("data")
    if (not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict)
            or type(entries[0].get("id")) is not int):
        raise ServiceError("roblox_username_not_found")
    return entries[0]["id"]
