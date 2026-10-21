"""Public-domain and openly licensed movies and TV episodes from the Internet Archive.

Uploaders set an item's licence and year themselves, so neither is trusted alone:
  * an explicit public-domain mark is only accepted for works dated up to `pd_max_year` (later "public domain"
    claims are usually mistaken), CC BY / CC BY-SA are accepted at any date, NC and ND licences never;
  * an item with no licence is accepted only when its date is before `pre_year` (US public domain by age);
  * series are taken only from shows listed in config/series.yaml, and their episodes still need a PD/CC licence;
  * config/denylist.yaml removes individual items (takedowns, mislabelled uploads).
"""

from __future__ import annotations

import html
import re
import time
import urllib.parse
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .. import languages, net
from ..models import Decision, Entry
from ..progress import Progress

SCRAPE = "https://archive.org/services/search/v1/scrape"
METADATA = "https://archive.org/metadata/{}"
SOURCE = "internet-archive"
VIDEO_FORMATS = {"h.264", "h.264 IA", "MPEG4", "512Kb MPEG4"}
_FORMAT_RANK = {"h.264": 3, "h.264 IA": 3, "MPEG4": 2, "512Kb MPEG4": 1}
LIST_FIELDS = "identifier,title,year,date,licenseurl,downloads"

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_TRAILING_YEAR = re.compile(r"\s*[\(\[](\d{4})[\)\]]\s*$")
_EPISODE_PATTERNS = [
    re.compile(r"\bS(?:eason)?\s*(\d{1,2})\s*[,.\-_ ]*\s*E(?:p(?:isode)?)?\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(\d{1,2})x(\d{1,3})\b"),
]
_EPISODE_ONLY = re.compile(r"\bEp(?:isode)?\.?\s*#?\s*(\d{1,3})\b", re.I)
_LEADING_NUMBER = re.compile(r"\(?(\d{1,3})\)?(?=[\s\-:])")
# Upload noise in episode titles: bracketed notes with digits, quality tags, years and bare season codes.
_JUNK = re.compile(
    r"\((?=[^)]*\d)[^)]*\)|\b(?:512kb|h264|public domain|pd|tv|colou?ri[sz]ed|subtitled|w/ ?commercials|"
    r"\d+ ?mbps|web)\b|\b(?:19|20)\d\d\b|\bS\d{1,2}\b",
    re.I,
)
_ARTICLE_LAST = re.compile(r"^(.+?),\s*(The|A|An)$", re.I)


# --- search and metadata ---------------------------------------------------------------------------------------

def search(query: str, limit: int, fields: str = LIST_FIELDS, sort: str = "downloads desc") -> list[dict]:
    """Items matching an advanced-search query, most downloaded first (the scrape API pages with a cursor)."""
    items: list[dict] = []
    cursor = None
    while len(items) < limit:
        params = {"q": query, "fields": fields, "sorts": sort, "count": max(100, min(10000, limit - len(items)))}
        if cursor:
            params["cursor"] = cursor
        page = net.get_json(f"{SCRAPE}?{urllib.parse.urlencode(params)}")
        items += page.get("items", [])
        cursor = page.get("cursor")
        if not cursor:
            break
    return items[:limit]


def _seconds(length) -> float | None:
    """File length as IA writes it: '4533.5', '75:33' or '1:15:00'."""
    if length in (None, ""):
        return None
    try:
        parts = [float(p) for p in str(length).split(":")]
    except ValueError:
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def videos(files: list[dict]) -> list[dict]:
    """One playable MP4 per source video in an item, best quality first within each source."""
    best: dict[str, dict] = {}
    for f in files:
        name = f.get("name", "")
        if f.get("format") not in VIDEO_FORMATS or not name.lower().endswith(".mp4"):
            continue
        key = f.get("original") or name
        rank = (_FORMAT_RANK.get(f["format"], 0), int(f.get("height") or 0))
        if key not in best or rank > best[key]["rank"]:
            best[key] = {"name": name, "length": _seconds(f.get("length")), "title": f.get("title"), "rank": rank}
    out = sorted(best.values(), key=lambda v: v["name"])
    for v in out:
        del v["rank"]
    return out


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _year(*values) -> int | None:
    this_year = date.today().year
    for v in values:
        m = re.match(r"\s*(\d{4})", str(_first(v) or ""))
        if m and 1880 <= int(m.group(1)) <= this_year:
            return int(m.group(1))
    return None


