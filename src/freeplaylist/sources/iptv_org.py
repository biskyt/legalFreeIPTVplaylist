"""Live and FAST channels from the iptv-org database, kept only when the automatic rules find them official.

iptv-org lists every stream it can find, including unofficial restreams, so nothing is accepted on its say-so.
A stream is accepted when its host belongs to the broadcaster, a known FAST service, or a licensed distribution
service (see config/live_hosts.yaml), and the channel isn't blocked, NSFW or closed. Manual decisions in
config/live_allowlist.yaml override the rules.
"""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from .. import languages, net
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
    return {n: net.get_json(f"{API}/{n}.json") for n in files}


def country_code(code: str) -> str:
    """iptv-org writes the United Kingdom as UK; ISO 3166-1 (and tvg-country) uses GB."""
    return "GB" if code.upper() == "UK" else code.upper()


def feed_countries(feed: dict | None, channel: dict) -> list[str]:
    """Where a feed is meant to be watched: its broadcast area's countries (c/DE, s/US-CA), else the channel's."""
    out: list[str] = []
    for area in (feed or {}).get("broadcast_area") or []:
        kind, _, code = area.partition("/")
        if kind in ("c", "s") and code:
            cc = country_code(code.split("-")[0])
            if cc not in out:
                out.append(cc)
    if not out and channel.get("country"):
        out.append(country_code(channel["country"]))
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
class Platform:
    name: str
    credit: str
    host: str
    path_prefix: str | None = None
    host_prefix: str | None = None  # the first host label must start with this (e.g. "xumo-")

    def matches(self, host: str, path: str) -> bool:
        return (_within(host, self.host) and (not self.path_prefix or path.startswith(self.path_prefix))
                and (not self.host_prefix or host.startswith(self.host_prefix)))


@dataclass
class Rules:
    platforms: list[Platform]
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
            platforms=[Platform(**p) for p in hosts.get("platforms") or []],
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
    platform: Platform | None = None


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
    for p in rules.platforms:
        if p.matches(host, parsed.path):
            return Verdict(True, f"fast:{p.credit}", p)
    if any(_within(host, d) for d in rules.distribution):
        return Verdict(True, "official:distribution")
    if any(_within(host, d) for d in rules.broadcaster_hosts):
        return Verdict(True, "official:broadcaster-host")

    # The remaining rules rely on the URL alone, so a stream that needs spoofed request headers (a common sign
    # of a scraped restream) is not accepted through them.
    official = _matches_website(host, parsed.path, channel, rules)
    if official is None and host in (website_hosts or {}).get(channel.get("website") or "", ()):
        official = "official:website-link"  # the broadcaster's own site points to this host
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


def unverified_sites(api: dict[str, list], rules: Rules) -> set[str]:
    """Websites of channels that have unverified streams and no accepted one: worth checking for stream links."""
    channels = {c["id"]: c for c in api["channels"]}
    blocked = {b["channel"]: b.get("reason", "blocked") for b in api["blocklist"]}
    unverified: set[str] = set()
    accepted: set[str] = set()
    for s in api["streams"]:
        channel = channels.get(s.get("channel"))
        v = evaluate(s, channel, blocked, rules)
        if v.accepted:
            accepted.add(channel["id"])
        elif v.reason == "unverified":
            unverified.add(channel["id"])
    return {channels[c]["website"] for c in unverified - accepted if channels[c].get("website")}


def build(api: dict[str, list], rules: Rules,
          website_hosts: dict[str, set[str]] | None = None) -> tuple[list[Entry], list[Decision]]:
    """One Entry per channel feed. Each carries every accepted stream for that feed, best first, in
    extra["candidates"]; the health check keeps the first that works."""
    channels = {c["id"]: c for c in api["channels"]}
    blocked = {b["channel"]: b.get("reason", "blocked") for b in api["blocklist"]}
    feeds = {(f["channel"], f["id"]): f for f in api["feeds"]}
    main_feeds = {f["channel"]: f for f in api["feeds"] if f.get("is_main")}
    languages.load(api.get("languages") or [])
    languages.load_countries(api.get("countries") or [])
    categories = {c["id"]: c["name"] for c in api["categories"]}
    logos: dict[tuple[str, str | None], str] = {}
    for logo in api["logos"]:
        if logo.get("in_use", True):
            logos.setdefault((logo["channel"], logo.get("feed")), logo["url"])

    decisions: list[Decision] = []
    grouped: dict[tuple[str, str | None], list[tuple[dict, Verdict]]] = {}
    for s in api["streams"]:
        channel = channels.get(s.get("channel"))
        v = evaluate(s, channel, blocked, rules, website_hosts)
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
        if verdict.platform:
            group, source = verdict.platform.name, verdict.platform.credit
        else:
            cats = [categories.get(c, c.title()) for c in channel.get("categories") or [] if c != "general"]
            group, source = cats[0] if cats else "General", SOURCE
        # A country code leads the group name ("DE | News"), for players that only filter on group names. Britain
        # is written UK there, as IPTV providers and players expect; tvg-country keeps the ISO code (GB).
        prefix = ("UK" if countries[0] == "GB" else countries[0]) if countries else "INT"
        group = f"{prefix} | {group}"
        catchup = (rules.allow.get(cid) or {}).get("catchup") or {}
        entries.append(Entry(
            id=f"{cid}@{feed_id}" if feed_id else cid,
            title=title,
            url=best["url"],
            group=group,
            kind="live",
            source=source,
            logo=logos.get((cid, feed_id)) or logos.get((cid, None)),
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
                "platform": verdict.platform.name if verdict.platform else None,
                "country": channel.get("country"),
                "reason": verdict.reason,
                "labels": best.get("labels", []),
                "candidates": [
                    {"url": s["url"], "user_agent": s.get("user_agent"), "referrer": s.get("referrer"),
                     "labels": s.get("labels", [])}
                    for s, _ in found
                ],
            },
        ))
    return entries, decisions
