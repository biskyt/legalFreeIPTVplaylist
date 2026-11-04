"""Live channels from the iptv-org database, classified by the automatic rules.

iptv-org lists every stream it can find, including unofficial restreams, so nothing is accepted on its say-so.
Each stream gets a reason (see config/live_hosts.yaml): its host belongs to the broadcaster, the broadcaster's
website refers to it, and so on, for a channel that isn't blocked, NSFW or closed. Which reasons count as proof
is decided in config/legal.yaml. Manual decisions in config/live_allowlist.yaml override the rules.
"""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .. import languages, net
from .. import logos as logos_
from ..models import Decision, Entry

API = "https://iptv-org.github.io/api"
FILES = ("channels", "streams", "blocklist", "feeds", "logos", "categories", "languages", "countries")
SOURCE = "iptv-org"

# Second-level labels under which ccTLDs register names (example.co.uk, example.com.au, example.gob.mx ...).
_SECOND_LEVEL = {"co", "com", "net", "org", "gov", "edu", "ac", "or", "ne", "go", "gob", "gv", "mil", "nic", "info"}
# Xtream-panel URLs (/live/<user>/<pass>/<id>.ts) and logins in the query string; not ordinary paths that happen
# to start with /live/ (e.g. Euronews' /live/eds/euronews-pl/26382/index.m3u8).
_CREDENTIALS = re.compile(
    r"/(live|movie|series)/[^/]+/[^/]+/\d+\.(ts|m3u8?|mp4|mkv|avi)(\?|$)|[?&](username|password)=", re.I
)
_HEIGHT = re.compile(r"(\d+)p")


def fetch_api(api_dir: Path | None = None, files: tuple[str, ...] = FILES) -> dict[str, list]:
    """The iptv-org API files, from a local directory (tests, offline runs) or the live API."""
    if api_dir:
        return {n: json.loads(p.read_text(encoding="utf-8")) if (p := api_dir / f"{n}.json").exists() else []
                for n in files}
    with ThreadPoolExecutor(len(files)) as pool:  # independent downloads, fetched side by side
        return dict(zip(files, pool.map(lambda n: net.get_json(f"{API}/{n}.json"), files), strict=True))


def feed_countries(feed: dict | None, channel: dict) -> list[str]:
    """Where a feed is meant to be watched: its broadcast area's countries (c/DE, s/US-CA), else the channel's."""
    out: list[str] = []
    for area in (feed or {}).get("broadcast_area") or []:
        kind, _, code = area.partition("/")
        if kind in ("c", "s") and code:
            cc = languages.country_code(code.split("-")[0])
            if cc not in out:
                out.append(cc)
    if not out and channel.get("country"):
        out.append(languages.country_code(channel["country"]))
    return out