def _text(value, limit: int = 600) -> str | None:
    if not value:
        return None
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    text = _SPACE.sub(" ", html.unescape(_TAGS.sub(" ", str(value)))).strip()
    return text[: limit - 1].rstrip() + "…" if len(text) > limit else text or None


def summarise(raw: dict) -> dict | None:
    """The few fields we keep from an item's metadata (and cache between runs)."""
    meta = raw.get("metadata")
    if not meta or raw.get("is_dark"):
        return None
    return {
        "title": _text(meta.get("title"), 200),
        "description": _text(meta.get("description")),
        "year": _year(meta.get("year"), meta.get("date")),
        "licenseurl": _first(meta.get("licenseurl")),
        "creator": _text(meta.get("director") or meta.get("creator"), 200),
        "language": meta.get("language"),
        "videos": videos(raw.get("files") or []),
    }


class MetadataCache:
    """Item summaries keyed by identifier, refreshed after `max_age_days` (staggered so not all expire at once)."""

    def __init__(self, data: dict, max_age_days: int = 30, workers: int = 6):
        self.data = data
        self.max_age = max_age_days * 86400
        self.workers = workers
        self.fetched = 0

    def _fresh(self, ident: str, now: float) -> bool:
        rec = self.data.get(ident)
        if not rec:
            return False
        jitter = (zlib.crc32(ident.encode()) % 7) * 86400  # spread refreshes over a week
        return now - rec.get("t", 0) < self.max_age + jitter

    def get_many(self, identifiers: list[str]) -> dict[str, dict | None]:
        now = time.time()
        missing = [i for i in dict.fromkeys(identifiers) if not self._fresh(i, now)]

        def fetch(ident: str):
            try:
                return ident, summarise(net.get_json(METADATA.format(urllib.parse.quote(ident)), timeout=45))
            except Exception as e:  # noqa: BLE001 - one bad item must not stop the build
                return ident, {"error": str(e)[:200]}

        with Progress("internet archive: item details", len(missing)) as progress, \
                ThreadPoolExecutor(self.workers) as pool:
            for ident, summary in pool.map(fetch, missing):
                progress.done()
                if summary is not None and "error" in summary:
                    continue  # keep any older copy; try again next run
                self.data[ident] = {"t": now, "s": summary}
                self.fetched += 1
        return {i: (self.data.get(i) or {}).get("s") for i in identifiers}


# --- licence rules ---------------------------------------------------------------------------------------------

def license_kind(url: str | None) -> str | None:
    """'pd', 'cc-by', 'cc-by-sa', 'restricted' (NC/ND/other) or None when no licence is given."""
    if not url:
        return None
    u = url.lower()
    if "publicdomain" in u:
        return "pd"
    if "creativecommons.org/licenses/" in u:
        if "-nc" in u or "-nd" in u:
            return "restricted"
        if "/by-sa/" in u:
            return "cc-by-sa"
        if "/by/" in u:
            return "cc-by"
    return "restricted"


def license_ok(licenseurl: str | None, year: int | None, *, pd_max_year: int, pre_year: int) -> tuple[bool, str]:
    kind = license_kind(licenseurl)
    if kind in ("cc-by", "cc-by-sa"):
        return True, kind
    if kind == "pd":
        if year is None:
            return False, "pd-claim-without-year"
        if year > pd_max_year:
            return False, "pd-claim-too-recent"
        return True, "pd"
    if kind == "restricted":
        return False, "restricted-license"
    if year is not None and year < pre_year:
        return True, f"pre-{pre_year}"
    return False, "no-license"


