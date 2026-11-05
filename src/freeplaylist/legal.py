"""What counts as proof that an entry may be published, and the evidence shown for each one that is kept.

The rules are in config/legal.yaml. Live streams are filtered where they're built (iptv_org.build(accept=...)), so
this module takes care of the rest: owners' takedown requests, films and episodes, and the evidence text and links
that credits.html and catalog.json show for every entry. Anything without a basis is dropped with a reason that
report.json records.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from . import net
from .models import Decision, Entry
from .sources.iptv_org import registrable

SOURCE = "legal"


@dataclass(frozen=True)
class Evidence:
    basis: str  # machine-readable: the live reason, "source:<key>" or "published-before-<year>"
    title: str  # short label for the basis
    text: str  # one sentence saying why the entry may be published
    links: tuple[tuple[str, str], ...] = ()  # (label, url) pointing at the evidence
    terms: tuple[str, ...] = ()  # the owner's terms and conditions, where we found them

    def as_dict(self) -> dict:
        return {"basis": self.basis, "title": self.title, "text": self.text, "links": [list(x) for x in self.links],
                "terms": list(self.terms)}


def accepted_live_reasons(policy: dict) -> set[str]:
    return set(policy.get("live") or {})


def permissions(policy: dict) -> dict[str, dict]:
    """{channel id: its entry in config/permissions.yaml}: the live channels whose owners allow their use."""
    return {p["channel"]: p for p in policy.get("permissions") or []}


def _takedown(e: Entry, policy: dict) -> str | None:
    channel = e.id.partition("@")[0]
    domains = {registrable(h) for h in (urllib.parse.urlparse(e.page or "").hostname, net.host_of(e.url)) if h}
    for t in policy.get("takedowns") or []:
        if (channel in (t.get("channels") or []) or e.id in (t.get("entries") or [])
                or e.source in (t.get("sources") or [])
                or any(registrable(d) in domains for d in t.get("domains") or [])):
            return t["owner"]
    return None


def _vod_basis(e: Entry, vod: dict) -> str | None:
    """The basis for a film or episode, or None if there's nothing but someone's say-so."""
    if e.source in (vod.get("sources") or {}):
        return f"source:{e.source}"
    cutoff = vod.get("public_domain_before", 1931)
    if e.source in (vod.get("dated_sources") or []) and e.kind != "series" and e.year and e.year < cutoff:
        return f"published-before-{cutoff}"
    return None


def apply(entries: list[Entry], policy: dict) -> tuple[list[Entry], list[Decision]]:
    """The entries that may be published, and a decision for each one dropped (live streams without a basis were
    already dropped when they were built)."""
    kept, dropped = [], []
    vod = policy.get("vod") or {}
    for e in entries:
        owner = _takedown(e, policy)
        if owner:
            dropped.append(Decision(SOURCE, e.id, False, f"takedown:{owner}"))
        elif e.kind == "live" and e.id.partition("@")[0] not in permissions(policy):
            dropped.append(Decision(SOURCE, e.id, False, "not-proven:no-permission"))
        elif e.kind != "live" and _vod_basis(e, vod) is None:
            dropped.append(Decision(SOURCE, e.id, False, "not-proven:uploader-claim"))
        else:
            kept.append(e)
    return kept, dropped


def evidence(e: Entry, policy: dict, sources: dict | None = None) -> Evidence:
    """Why an entry that passed apply() may be published, with links to the evidence."""
    if e.kind == "live":
        grant = permissions(policy).get(e.id.partition("@")[0]) or {}
        reason = next((c.get("reason") for c in e.extra.get("candidates") or [] if c["url"] == e.url), None)
        reason = reason or e.extra.get("reason") or ""
        rule = (policy.get("live") or {}).get(reason) or {}
        served = (rule.get("text") or "").format(host=net.host_of(e.url), site=e.page or "its website")
        quote = " ".join(str(grant.get("quote", "")).split())
        text = f"The owner's terms say: \u201c{quote}\u201d"
        if grant.get("note"):
            text += " " + " ".join(str(grant["note"]).split())
        if served:
            text += " The stream is the owner's own: " + served[0].lower() + served[1:]
        links = [("Where it says so", grant["url"])] if grant.get("url") else []
        if e.page:
            links.append(("Channel website", e.page))
        return Evidence("permission", "The owner's terms allow it", text, tuple(links),
                        (grant["url"],) if grant.get("url") else ())
    vod = policy.get("vod") or {}
    basis = _vod_basis(e, vod) or ""
    links = [("Source page", e.page)] if e.page else []
    if e.license and e.license.startswith("http"):
        links.append(("Licence", e.license))
    if e.imdb:
        links.append(("IMDb", f"https://www.imdb.com/title/{e.imdb}/"))
    if basis.startswith("source:"):
        reason = " ".join(str((vod.get("sources") or {}).get(e.source, "")).split())
        who = (sources or {}).get(e.source, {}).get("name", e.source)
        terms = (sources or {}).get(e.source, {}).get("terms")
        return Evidence(basis, f"Accepted source: {who}", reason, tuple(links), (terms,) if terms else ())
    cutoff = vod.get("public_domain_before", 1931)
    text = (f"Published in {e.year}: works published before {cutoff} are in the US public domain. "
            "The year is the one in the Internet Archive's own record for the item.")
    terms = (sources or {}).get(e.source, {}).get("terms")
    return Evidence(basis, f"Public domain by age (published before {cutoff})", text, tuple(links),
                    (terms,) if terms else ())
