"""Channel logos that every viewer can load.

iptv-org's logo list is mostly links to Imgur, which has refused the UK since September 2025. It doesn't fail: it
answers with an ordinary image saying "not available in your region", so a player can't tell the logo didn't load
and shows that message on every channel. Where iptv-org lists another logo for a channel, the playlist uses the
first of those that loads; the rest stay on Imgur (there's nothing else to use). Checks are cached in
state/logo_check.json: a working logo for 30 days, a missing one for 3.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from . import net
from .models import Entry
from .progress import Progress

log = logging.getLogger("freeplaylist")
AVOID = {"i.imgur.com"}  # hosts that refuse some regions with an image instead of an error
TTL_OK, TTL_BAD = 30 * 86400, 3 * 86400


def split(urls: list[str]) -> tuple[str | None, list[str]]:
    """(the logo to use unless something better is found, other logos worth trying instead). The alternatives are
    only wanted when the first is on a host in AVOID, and never include one."""
    if not urls:
        return None, []
    first = urls[0]
    if net.host_of(first) not in AVOID:
        return first, []
    return first, list(dict.fromkeys(u for u in urls[1:] if net.host_of(u) not in AVOID))


def is_image(body: bytes) -> bool:
    """Whether a response starts like a PNG, JPEG, GIF, WebP or SVG (headers are no use: some CDNs send
    application/octet-stream for images)."""
    head = body[:512]
    return (head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8")) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
            or b"<svg" in head)


def _check(url: str, probe) -> bool | None:
    """True if the logo loads as an image, False if it definitely doesn't, None if the answer isn't clear."""
    ua = net.USER_AGENT if net.host_of(url) in net.IDENTIFY_TO else None
    p = probe(url, user_agent=ua, timeout=10, max_bytes=2048)
    if p.status in (200, 206):
        return is_image(p.body)
    if p.status is not None and p.status < 500 and p.status != 429:
        return False
    return None  # timeout, server error or throttled: try again another night


def prefer_open_hosts(entries: list[Entry], state: dict, probe=net.probe, now: float | None = None) -> int:
    """Switch each entry whose logo is on an AVOID host to the first alternative that loads (the alternatives are
    in extra["logo_alternatives"], which is removed). Returns how many were switched."""
    now = now or time.time()

    def fresh(url: str) -> bool:
        rec = state.get(url)
        return bool(rec) and now - rec["t"] < (TTL_OK if rec["ok"] else TTL_BAD)

    wanted = sorted({u for e in entries for u in e.extra.get("logo_alternatives", [])})
    todo = net.round_robin([u for u in wanted if not fresh(u)], key=net.host_of)
    with Progress("logo check", len(todo)) as progress, ThreadPoolExecutor(8) as pool:
        for url, ok in zip(todo, pool.map(lambda u: _check(u, probe), todo), strict=True):
            if ok is not None:
                state[url] = {"t": now, "ok": ok}
            progress.done()
    switched = 0
    for e in entries:
        for url in e.extra.pop("logo_alternatives", []):
            if (state.get(url) or {}).get("ok") and fresh(url):
                e.logo = url
                switched += 1
                break
    for url in [u for u in state if u not in wanted]:
        del state[url]  # no longer an alternative to anything
    return switched
