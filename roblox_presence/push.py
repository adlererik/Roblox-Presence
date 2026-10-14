"""Minimal notifications via an existing hosted ntfy or Pushover service."""

import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from .config import secret
from .http import ServiceError, require_success


def message(event):
    observed = datetime.fromtimestamp(event["created_at"], timezone.utc).strftime("%H:%M UTC")
    kind = event["kind"]
    if kind == "online":
        return "Roblox connection online", f"Your Roblox connection is online. Observed at {observed}. Time to play together!"
    if kind == "outage":
        return "Roblox monitor needs attention", "Presence checks are failing. Check the monitor status on its host."
    if kind == "recovery":
        return "Roblox monitor recovered", "Presence checks are working again."
    return "Roblox monitor test", "Test notification from your Roblox Presence Monitor."


class Push:
    def __init__(self, config, http):
        self.config, self.http = config, http

    def send(self, event):
        title, body = message(event)
        click = f"https://www.roblox.com/users/{self.config.target_user_id}/profile"
        if self.config.push_provider == "ntfy":
            topic = secret(self.config.push_topic_file)
            # Validate immediately before use as secrets can be rotated.
            import re
            if not re.fullmatch(r"[-_A-Za-z0-9]{1,64}", topic):
                raise ServiceError("ntfy_topic_invalid")
            headers = {"Content-Type": "application/json"}
            if self.config.push_token_file:
                headers["Authorization"] = "Bearer " + secret(self.config.push_token_file)
            payload = {"topic": topic, "title": title, "message": body, "priority": 4,
                       "tags": ["video_game" if event["kind"] == "online" else "information_source"]}
            if event["kind"] == "online":
                payload["click"] = click
            data = require_success(self.http.request("POST", self.config.push_base_url + "/",
                                                     headers=headers, body=json.dumps(payload).encode()), "ntfy")
            if (data.get("event") != "message" or not isinstance(data.get("id"), str)
                    or not data["id"] or data.get("topic") != topic):
                raise ServiceError("ntfy_invalid_acknowledgement")
        else:
            payload = {"token": secret(self.config.push_token_file),
                       "user": secret(self.config.push_user_file), "title": title,
                       "message": body, "priority": "1"}
            if event["kind"] == "online":
                payload.update(url=click, url_title="Open Roblox profile")
            data = require_success(self.http.request("POST", "https://api.pushover.net/1/messages.json",
                                                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                                                     body=urlencode(payload).encode()), "pushover")
            if type(data.get("status")) is not int or data["status"] != 1 or not data.get("request"):
                raise ServiceError("pushover_invalid_acknowledgement")