def license_label(licenseurl: str | None, basis: str) -> str:
    if basis.startswith("pre-"):
        return f"Public domain in the US (published before {basis[4:]})"
    if basis == "pd":
        return "Public domain in the US (as marked on the Internet Archive)"
    return licenseurl or basis


# --- entries ---------------------------------------------------------------------------------------------------

def cc_attribution(summary: dict, basis: str) -> str | None:
    """The credit line CC BY / BY-SA ask for: work, author, licence, source."""
    if not basis.startswith("cc-by"):
        return None
    author = f" by {summary['creator']}" if summary.get("creator") else ""
    return f"{summary.get('title') or 'Untitled'}{author}, {summary.get('licenseurl')}, via the Internet Archive"


def download_url(identifier: str, name: str) -> str:
    return f"https://archive.org/download/{urllib.parse.quote(identifier)}/{urllib.parse.quote(name)}"


def _movie_title(title: str, year: int | None) -> str:
    title = _TRAILING_YEAR.sub("", title).strip()
    title = _ARTICLE_LAST.sub(r"\2 \1", title)  # "Monster Walks, The" -> "The Monster Walks"
    return f"{title} ({year})" if year else title


def movie_entry(identifier: str, summary: dict, video: dict, *, group: str, source: str = SOURCE,
                license: str | None = None, attribution: str | None = None, title: str | None = None,
                year: int | None = None, id_prefix: str = "ia", langs: list[str] | None = None) -> Entry:
    year = year or summary.get("year")
    return Entry(
        id=f"{id_prefix}.{identifier}",
        title=title or _movie_title(summary.get("title") or identifier, year),
        url=download_url(identifier, video["name"]),
        group=group,
        kind="movie",
        source=source,
        logo=f"https://archive.org/services/img/{urllib.parse.quote(identifier)}",
        duration=round(video["length"]) if video.get("length") else None,
        year=year,
        license=license,
        attribution=attribution,
        page=f"https://archive.org/details/{urllib.parse.quote(identifier)}",
        description=summary.get("description"),
        languages=langs or [],
        extra={"creator": summary.get("creator")} if summary.get("creator") else {},
    )


def item_languages(summary: dict, default: str | list | None) -> list[str]:
    """The item's own language metadata when it has any, otherwise the configured default."""
    return languages.normalise_all(summary.get("language")) or languages.normalise_all(default)


