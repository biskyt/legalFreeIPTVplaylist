"""Openly licensed Dutch archive film from Open Beelden (Netherlands Institute for Sound and Vision).

Records come from the site's OAI-PMH feed (about 11,000 records, 100 per request), kept in
state/open_beelden.json. The first harvest is spread over several runs (see `harvest`); after that, runs only
ask for records changed since the last one.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from .. import languages, net
from ..models import Decision, Entry
from .internet_archive import license_kind

OAI = "https://www.openbeelden.nl/feeds/oai/"
SITE = "https://www.openbeelden.nl"
SOURCE = "open-beelden"
NS = {"o": "http://www.openarchives.org/OAI/2.0/", "oi": "http://www.openbeelden.nl/oai/"}
log = logging.getLogger("freeplaylist")
_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?$")


def seconds(extent: str | None) -> float | None:
    """ISO 8601 durations as the feed writes them: PT46S, PT1M30S, PT1H2M."""
    m = _DURATION.match(extent or "")
    if not m or not any(m.groups()):
        return None
    h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def parse_record(rec: ET.Element) -> tuple[str, dict | None]:
    """(OAI identifier, the fields we keep) for one record; None for a deleted record."""
    header = rec.find("o:header", NS)
    ident = header.findtext("o:identifier", "", NS)
    if header.get("status") == "deleted":
        return ident, None
    md = rec.find("o:metadata", NS)
    oi = md[0] if md is not None and len(md) else None
    if oi is None:
        return ident, None

    def text(tag: str) -> str:
        return (oi.findtext(f"oi:{tag}", "", NS) or "").strip()

    media = {(m.get("format"), (m.text or "").strip()) for m in oi.findall("oi:medium", NS)}
    mp4 = sorted((u for f, u in media if u.endswith(".mp4")), key=lambda u: "hd" not in u)
    thumb = next((u for f, u in media if f == "thumbnail"), None)
    page = text("attributionURL")
    return ident, {
        "title": text("title"),
        "description": text("description")[:600] or None,
        "date": text("date"),
        "seconds": seconds(text("extent")),
        "mp4": next((u for f, u in sorted(media) if f == "hd" and u.endswith(".mp4")), mp4[0] if mp4 else None),
        "thumb": urllib.parse.urljoin(SITE, thumb) if thumb else None,
        "license": text("license"),
        "language": text("language"),
        "attribution": text("attributionName") or text("creator"),
        "page": urllib.parse.urljoin(SITE, page) if page else None,
    }


def _pages(params: dict, records: dict, fetch, pause: float, budget: list[int]) -> bool:
    """Fetch one OAI-PMH list (following resumption tokens) into `records`; False if the page budget ran out."""
    url = f"{OAI}?{urllib.parse.urlencode(params)}"
    while url:
        if budget[0] <= 0:
            return False
        budget[0] -= 1
        root = ET.fromstring(fetch(url, timeout=90, retries=2))
        if root.find("o:error", NS) is not None:  # noRecordsMatch
            return True
        for rec in root.iterfind(".//o:record", NS):
            ident, fields = parse_record(rec)
            if fields is None:
                records.pop(ident, None)
            else:
                records[ident] = fields
        token = root.findtext(".//o:resumptionToken", "", NS).strip()
        # The server stalls on a percent-encoded "!", which its tokens are full of, so those stay as they are.
        url = f"{OAI}?verb=ListRecords&resumptionToken={urllib.parse.quote(token, safe='!')}" if token else ""
        if url:
            time.sleep(pause)
    return True


def harvest(state: dict, fetch=net.get_bytes, pause: float = 1.0, max_pages: int = 30,
            first_year: int = 2007) -> dict:
    """Bring state["records"] up to date within a page budget.

    The feed is slow (sometimes most of a minute per 100 records) and its resumption tokens expire, so the
    first harvest goes one year of record dates at a time, remembering finished years in state["years"], and
    continues on later runs. Once every year is done, runs only ask for records changed since the last one.
    A failure keeps what arrived; the next run carries on.
    """
    records = state.setdefault("records", {})
    done = set(state.setdefault("years", []))
    today = datetime.now(UTC)
    budget = [max_pages]
    try:
        if state.get("last"):
            if _pages({"verb": "ListRecords", "metadataPrefix": "oai_oi", "from": state["last"]}, records, fetch,
                      pause, budget):
                state["last"] = today.strftime("%Y-%m-%d")
            return state
        for year in range(first_year, today.year + 1):
            if year in done:
                continue
            window = {"verb": "ListRecords", "metadataPrefix": "oai_oi", "from": f"{year}-01-01",
                      "until": f"{year}-12-31"}
            if not _pages(window, records, fetch, pause, budget):
                log.info("open beelden: page budget used; %d records so far, continuing next run", len(records))
                return state
            done.add(year)
            state["years"] = sorted(done)
        state["last"] = today.strftime("%Y-%m-%d")  # every year harvested: from now on, changes only
    except Exception as e:  # noqa: BLE001 - use what we have; the next run continues
        log.warning("open beelden: harvest stopped (%s); using %d records", e, len(records))
    return state


def build(cfg: dict, state: dict, fetch=net.get_bytes, pause: float = 1.0) -> tuple[list[Entry], list[Decision]]:
    harvest(state, fetch, pause, max_pages=cfg.get("max_pages", 30))
    decisions: list[Decision] = []
    picked: list[tuple[str, dict]] = []
    for ident, r in state["records"].items():
        kind = license_kind(r.get("license"))
        if kind not in ("pd", "cc-by", "cc-by-sa"):
            reason = f"license:{kind or 'none'}"
        elif not r.get("mp4"):
            reason = "no-mp4"
        elif (r.get("seconds") or 0) < cfg.get("min_minutes", 3) * 60:
            reason = "too-short"
        else:
            picked.append((ident, r))
            continue
        decisions.append(Decision(SOURCE, ident, False, reason))
    picked.sort(key=lambda ir: -(ir[1]["seconds"] or 0))
    entries = []
    for ident, r in picked[: cfg.get("max", 400)]:
        year = int(r["date"][:4]) if r.get("date", "")[:4].isdigit() else None
        title = f"{r['title']} ({year})" if year and str(year) not in r["title"] else r["title"]
        entries.append(Entry(
            id=f"openbeelden.{ident.rsplit(':', 1)[-1]}",
            title=title,
            url=r["mp4"],
            group=cfg.get("group", "Documentaries: Dutch archive"),
            kind="movie",
            source=SOURCE,
            logo=r.get("thumb"),
            duration=round(r["seconds"]),
            year=year,
            languages=languages.normalise_all(r.get("language")) or ["nld"],
            countries=["NL"],
            license=r.get("license"),
            attribution=f"{r['title']} by {r['attribution']}, {r.get('license')}, via Open Beelden"
            if r.get("attribution") else f"{r['title']}, {r.get('license')}, via Open Beelden",
            page=r.get("page"),
            description=r.get("description"),
        ))
        decisions.append(Decision(SOURCE, ident, True, license_kind(r.get("license")) or ""))
    decisions += [Decision(SOURCE, i, False, "cap") for i, _ in picked[cfg.get("max", 400):]]
    return entries, decisions
