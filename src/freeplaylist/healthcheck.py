"""Drops dead streams, the way a player would find them.

A stream passes when it answers 200 and, for HLS, returns a playlist whose first variant playlist also loads.
Live entries may carry several candidate streams (extra["candidates"]); the first that works is used.
Results are remembered in state/health.json:
  * a stream that has never been seen working is dropped as soon as it fails;
  * a stream that worked before gets one grace run, and is dropped after 2 consecutive failures;
  * a 401/403/451 on a stream iptv-org labels "Geo-blocked" is kept, as the build runs from a US data centre.
Only a sample of VOD entries (plus all new ones) is checked each run; archive.org files rarely disappear, and a
VOD entry is only dropped for a definite answer (such as 404), not for a timeout or server error, which archive.org
returns at busy times.
"""

from __future__ import annotations

import random
import threading
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date

from . import net
from .models import Decision, Entry

GEO_STATUSES = {401, 403, 451}
MAX_FAILS = 2


@dataclass
class Result:
    status: str  # "ok", "geo", "dead", or "error" (no definite answer: timeout, connection or server error)
    detail: str = ""


def _is_playlist(body: bytes) -> bool:
    return body.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U")


def _first_variant(body: bytes) -> str | None:
    """The first media playlist a master playlist points to, or None for a media playlist."""
    text = body.decode("utf-8", "replace")
    if "#EXT-X-STREAM-INF" not in text:
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.startswith("#"):
                    return nxt.strip()
    return None


class Checker:
    def __init__(self, *, workers: int = 48, per_host: int = 4, timeout: float = 8, probe=net.probe):
        self.workers = workers
        self.timeout = timeout
        self._probe = probe
        self._lock = threading.Lock()
        self._hosts: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(per_host))

    def _get(self, url: str, ua: str | None, ref: str | None) -> net.Probe:
        host = urllib.parse.urlparse(url).hostname or ""
        with self._lock:
            sem = self._hosts[host]
        with sem:
            return self._probe(url, user_agent=ua, referrer=ref, timeout=self.timeout)

    def check(self, url: str, ua: str | None = None, ref: str | None = None, labels=()) -> Result:
        p = self._get(url, ua, ref)
        if p.status in (200, 206):
            path = urllib.parse.urlparse(url).path.lower()
            hls = path.endswith((".m3u8", ".m3u")) or _is_playlist(p.body)
            if not hls:
                return Result("ok")
            if not _is_playlist(p.body):
                return Result("dead", "not a playlist")
            variant = _first_variant(p.body)
            if variant is None:
                return Result("ok")
            v = self._get(urllib.parse.urljoin(p.final_url, variant), ua, ref)
            if v.status in (200, 206) and _is_playlist(v.body):
                return Result("ok")
            return Result(_failure(v), f"variant: {v.error or 'not a playlist'}")
        if p.status in GEO_STATUSES and "Geo-blocked" in labels:
            return Result("geo", p.error or "")
        return Result(_failure(p), p.error or f"HTTP {p.status}")


def _failure(p: net.Probe) -> str:
    """'error' when the server gave no definite answer, otherwise 'dead'."""
    if p.status is None or p.status >= 500 or p.status == 429:
        return "error"
    return "dead"


def _candidates(e: Entry) -> list[dict]:
    return e.extra.get("candidates") or [
        {"url": e.url, "user_agent": e.user_agent, "referrer": e.referrer, "labels": e.extra.get("labels", [])}
    ]


def run(entries: list[Entry], state: dict, checker: Checker, *, sample: float = 1.0, today: str | None = None,
        rng: random.Random | None = None, keep_on_error: bool = False) -> tuple[list[Entry], list[Decision]]:
    """Entries that pass (in the same order), and a decision for every entry that was checked.
    With keep_on_error, an entry whose checks all ended without a definite answer is kept unchanged."""
    today = today or date.today().isoformat()
    rng = rng or random.Random()

    def wanted(e: Entry) -> bool:
        # Always check what is new, failed last time, or never confirmed working; sample the rest.
        unsure = any(not (state.get(c["url"]) or {}).get("ok") or state[c["url"]].get("fails")
                     for c in _candidates(e))
        return sample >= 1 or unsure or rng.random() < sample

    def task(e: Entry) -> tuple[Entry | None, Decision, list[tuple[str, Result]]]:
        tried: list[tuple[dict, Result]] = []
        geo = None
        for c in _candidates(e):
            r = checker.check(c["url"], c.get("user_agent"), c.get("referrer"), c.get("labels", ()))
            tried.append((c, r))
            if r.status == "ok":
                return _use(e, c), Decision("health", e.id, True, "ok"), _urls(tried)
            if r.status == "geo" and geo is None:
                geo = c
        if geo is not None:
            return _use(e, geo), Decision("health", e.id, True, "geo-blocked"), _urls(tried)
        if keep_on_error and tried and all(r.status == "error" for _, r in tried):
            return e, Decision("health", e.id, True, f"unconfirmed: {tried[0][1].detail}"), []
        # Grace for a stream that worked last time: keep it unless it has now failed MAX_FAILS runs in a row.
        for c, _ in tried:
            rec = state.get(c["url"]) or {}
            if rec.get("ok") and rec.get("fails", 0) + 1 < MAX_FAILS:
                return _use(e, c), Decision("health", e.id, True, "grace"), _urls(tried)
        detail = tried[0][1].detail if tried else ""
        return None, Decision("health", e.id, False, f"dead: {detail}".strip()), _urls(tried)

    checked = [e for e in entries if wanted(e)]
    with ThreadPoolExecutor(checker.workers) as pool:
        outcomes = dict(zip((id(e) for e in checked), pool.map(task, checked), strict=True))

    kept, decisions = [], []
    for e in entries:
        if id(e) not in outcomes:
            kept.append(e)
            continue
        new, decision, tried = outcomes[id(e)]
        decisions.append(decision)
        for url, r in tried:
            rec = state.setdefault(url, {})
            if r.status in ("dead", "error"):
                rec["fails"] = rec.get("fails", 0) + 1
            else:
                rec.update(ok=today, fails=0)
        if new is not None:
            kept.append(new)
    return kept, decisions


def _urls(tried: list[tuple[dict, Result]]) -> list[tuple[str, Result]]:
    return [(c["url"], r) for c, r in tried]


def _use(e: Entry, c: dict) -> Entry:
    return replace(e, url=c["url"], user_agent=c.get("user_agent"), referrer=c.get("referrer"))


def prune(state: dict, keep_urls: set[str]) -> dict:
    """Forget streams that no longer appear in any source."""
    return {u: v for u, v in state.items() if u in keep_urls}
