"""Small HTTP helpers on the standard library (no third-party HTTP client needed)."""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

USER_AGENT = "freeplaylist/0.1 (+https://github.com/biskyt/licenseFreeIPTVplaylist)"
# Some streaming servers refuse unknown clients; probes look like an ordinary player.
PLAYER_AGENT = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def get_bytes(url: str, *, timeout: float = 60, retries: int = 3) -> bytes:
    """GET with retries and exponential backoff on network errors and 5xx/429 responses."""
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429 or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def get_json(url: str, **kw):
    return json.loads(get_bytes(url, **kw))


@dataclass
class Probe:
    status: int | None  # HTTP status, or None when the request never got a response
    final_url: str
    body: bytes
    error: str | None = None


def probe(url: str, *, user_agent: str | None = None, referrer: str | None = None, timeout: float = 8,
          max_bytes: int = 65536) -> Probe:
    """Fetch the start of a URL the way a player would, following redirects."""
    # No Range header: some live servers reject it. Reading stops after max_bytes and the connection is closed.
    headers = {"User-Agent": user_agent or PLAYER_AGENT}
    if referrer:
        headers["Referer"] = referrer
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                body = resp.read(max_bytes)
            except http.client.IncompleteRead as e:
                body = e.partial  # live servers often cut the connection; what arrived still counts
            return Probe(resp.status, resp.geturl(), body)
    except urllib.error.HTTPError as e:
        return Probe(e.code, url, b"", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001 - any failure to fetch just means the stream doesn't work
        reason = getattr(e, "reason", e)
        return Probe(None, url, b"", f"{type(e).__name__}: {reason}")