def registrable(host: str) -> str:
    """example.co.uk for www.cdn.example.co.uk; a close-enough stand-in for the Public Suffix List."""
    parts = host.lower().rstrip(".").split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _within(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


@dataclass
class Rules:
    distribution: list[str]
    broadcaster_hosts: dict[str, str]
    generic_cdns: list[str]
    denied_domains: list[str]
    generic_tokens: set[str]
    allow: dict[str, dict] = field(default_factory=dict)
    deny: set[str] = field(default_factory=set)

    @classmethod
    def from_config(cls, hosts: dict, allowlist: dict) -> Rules:
        return cls(
            distribution=list(hosts.get("distribution") or []),
            broadcaster_hosts=dict(hosts.get("broadcaster_hosts") or {}),
            generic_cdns=list(hosts.get("generic_cdns") or []),
            denied_domains=list(hosts.get("denied_domains") or []),
            generic_tokens=set(hosts.get("generic_tokens") or []),
            allow={a["channel"]: a for a in allowlist.get("allow") or []},
            deny={d["channel"] if isinstance(d, dict) else d for d in allowlist.get("deny") or []},
        )


@dataclass
class Verdict:
    accepted: bool
    reason: str


def evaluate(stream: dict, channel: dict | None, blocked: dict[str, str], rules: Rules,
             website_hosts: dict[str, set[str]] | None = None) -> Verdict:
    """Decide whether one iptv-org stream is an official, legally free stream."""
    if channel is None:
        return Verdict(False, "no-channel")
    cid = channel["id"]
    if cid in blocked:
        return Verdict(False, f"blocklist:{blocked[cid]}")
    if channel.get("is_nsfw") or "xxx" in (channel.get("categories") or []):
        return Verdict(False, "nsfw")
    if channel.get("closed") or channel.get("replaced_by"):
        return Verdict(False, "closed")
    if cid in rules.deny:
        return Verdict(False, "denied-channel")

    url = stream["url"]
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return Verdict(False, "unsupported-url")
    if _is_ip(host):
        return Verdict(False, "ip-host")
    if _CREDENTIALS.search(url):
        return Verdict(False, "credentials-in-url")
    if any(_within(host, d) for d in rules.denied_domains):
        return Verdict(False, "denied-domain")

    allowed = rules.allow.get(cid)
    if allowed is not None:
        if not allowed.get("hosts") or any(_within(host, h) for h in allowed["hosts"]):
            return Verdict(True, "allowlist")
        return Verdict(False, "allowlist-other-host")
    if any(_within(host, d) for d in rules.distribution):
        return Verdict(True, "official:distribution")
    if any(_within(host, d) for d in rules.broadcaster_hosts):
        return Verdict(True, "official:broadcaster-host")

    # The remaining rules rely on the URL alone, so a stream that needs spoofed request headers (a common sign
    # of a scraped restream) is not accepted through them.
    official = _matches_website(host, parsed.path, channel, rules)
    if official in (None, "official:cdn-named") and host in (website_hosts or {}).get(channel.get("website") or "", ()):
        official = "official:website-link"  # the broadcaster's own site points to this host (better proof than a name)
    if official is None:
        return Verdict(False, "unverified")
    if stream.get("user_agent") or stream.get("referrer"):
        return Verdict(False, "needs-spoofed-headers")
    return Verdict(True, official)


def _matches_website(host: str, path: str, channel: dict, rules: Rules) -> str | None:
    website = urllib.parse.urlparse(channel.get("website") or "").hostname
    if not website:
        return None
    site = registrable(website)
    if registrable(host) == site:
        return "official:website-domain"
    cdn = next((d for d in rules.generic_cdns if _within(host, d)), None)
    if cdn is None:
        return None
    token = site.split(".")[0]
    if len(token) < 2 or token in rules.generic_tokens:
        return None
    labels = [label for label in host[: -len(cdn)].rstrip(".").split(".") if label]
    # "dwamdstream102" names dw.com; "telesur" (5+ letters) names telesurtv.net.
    if any(label.startswith(token) or (len(label) >= 5 and token.startswith(label)) for label in labels):
        return "official:cdn-named"
    if len(token) >= 4 and token in path.lower():
        return "official:cdn-named"
    return None


def _height(stream: dict) -> int:
    m = _HEIGHT.search(stream.get("quality") or "")
    return int(m.group(1)) if m else 0


def unverified_sites(api: dict[str, list], rules: Rules, accept: set[str] | None = None) -> dict[str, set[str]]:
    """{website: hosts of the streams to prove} for channels that have streams not yet proven and no proven one:
    worth checking for stream links. With `accept`, a stream accepted for another reason (such as a name in a CDN
    path) doesn't count as proven."""
    channels = {c["id"]: c for c in api["channels"]}
    blocked = {b["channel"]: b.get("reason", "blocked") for b in api["blocklist"]}
    unverified: set[str] = set()
    accepted: set[str] = set()
    hosts: dict[str, set[str]] = {}
    for s in api["streams"]:
        channel = channels.get(s.get("channel"))
        v = evaluate(s, channel, blocked, rules)
        if v.accepted and (accept is None or v.reason in accept):
            accepted.add(channel["id"])
        elif v.accepted or v.reason == "unverified":
            unverified.add(channel["id"])
            hosts.setdefault(channel["id"], set()).add(net.host_of(s["url"]))
    out: dict[str, set[str]] = {}
    for c in unverified - accepted:
        if channels[c].get("website"):
            out.setdefault(channels[c]["website"], set()).update(hosts[c])
    return out


def build(api: dict[str, list], rules: Rules, website_hosts: dict[str, set[str]] | None = None,
          accept: set[str] | None = None) -> tuple[list[Entry], list[Decision]]:
    """One Entry per channel feed. Each carries every accepted stream for that feed, best first, in
    extra["candidates"]; the health check keeps the first that works.

    With `accept`, only streams accepted for one of those reasons count (see config/legal.yaml); the others are
    recorded as "not-proven:<reason>", so a channel's group and credit come from a stream that is kept."""
    channels = {c["id"]: c for c in api["channels"]}
    blocked = {b["channel"]: b.get("reason", "blocked") for b in api["blocklist"]}
    feeds = {(f["channel"], f["id"]): f for f in api["feeds"]}
    main_feeds = {f["channel"]: f for f in api["feeds"] if f.get("is_main")}
    categories = {c["id"]: c["name"] for c in api["categories"]}
    logos: dict[tuple[str, str | None], list[str]] = {}
    for logo in api["logos"]:
        if logo.get("in_use", True):
            logos.setdefault((logo["channel"], logo.get("feed")), []).append(logo["url"])

    decisions: list[Decision] = []
    grouped: dict[tuple[str, str | None], list[tuple[dict, Verdict]]] = {}
    for s in api["streams"]:
        channel = channels.get(s.get("channel"))
        v = evaluate(s, channel, blocked, rules, website_hosts)
        if v.accepted and accept is not None and v.reason not in accept:
            v = Verdict(False, f"not-proven:{v.reason}")
        decisions.append(Decision(SOURCE, f'{s.get("channel") or "?"} {s["url"]}', v.accepted, v.reason))
        if v.accepted:
            grouped.setdefault((channel["id"], s.get("feed")), []).append((s, v))

    entries = []
    for (cid, feed_id), found in grouped.items():
        channel = channels[cid]
        found.sort(key=lambda sv: ("Geo-blocked" in sv[0].get("labels", []), -_height(sv[0])))
        best, verdict = found[0]
        feed = feeds.get((cid, feed_id)) if feed_id else main_feeds.get(cid)
        title = channel["name"]
        if feed and not feed.get("is_main"):
            title = f"{title} {feed['name']}"
        countries = feed_countries(feed, channel)
        cats = [categories.get(c, c.title()) for c in channel.get("categories") or [] if c != "general"]
        group, source = cats[0] if cats else "General", SOURCE
        # A country code leads the group name ("DE | News"), for players that only filter on group names. Britain
        # is written UK there, as IPTV providers and players expect; tvg-country keeps the ISO code (GB).
        prefix = ("UK" if countries[0] == "GB" else countries[0]) if countries else "INT"
        group = f"{prefix} | {group}"
        catchup = (rules.allow.get(cid) or {}).get("catchup") or {}
        # The feed's own logos first, then the channel's; see logos.py for why the others are kept.
        logo, logo_alternatives = logos_.split(logos.get((cid, feed_id), []) + logos.get((cid, None), []))
        entries.append(Entry(
            id=f"{cid}@{feed_id}" if feed_id else cid,
            title=title,
            url=best["url"],
            group=group,
            kind="live",
            source=source,
            logo=logo,
            user_agent=best.get("user_agent"),
            referrer=best.get("referrer"),
            catchup=catchup.get("mode"),
            catchup_days=catchup.get("days"),
            catchup_source=catchup.get("source"),
            page=channel.get("website"),
            languages=languages.normalise_all((feed or {}).get("languages")),
            countries=countries,
            extra={
                "broadcaster": channel["name"],
                "main_feed": bool(feed and feed.get("is_main")),
                "country": channel.get("country"),
                "reason": verdict.reason,
                "labels": best.get("labels", []),
                **({"logo_alternatives": logo_alternatives} if logo_alternatives else {}),
                "candidates": [
                    {"url": s["url"], "user_agent": s.get("user_agent"), "referrer": s.get("referrer"),
                     "labels": s.get("labels", []), "reason": v.reason}
                    for s, v in found
                ],
            },
        ))
    return entries, decisions
