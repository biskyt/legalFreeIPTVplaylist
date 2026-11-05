"""Finds which stream hosts a broadcaster's own website points to.

Many official streams sit on general-purpose CDNs whose addresses don't name the broadcaster, so the URL alone
can't show they're official. If the broadcaster's website (its home page, or a "live" page linked from it)
mentions the stream's host, the broadcaster is publishing that stream itself.

Results are cached per website in state/website_links.json. Each night refreshes one of seven groups of sites
(config/schedule.yaml), so a nightly build fetches only a few hundred pages.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .. import net, schedule
from ..progress import Progress

# Links worth following from a home page to its live player: "live", "direct", "en vivo", "ao vivo", "canlı"...
_LIVE_LINK = re.compile(r"live|direct|directo|vivo|watch|stream|player|senal|canli|tv-?online|en-?ligne", re.I)
_HREF = re.compile(r"""href\s*=\s*["']([^"'#>]+)""", re.I)
# Host names in URLs, including JSON-escaped ones in inline scripts ("https:\/\/cdn.example.com\/live").
_HOST = re.compile(r"""(?:https?:)?\\?/\\?/([a-z0-9][a-z0-9.-]*\.[a-z]{2,63})""", re.I)
PAGE_BYTES = 512 * 1024
# Links to a site's terms and conditions, in the labels and addresses sites use: "Terms of use", "Conditions
# d'utilisation", "Nutzungsbedingungen", "Aviso legal", "Condizioni"... Privacy and cookie pages are not terms.
_ANCHOR = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"'#>][^"'>]*)["'][^>]*>(.*?)</a>""", re.I | re.S)
_TERMS = re.compile(r"terms|conditions|\btos\b|legal|mentions[-_ ]l[eé]gales|aviso[-_ ]legal|condiciones|"
                    r"nutzungsbedingungen|\bagb\b|condizioni|termini[-_ ](?:e|di)|disclaimer|utilisation|regulamin|"
                    r"voorwaarden|villkor|vilk[aå]r|kullan[iı]m|\bcgu\b|\bcgv\b", re.I)
_NOT_TERMS = re.compile(r"privacy|cookie|datenschutz|confidential|privacidad|vie[-_ ]priv", re.I)
TERMS_TTL = 30 * 86400


def hosts_in(text: str) -> set[str]:
    return {h.lower().rstrip(".") for h in _HOST.findall(text)}


def live_links(text: str, base: str, limit: int = 2) -> list[str]:
    """Up to `limit` same-site links that look like a live player page."""
    site = urllib.parse.urlparse(base).hostname or ""
    found: list[str] = []
    for href in _HREF.findall(text):
        try:
            url = urllib.parse.urljoin(base, href.strip())
            parsed = urllib.parse.urlparse(url)
            hostname = parsed.hostname or ""
        except ValueError:  # malformed links (e.g. "http://[broken") are just skipped
            continue
        if parsed.scheme not in ("http", "https") or hostname != site:
            continue
        if _LIVE_LINK.search(parsed.path) and url not in found and url.rstrip("/") != base.rstrip("/"):
            found.append(url)
            if len(found) >= limit:
                break
    return found


def terms_links(text: str, base: str, limit: int = 3) -> list[str]:
    """Up to `limit` links on a page that look like the site's terms and conditions."""
    found: list[str] = []
    for href, label in _ANCHOR.findall(text):
        label = " ".join(re.sub(r"<[^>]+>", " ", label).split())
        try:
            url = urllib.parse.urljoin(base, href.strip())
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            continue
        # A footer link has a short label and a short address; a news headline that mentions "conditions" or a
        # deadline ("termini") doesn't.
        segments = [x for x in parsed.path.split("/") if x]
        short_label = len(label) <= 45 and _TERMS.search(label)
        short_path = len(segments) <= 3 and bool(segments) and len(segments[-1]) <= 40 and _TERMS.search(segments[-1])
        if not (short_label or short_path) or _NOT_TERMS.search(href + label):
            continue
        if parsed.scheme in ("http", "https") and url not in found:
            found.append(url)
            if len(found) >= limit:
                break
    return found


def _page(url: str, fetch) -> str:
    p = fetch(url, user_agent=net.USER_AGENT, timeout=10, max_bytes=PAGE_BYTES)
    return p.body.decode("utf-8", "replace") if p.status in (200, 206) else ""


def site_hosts(url: str, fetch=net.probe) -> tuple[set[str], bool]:
    """(hosts mentioned by a website's home page and up to two of its live pages, whether the home page loaded).
    Any error counts as "didn't load", so one odd website never stops the build; it's retried another night."""
    try:
        home = _page(url, fetch)
        hosts = hosts_in(home)
        for link in live_links(home, url):
            hosts |= hosts_in(_page(link, fetch))
        return hosts, bool(home)
    except Exception:  # noqa: BLE001
        return set(), False


def find_hosts(sites: set[str], state: dict, tonight: schedule.Tonight, *, everything: bool = False,
               max_sites: int = 2500, workers: int = 16, fetch=net.probe) -> dict[str, set[str]]:
    """{website: hosts it mentions} for every site. Sites are split into the schedule's nightly groups by name and
    one group is re-fetched each night, so each site is checked about weekly; new sites are fetched at once."""
    now = time.time()

    def stale(site: str) -> bool:
        rec = state.get(site)
        if rec is None or everything:
            return True
        age = now - rec.get("t", 0)
        if tonight.is_turn(net.host_of(site)):
            return age > 20 * 3600  # its night: refresh unless already done today
        return age > (tonight.groups + 1) * 86400  # safety net if a night was missed

    # New sites first, then the oldest results; spread over hosts so no one server gets a run of requests.
    todo = sorted((s for s in sites if stale(s)), key=lambda s: state.get(s, {}).get("t", 0))[:max_sites]
    todo = net.round_robin(todo, key=net.host_of)
    with Progress("website check", len(todo)) as progress, ThreadPoolExecutor(workers) as pool:
        for site, (hosts, ok) in zip(todo, pool.map(lambda s: site_hosts(s, fetch), todo), strict=True):
            state[site] = {"t": now, "ok": ok, "hosts": sorted(hosts)}
            progress.done()
    return {s: set(state[s]["hosts"]) for s in sites if s in state}


def find_terms(sites: set[str], state: dict, *, fetch=net.probe, max_sites: int = 400,
               workers: int = 16) -> dict[str, list[str]]:
    """{website: links to its terms and conditions} for the sites that have one on their home page. Each site is
    looked at about once a month (a missing answer is retried after a day), at most `max_sites` a night, oldest
    first, spread over hosts."""
    now = time.time()

    def stale(site: str) -> bool:
        rec = state.get(site)
        return rec is None or now - rec["t"] > (TERMS_TTL if rec["ok"] else 86400)

    todo = sorted((s for s in sites if stale(s)), key=lambda s: state.get(s, {}).get("t", 0))[:max_sites]
    todo = net.round_robin(todo, key=net.host_of)

    def look(site: str) -> tuple[list[str], bool]:
        try:
            home = _page(site, fetch)
            return terms_links(home, site), bool(home)
        except Exception:  # noqa: BLE001 - one odd website never stops the build
            return [], False

    with Progress("terms check", len(todo)) as progress, ThreadPoolExecutor(workers) as pool:
        for site, (links, ok) in zip(todo, pool.map(look, todo), strict=True):
            state[site] = {"t": now, "ok": ok, "terms": links}
            progress.done()
    return {s: state[s]["terms"] for s in sites if state.get(s, {}).get("terms")}
