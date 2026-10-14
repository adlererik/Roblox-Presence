"""Bounded HTTPS requests with no redirects, cookie jar, or proxy inheritance."""

import json
import socket
import ssl
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener


class ServiceError(Exception):
    """Only a fixed safe code reaches logs; upstream bodies and URLs do not."""

    def __init__(self, code, retry_after=None, status=None):
        self.code, self.retry_after, self.status = code, retry_after, status
        super().__init__(code)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self):
        try:
            data = json.loads(self.body)
        except (ValueError, UnicodeError, RecursionError):
            raise ServiceError("invalid_json") from None
        if not isinstance(data, dict):
            raise ServiceError("invalid_response")
        return data


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_after(headers, now=None):
    value = headers.get("retry-after", "")
    try:
        if value.isdigit():
            return min(86400, max(1, int(value)))
        seconds = parsedate_to_datetime(value).timestamp() - (time.time() if now is None else now)
        return min(86400, max(1, seconds))
    except (ValueError, TypeError, OverflowError):
        return None


class Http:
    def __init__(self, timeout=8, opener=None):
        self.timeout = timeout
        self.opener = opener or build_opener(ProxyHandler({}), NoRedirect(),
                                             HTTPSHandler(context=ssl.create_default_context()))

    def request(self, method, url, *, headers=None, body=None):
        if not url.startswith("https://"):
            raise ServiceError("https_required")
        req = Request(url, data=body, method=method,
                      headers={"User-Agent": "Roblox-Presence/0.1.0", "Accept": "application/json",
                               **(headers or {})})
        try:
            try:
                stream = self.opener.open(req, timeout=self.timeout)
            except HTTPError as exc:
                stream = exc
            with stream:
                data = stream.read(131073)
                if len(data) > 131072:
                    raise ServiceError("response_too_large")
                return Response(stream.code, {k.lower(): v for k, v in stream.headers.items()}, data)
        except ServiceError:
            raise
        except (URLError, OSError, socket.timeout, HTTPException, ValueError, UnicodeError):
            raise ServiceError("network_error") from None


def require_success(response, service):
    status = response.status
    if not 200 <= status < 300:
        code = ("authentication_failed" if status in (401, 403) else
                "rate_limited" if status == 429 else
                "redirect_refused" if 300 <= status < 400 else "http_error")
        raise ServiceError(f"{service}_{code}", retry_after(response.headers), status)
    return response.json()
