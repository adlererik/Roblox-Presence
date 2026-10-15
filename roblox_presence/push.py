"""Minimal notifications via an existing hosted ntfy or Pushover service."""

import json
from datetime import datetime
from urllib.parse import urlencode

from .config import secret
from .http import ServiceError, require_success
from .roblox import clean_text


def message(event):
    kind = event["kind"]
    if kind in ("online", "playing"):
        details = event.get("details") or {}
        if isinstance(details, str):
            details = json.loads(details)
        observed = datetime.fromtimestamp(details.get("observed_at", event["created_at"])).astimezone().strftime("%d %b %Y at %H:%M:%S %Z (UTC%z)")
        username = clean_text(details.get("username"), 40)
        display = clean_text(details.get("display_name"), 80)
        name = f"{display} (@{username})" if display and username else display or ("@" + username if username else "Your Roblox connection")
        game = clean_text(details.get("game_name"))
        if game:
            activity = f"Playing: {game}."
        elif details.get("presence_type") == "in_game":
            activity = "In a game; Roblox has not shared its name."
        elif details.get("presence_type") == "in_studio":
            activity = "Using Roblox Studio."
        else:
            activity = "No game reported yet."
        return f"{name} {'started playing' if kind == 'playing' else 'is online'}", f"{activity}\nObserved {observed} (server time)."
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
        # Names and the authorized game description are deliberately in the message.
        # Cookies, numeric IDs, place/server IDs and profile URLs are never sent.
        click = "https://www.roblox.com/home"
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
                       "tags": ["video_game" if event["kind"] in ("online", "playing") else "information_source"]}
            if event["kind"] in ("online", "playing"):
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
            if event["kind"] in ("online", "playing"):
                payload.update(url=click, url_title="Open Roblox")
            data = require_success(self.http.request("POST", "https://api.pushover.net/1/messages.json",
                                                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                                                     body=urlencode(payload).encode()), "pushover")
            if type(data.get("status")) is not int or data["status"] != 1 or not data.get("request"):
                raise ServiceError("pushover_invalid_acknowledgement")
