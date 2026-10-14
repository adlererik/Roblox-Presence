"""Observe a configured connection using the authorized observer's session."""

import json

from .config import cookie
from .http import ServiceError, require_success

USERS = "https://users.roblox.com"
PRESENCE = "https://presence.roblox.com/v1/presence/users"
PRESENCE_NAMES = {0: "offline", 1: "online", 2: "in_game", 3: "in_studio"}


def parse_presence(data, target_user_id):
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
    # Location, game IDs, timestamps, etc. are intentionally not retained.
    return status != 0


class Roblox:
    def __init__(self, config, http):
        self.config, self.http = config, http

    def validate_target(self):
        data = require_success(self.http.request("GET", f"{USERS}/v1/users/{self.config.target_user_id}"),
                               "roblox")
        if type(data.get("id")) is not int or data["id"] != self.config.target_user_id:
            raise ServiceError("roblox_target_invalid")
        if data.get("isBanned") is True:
            raise ServiceError("roblox_target_banned")

    def poll(self):
        headers = {"Cookie": ".ROBLOSECURITY=" + cookie(self.config.cookie_file)}
        identity = require_success(self.http.request("GET", f"{USERS}/v1/users/authenticated",
                                                     headers=headers), "roblox")
        if type(identity.get("id")) is not int or identity["id"] != self.config.observer_user_id:
            raise ServiceError("roblox_observer_mismatch")
        headers["Content-Type"] = "application/json"
        body = json.dumps({"userIds": [self.config.target_user_id]}).encode("utf-8")
        result = self.http.request("POST", PRESENCE, headers=headers, body=body)
        csrf = result.headers.get("x-csrf-token")
        if result.status == 403 and csrf:
            if len(csrf) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in csrf):
                raise ServiceError("roblox_invalid_csrf")
            result = self.http.request("POST", PRESENCE,
                                       headers={**headers, "X-CSRF-Token": csrf}, body=body)
        return parse_presence(require_success(result, "roblox"), self.config.target_user_id)


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