def movies(cfg: dict, cache: MetadataCache, denylist: set[str]) -> tuple[list[Entry], list[Decision]]:
    rules = cfg.get("rules", {})
    pd_max, pre = rules.get("pd_max_year", 1977), rules.get("pre_year", 1931)
    min_minutes, short_minutes = rules.get("min_minutes", 5), rules.get("short_minutes", 40)
    excluded = re.compile(rules["exclude_titles"], re.I) if rules.get("exclude_titles") else None
    decisions: list[Decision] = []
    seen: set[str] = set()
    picked: list[tuple[dict, dict]] = []  # (collection config, listing item)

    for col in cfg["collections"]:
        listing = search(f"collection:({col['collection']}) AND mediatype:(movies)", col.get("candidates", 600))
        kept = 0
        for item in listing:
            ident = item["identifier"]
            if ident in seen:
                continue
            seen.add(ident)
            if ident in denylist:
                decisions.append(Decision(SOURCE, ident, False, "denylist"))
                continue
            if excluded and excluded.search(f"{ident} {item.get('title') or ''}"):
                decisions.append(Decision(SOURCE, ident, False, "excluded-title"))
                continue
            ok, why = license_ok(item.get("licenseurl"), _year(item.get("year"), item.get("date")),
                                 pd_max_year=pd_max, pre_year=pre)
            if not ok:
                decisions.append(Decision(SOURCE, ident, False, why))
                continue
            picked.append((col, item))
            kept += 1
            if kept >= col.get("max", 200) * 1.3:  # some fail the metadata checks below
                break

    summaries = cache.get_many([item["identifier"] for _, item in picked])
    entries: list[Entry] = []
    per_collection: dict[str, int] = {}
    for col, item in picked:
        ident = item["identifier"]
        summary = summaries.get(ident)
        if not summary:
            decisions.append(Decision(SOURCE, ident, False, "metadata-unavailable"))
            continue
        # The item page is authoritative; re-check the licence against it.
        ok, why = license_ok(summary.get("licenseurl"), summary.get("year"), pd_max_year=pd_max, pre_year=pre)
        if not ok:
            decisions.append(Decision(SOURCE, ident, False, f"metadata:{why}"))
            continue
        vids = [v for v in summary["videos"] if (v.get("length") or 0) >= min_minutes * 60]
        long_parts = [v for v in vids if v["length"] >= 20 * 60]
        if not vids:
            decisions.append(Decision(SOURCE, ident, False, "no-playable-video"))
            continue
        if len(long_parts) > 1:
            decisions.append(Decision(SOURCE, ident, False, "multi-part"))
            continue
        if per_collection.get(col["collection"], 0) >= col.get("max", 200):
            decisions.append(Decision(SOURCE, ident, False, "collection-cap"))
            continue
        video = max(vids, key=lambda v: v["length"])
        group = col["group"]
        if video["length"] < short_minutes * 60 and col.get("shorts_group", True):
            group = cfg.get("shorts_group", "Movies: Shorts")
        entries.append(movie_entry(ident, summary, video, group=group,
                                   license=license_label(summary.get("licenseurl"), why),
                                   attribution=cc_attribution(summary, why),
                                   langs=item_languages(summary, col.get("language"))))
        per_collection[col["collection"]] = per_collection.get(col["collection"], 0) + 1
        decisions.append(Decision(SOURCE, ident, True, why))
    return entries, decisions


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"\.mp4$", "", name, flags=re.I)).strip("_")


def parse_episode(text: str) -> tuple[int | None, int | None]:
    for pattern in _EPISODE_PATTERNS:
        m = pattern.search(text)
        if m:
            return int(m.group(1)), int(m.group(2))
    m = _EPISODE_ONLY.search(text)
    return (None, int(m.group(1))) if m else (None, None)


def episode_info(text: str, show: dict) -> tuple[int | None, int | None, str]:
    """(season, episode, title) from an upload's title or file name, e.g.
    'Beverly_Hillbillies_Ep01_The_Clampetts_Strike_Oil' -> (None, 1, 'The Clampetts Strike Oil') and
    'Sherlock Holmes 02 The Case Of Lady Beryl.mp4' -> (None, 2, 'The Case Of Lady Beryl')."""
    t = re.sub(r"(\.ia)?\.mp4$", "", text, flags=re.I).replace("_", " ")
    if " " not in t:
        t = t.replace(".", " ")  # dotted file names: s01e01.The.Speckled.Band
    t = re.sub(show["match"], " ", t, flags=re.I)
    season, number = parse_episode(t)
    for pattern in [*_EPISODE_PATTERNS, _EPISODE_ONLY]:
        t = pattern.sub(" ", t)
    t = t.strip(" -:|,.#'\"")
    if number is None:
        m = _LEADING_NUMBER.match(t)
        if m:
            number, t = int(m.group(1)), t[m.end():]
    t = _JUNK.sub(" ", t)
    t = _SPACE.sub(" ", t.replace("''", "'")).strip(" -:;|,.#'\"")
    t = re.sub(r"^in\s+|\s+Ep$", "", t, flags=re.I)
    return season, number, t


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^(the )?case of (the )?", "", title.lower()))


