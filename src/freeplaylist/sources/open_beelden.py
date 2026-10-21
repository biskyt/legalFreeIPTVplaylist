"""Openly licensed Dutch archive film from Open Beelden (Netherlands Institute for Sound and Vision).

Records come from the site's OAI-PMH feed (about 11,000 records, 100 per request), kept in
state/open_beelden.json. The first harvest is spread over several runs (see `harvest`); after that, runs only
ask for records changed since the last one.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta

from .. import languages, net
from ..models import Decision, Entry
from ..progress import Progress
from .internet_archive import _movie_title, _year, license_kind

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

    media = [(m.get("format"), (m.text or "").strip()) for m in oi.findall("oi:medium", NS)]
    mp4 = [u for f, u in sorted(media, key=lambda fu: fu[0] != "hd") if u.endswith(".mp4")]  # HD first
    thumb = next((u for f, u in media if f == "thumbnail"), None)
    page = text("attributionURL")
    return ident, {
        "title": text("title"),
        "description": text("description")[:600] or None,
        "date": text("date"),
        "seconds": seconds(text("extent")),
        "mp4": mp4[0] if mp4 else None,
        "thumb": urllib.parse.urljoin(SITE, thumb) if thumb else None,
        "license": text("license"),
        "language": text("language"),
        "attribution": text("attributionName") or text("creator"),
        "page": urllib.parse.urljoin(SITE, page) if page else None,
    }


class _BudgetUsed(Exception):
    pass


class _TooSlow(Exception):
    pass


def _page(url: str, records: dict, fetch) -> str:
    """One OAI-PMH response into `records`; returns its resumption token ("" when it was the last page, or when
    the request matched nothing). Raises _TooSlow when the server doesn't answer in time."""
    try:
        body = fetch(url, timeout=60, retries=0)
    except (OSError, urllib.error.URLError) as e:  # timeouts and server errors: usually a window too big for it
        raise _TooSlow(str(e)) from e
    root = ET.fromstring(body)
    error = root.find("o:error", NS)
    if error is not None:
        if error.get("code") == "noRecordsMatch":  # an empty window: done
            return ""
        # Anything else (e.g. an expired resumption token) means this list wasn't finished.
        raise RuntimeError(f"OAI-PMH {error.get('code')}: {(error.text or '').strip()}")
    for rec in root.iterfind(".//o:record", NS):
        ident, fields = parse_record(rec)
        if fields is None:
            records.pop(ident, None)
        else:
            records[ident] = fields
    return root.findtext(".//o:resumptionToken", "", NS).strip()


def _resume(token: str) -> str:
    # The server stalls on a percent-encoded "!", which its tokens are full of, so those stay as they are.
    return f"{OAI}?verb=ListRecords&resumptionToken={urllib.parse.quote(token, safe='!')}"


def _list_url(start: str, end: str) -> str:
    params = {"verb": "ListRecords", "metadataPrefix": "oai_oi", "from": start, "until": end}
    return f"{OAI}?{urllib.parse.urlencode(params)}"


def _days(window: list[str]) -> int:
    return (date.fromisoformat(window[1]) - date.fromisoformat(window[0])).days


def _halves(start: str, end: str) -> list[list[str]]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    mid = a + (b - a) / 2
    return [[(mid + timedelta(days=1)).isoformat(), end], [start, mid.isoformat()]]  # the earlier half is next


def harvest(state: dict, fetch=net.get_bytes, pause: float = 1.0, max_pages: int = 30,
            first_day: str = "1800-01-01", rewalk_days: int = 30) -> dict:
    """Bring state["records"] up to date within a request budget per run.

    The feed filters by the films' own dates, which are uneven (most from a few decades), answers slowly and
    erratically (large lists often not at all), and its resumption tokens expire. So the archive is walked in
    date windows kept in state["windows"], carried on over as many runs as it takes:
    * a window that fits on one page is done in one request, however long (empty centuries cost one request);
    * a window longer than a month with more pages, or one the server doesn't answer in time, is split in half;
    * a window of a month or less is read to its end; a single day that still times out waits for the next walk.
    When every window is done, state["walked"] records the date; the whole archive is walked again after
    `rewalk_days`, which picks up new and changed records. A failure keeps what arrived.
    """
    records = state.setdefault("records", {})
    for old in ("months", "last"):  # from the earlier harvests
        state.pop(old, None)
    today = datetime.now(UTC).date()
    walked = state.get("walked")
    if not state.get("windows") and walked and (today - date.fromisoformat(walked)).days < rewalk_days:
        return state  # walked recently; records are up to date
    if not state.get("windows"):
        state["windows"] = [[first_day, today.isoformat()], *state.pop("skipped", [])]
    windows = state["windows"]
    budget = [max_pages]
    progress = Progress("open beelden: requests (at most)", max_pages)

    def get(url: str) -> str:
        if budget[0] <= 0:
            raise _BudgetUsed
        budget[0] -= 1
        progress.done()
        return _page(url, records, fetch)

    try:
        with progress:
            while windows:
                window = windows.pop()
                try:
                    token = get(_list_url(*window))
                    if token and _days(window) > 31:
                        windows += _halves(*window)
                        continue
                    while token:
                        time.sleep(pause)
                        token = get(_resume(token))
                except _TooSlow:
                    if _days(window) > 0:
                        windows += _halves(*window)
                    else:
                        state.setdefault("skipped", []).append(window)
                except BaseException:
                    windows.append(window)  # not finished: start it again next run
                    raise
                time.sleep(pause)
            state["walked"] = today.isoformat()
    except _BudgetUsed:
        log.info("open beelden: request budget used; %d records so far, %d date windows left for the next run",
                 len(records), len(windows))
    except Exception as e:  # noqa: BLE001 - use what we have; the next run carries on
        log.warning("open beelden: harvest stopped (%s); using %d records", e, len(records))
    return state


def filling(state: dict) -> bool:
    """True while the first walk of the archive is unfinished (so it's worth carrying on every night)."""
    return not state.get("walked")


def build(cfg: dict, state: dict, fetch=net.get_bytes, pause: float = 1.0) -> tuple[list[Entry], list[Decision]]:
    harvest(state, fetch, pause, max_pages=cfg.get("max_pages", 30))
    decisions: list[Decision] = []
    picked: list[tuple[str, dict, str]] = []
    for ident, r in state["records"].items():
        kind = license_kind(r.get("license"))
        if kind not in ("pd", "cc-by", "cc-by-sa"):
            reason = f"license:{kind or 'none'}"
        elif not r.get("mp4"):
            reason = "no-mp4"
        elif (r.get("seconds") or 0) < cfg.get("min_minutes", 3) * 60:
            reason = "too-short"
        else:
            picked.append((ident, r, kind))
            continue
        decisions.append(Decision(SOURCE, ident, False, reason))
    picked.sort(key=lambda irk: -(irk[1]["seconds"] or 0))
    entries = []
    for ident, r, kind in picked[: cfg.get("max", 400)]:
        year = _year(r.get("date"))
        title = _movie_title(r["title"], year)
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
        decisions.append(Decision(SOURCE, ident, True, kind))
    decisions += [Decision(SOURCE, i, False, "cap") for i, _, _ in picked[cfg.get("max", 400):]]
    return entries, decisions
