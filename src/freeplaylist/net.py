"""Small HTTP helpers on the standard library (no third-party HTTP client needed).

Every request goes through one shared per-host limiter, so the build stays polite whichever part makes the
request: a few connections per host at most, a short gap between requests to the same host, and a back-off
when a host signals it's overloaded (429, 503, or a Retry-After header) that applies to that host only.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

USER_AGENT = "freeplaylist/0.1 (+https://github.com/biskyt/legalFreeIPTVplaylist)"
# Some streaming servers refuse unknown clients; probes look like an ordinary player.
PLAYER_AGENT = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
THROTTLED = {429, 503}


def host_of(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


class HostLimiter:
    """Per-host concurrency, spacing and back-off, shared by every thread."""

    def __init__(self, per_host: int = 4, min_interval: float = 0.25, max_backoff: float = 120):
        self.per_host = per_host
        self.min_interval = min_interval
        self.max_backoff = max_backoff
        self._lock = threading.Lock()
        self._slots: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(self.per_host))
        self._next: dict[str, float] = defaultdict(float)  # earliest time the next request to a host may start
        self._backoff: dict[str, float] = defaultdict(float)  # current back-off per host, in seconds

    @contextmanager
    def slot(self, url: str):
        host = host_of(url)
        with self._lock:
            sem = self._slots[host]
        with sem:
            with self._lock:
                start = max(time.monotonic(), self._next[host])
                self._next[host] = start + self.min_interval
            wait = start - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            yield

    def throttled(self, url: str, retry_after: str | None = None) -> float:
        """Record that a host asked us to slow down; returns how long that host is paused for."""
        host = host_of(url)
        with self._lock:
            if retry_after and retry_after.strip().isdigit():
                pause = min(float(retry_after), self.max_backoff)
            else:
                pause = min(max(self._backoff[host] * 2, 2.0), self.max_backoff)
            self._backoff[host] = pause
            self._next[host] = max(self._next[host], time.monotonic() + pause)
            return pause

    def ok(self, url: str) -> None:
        with self._lock:
            self._backoff[host_of(url)] /= 2  # recover gradually after a throttled period


LIMITER = HostLimiter()


def round_robin(items: Iterable, key: Callable[[object], str]) -> list:
    """Items reordered so consecutive ones go to different hosts: one from each host in turn."""
    queues: dict[str, list] = defaultdict(list)
    for item in items:
        queues[key(item)].append(item)
    out: list = []
    lists = list(queues.values())
    for i in range(max((len(q) for q in lists), default=0)):
        out.extend(q[i] for q in lists if i < len(q))
    return out


def get_bytes(url: str, *, timeout: float = 60, retries: int = 3) -> bytes:
    """GET with retries: network errors and 5xx back off exponentially; 429/503 pause the host (Retry-After)."""
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            with LIMITER.slot(url):
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read()
            LIMITER.ok(url)
            return body
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429 or attempt == retries:
                raise
            if e.code in THROTTLED:
                LIMITER.throttled(url, e.headers.get("Retry-After"))  # the next slot() waits for it
                continue
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
          max_bytes: int = 65536, retries: int = 1) -> Probe:
    """Fetch the start of a URL the way a player would, following redirects. A throttled answer (429/503) is
    retried after the host's back-off, so a busy server isn't mistaken for a dead stream."""
    # No Range header: some live servers reject it. Reading stops after max_bytes and the connection is closed.
    headers = {"User-Agent": user_agent or PLAYER_AGENT}
    if referrer:
        headers["Referer"] = referrer
    for attempt in range(retries + 1):
        try:
            with LIMITER.slot(url):
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    try:
                        body = resp.read(max_bytes)
                    except http.client.IncompleteRead as e:
                        body = e.partial  # live servers often cut the connection; what arrived still counts
                    LIMITER.ok(url)
                    return Probe(resp.status, resp.geturl(), body)
        except urllib.error.HTTPError as e:
            if e.code in THROTTLED and attempt < retries:
                LIMITER.throttled(url, e.headers.get("Retry-After"))
                continue
            return Probe(e.code, url, b"", f"HTTP {e.code}")
        except Exception as e:  # noqa: BLE001 - any failure to fetch just means the stream doesn't work
            reason = getattr(e, "reason", e)
            return Probe(None, url, b"", f"{type(e).__name__}: {reason}")
    raise AssertionError("unreachable")