def series(cfg: dict, cache: MetadataCache, denylist: set[str]) -> tuple[list[Entry], list[Decision]]:
    decisions: list[Decision] = []
    entries: list[Entry] = []
    for show in cfg.get("shows") or []:
        listing = search(show["query"], show.get("candidates", 300))
        idents = [i["identifier"] for i in listing if i["identifier"] not in denylist]
        summaries = cache.get_many(idents)
        matcher = re.compile(show["match"], re.I)
        episodes: list[Entry] = []
        titles: set[str] = set()
        numbers: set[tuple[int, int]] = set()
        for ident in idents:
            summary = summaries.get(ident)
            if not summary:
                decisions.append(Decision(SOURCE, ident, False, "metadata-unavailable"))
                continue
            if not matcher.search(f"{ident} {summary.get('title') or ''}"):
                decisions.append(Decision(SOURCE, ident, False, f"not-{show['name']}"))
                continue
            if show.get("max_year") and (summary.get("year") or 0) > show["max_year"]:
                decisions.append(Decision(SOURCE, ident, False, "series:too-recent"))
                continue
            kind = license_kind(summary.get("licenseurl"))
            if kind not in ("pd", "cc-by", "cc-by-sa"):
                decisions.append(Decision(SOURCE, ident, False, f"series:{kind or 'no-license'}"))
                continue
            # Episode-length videos only; this also keeps feature films about the same characters out.
            lo, hi = show.get("min_minutes", 10) * 60, show.get("max_minutes", 70) * 60
            vids = [v for v in summary["videos"] if lo <= (v.get("length") or 0) <= hi]
            if not vids:
                decisions.append(Decision(SOURCE, ident, False, "no-playable-video"))
                continue
            # A single-video item is one episode named by the item; a multi-video item holds several episodes.
            for v in vids:
                if len(vids) > 1:
                    season, number, name = episode_info(v.get("title") or v["name"], show)
                else:
                    season, number, name = episode_info(summary.get("title") or ident, show)
                    if number is None:
                        season, number, _ = episode_info(f"{ident} {v['name']}", show)
                name = name or (f"Episode {number}" if number is not None else "")
                if not name:
                    decisions.append(Decision(SOURCE, f"{ident}/{v['name']}", False, "untitled-episode"))
                    continue
                # The same episode is often uploaded several times, numbered differently or not at all.
                title_key = _title_key(name) if not name.startswith("Episode ") else None
                if title_key and title_key in titles:
                    continue
                if number is not None and ((season or 1), number) in numbers:
                    if not title_key:
                        continue
                    season = number = None
                if title_key:
                    titles.add(title_key)
                if number is not None:
                    numbers.add(((season or 1), number))
                code = f" S{season or 1:02d}E{number:02d}" if number is not None else ""
                episodes.append(Entry(
                    id=f"ia.{ident}" + (f".{_slug(v['name'])}" if len(vids) > 1 else ""),
                    title=f"{show['name']}{code} - {name}",
                    url=download_url(ident, v["name"]),
                    group=f"Series: {show['name']}",
                    kind="series",
                    source=SOURCE,
                    logo=f"https://archive.org/services/img/{urllib.parse.quote(ident)}",
                    duration=round(v["length"]),
                    year=summary.get("year"),
                    series_name=show["name"],
                    season=(season or 1) if number is not None else None,
                    episode=number,
                    license=license_label(summary.get("licenseurl"), kind),
                    attribution=cc_attribution(summary, kind),
                    page=f"https://archive.org/details/{urllib.parse.quote(ident)}",
                    description=summary.get("description"),
                    languages=item_languages(summary, show.get("language")),
                    tmdb=str(show["tmdb"]) if show.get("tmdb") else None,
                    imdb=show.get("imdb"),
                    extra={"basis": show.get("basis")},
                ))
            decisions.append(Decision(SOURCE, ident, True, f"series:{show['name']}"))
        entries += episodes[: show.get("max", 300)]
    return entries, decisions
