"""Finds which stream hosts a broadcaster's own website points to.

Many official streams sit on general-purpose CDNs whose addresses don't name the broadcaster, so the URL alone
can't show they're official. If the broadcaster's website (its home page, or a "live" page linked from it)
mentions the stream's host, the broadcaster is publishing that stream itself.

Results are cached per website in state/website_links.json and refreshed weekly (staggered), so a daily build
fetches only a few hundred pages.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import zlib
from concurrent.futures import ThreadPoolExecutor

from .. import net

# Links worth following from a home page to its live player: "live", "direct", "en vivo", "ao vivo", "canlı"...
_LIVE_LINK = re.compile(r"live|direct|directo|vivo|watch|stream|player|senal|canli|tv-?online|en-?ligne", re.I)
_HREF = re.compile(r"""href\s*=\s*["']([^"'#>]+)""", re.I)
# Host names in URLs, including JSON-escaped ones in inline scripts ("https:\/\/cdn.example.com\/live").
_HOST = re.compile(r"""(?:https?:)?\\?/\\?/([a-z0-9][a-z0-9.-]*\.[a-z]{2,63})""", re.I)
PAGE_BYTES = 512 * 1024


def hosts_in(text: str) -> set[str]:
    return {h.lower().rstrip(".") for h in _HOST.findall(text)}


def live_links(text: str, base: str, limit: int = 2) -> list[str]:
    """Up to `limit` same-site links that look like a live player page."""
    site = urllib.parse.urlparse(base).hostname or ""
    found: list[str] = []
    for href in _HREF.findall(text):
        url = urllib.parse.urljoin(base, href.strip())
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or (parsed.hostname or "") != site:
            continue
        if _LIVE_LINK.search(parsed.path) and url not in found and url.rstrip("/") != base.rstrip("/"):
            found.append(url)
            if len(found) >= limit:
                break
    return found


def _page(url: str, fetch) -> str:
    p = fetch(url, user_agent=net.USER_AGENT, timeout=10, max_bytes=PAGE_BYTES)
    return p.body.decode("utf-8", "replace") if p.status in (200, 206) else ""


def site_hosts(url: str, fetch=net.probe) -> tuple[set[str], bool]:
    """(hosts mentioned by a website's home page and up to two of its live pages, whether the home page loaded)."""
    home = _page(url, fetch)
    hosts = hosts_in(home)
    for link in live_links(home, url):
        hosts |= hosts_in(_page(link, fetch))
    return hosts, bool(home)


def find_hosts(sites: set[str], state: dict, *, ttl_days: int = 7, max_sites: int = 2500, workers: int = 16,
               fetch=net.probe) -> dict[str, set[str]]:
    """{website: hosts it mentions} for every site, fetching at most `max_sites` stale or new ones this run."""
    now = time.time()

    def stale(site: str) -> bool:
        rec = state.get(site)
        if rec is None:
            return True
        if not rec.get("ok"):
            return now - rec.get("t", 0) > 86400  # a site that didn't load is retried the next day
        jitter = (zlib.crc32(site.encode()) % ttl_days) * 86400  # spread refreshes over the week
        return now - rec.get("t", 0) > ttl_days * 86400 + jitter

    # New sites first, then the oldest results.
    todo = sorted((s for s in sites if stale(s)), key=lambda s: state.get(s, {}).get("t", 0))[:max_sites]
    with ThreadPoolExecutor(workers) as pool:
        for site, (hosts, ok) in zip(todo, pool.map(lambda s: site_hosts(s, fetch), todo), strict=True):
            state[site] = {"t": now, "ok": ok, "hosts": sorted(hosts)}
    return {s: set(state[s]["hosts"]) for s in sites if s in state}
