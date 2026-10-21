"""Public-domain and freely licensed films from Wikimedia Commons.

Commons only keeps files that are free in the United States *and* in their country of origin, a stricter test
than "public domain in the US", which makes these the safest films here for viewers outside the US. Files are
played from Commons' VP9 WebM transcodes (Theora .ogv originals don't play on most TVs).
"""

from __future__ import annotations

import re
import urllib.parse

from .. import languages, net
from ..models import Decision, Entry
from .internet_archive import _movie_title, _slug, _text

API = "https://commons.wikimedia.org/w/api.php"
SOURCE = "wikimedia-commons"
FREE_LICENCE = re.compile(r"public domain|^pd\b|cc0|^cc by(-sa)?( \d|$)", re.I)
_LANGUAGE_CAT = re.compile(r"^Category:(.+?)-language (?:films|videos)$")
_COUNTRY_CAT = re.compile(r"^Category:(?:\d{4} )?(?:films|videos)(?: of \d{4})? (?:of|from) (.+)$", re.I)
_SILENT_CAT = re.compile(r"^Category:Silent (?:films|videos)", re.I)
_DOC_CAT = re.compile(r"documentar", re.I)
_YEAR = re.compile(r"\b(18[89]\d|19\d\d|20[0-2]\d)\b")


def clean_title(name: str) -> str:
    """"1936. Цирк" / "Mukti, 1937" / "The Cat and the Canary (1927) by Paul Leni" -> the bare title."""
    t = re.sub(r"^(18|19|20)\d\d\.\s*", "", name)
    t = re.sub(r"\s*\((18|19|20)\d\d\)\s*(by .+)?$", "", t)
    t = re.sub(r",\s*(18|19|20)\d\d$", "", t)
    return t.strip(" -,.") or name


def fetch(query: str, limit: int) -> list[dict]:
    """File pages matching a CirrusSearch query, with video info and visible categories."""
    pages: list[dict] = []
    params = {
        "action": "query", "format": "json", "formatversion": "2", "generator": "search", "gsrnamespace": "6",
        "gsrlimit": "50", "gsrsearch": query, "prop": "videoinfo|categories", "cllimit": "max", "clshow": "!hidden",
        "viprop": "url|size|mediatype|derivatives|extmetadata", "viurlwidth": "500",  # thumburl: 500px, a standard size
        "viextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ObjectName|DateTimeOriginal|ImageDescription",
    }
    cont: dict = {}
    while len(pages) < limit:
        data = net.get_json(f"{API}?{urllib.parse.urlencode({**params, **cont})}")
        pages += data.get("query", {}).get("pages", [])
        cont = data.get("continue") or {}
        if not cont:
            break
    return pages[:limit]


def _meta(info: dict, key: str, limit: int = 600) -> str:
    return _text((info.get("extmetadata") or {}).get(key, {}).get("value"), limit) or ""


def best_video(info: dict, max_height: int = 720) -> str | None:
    """The largest VP9 WebM no taller than max_height (the original if it is one), or None."""
    options = [
        (d.get("height") or 0, d["src"]) for d in info.get("derivatives") or []
        if d.get("type", "").startswith("video/webm") and (d.get("height") or 0) <= max_height
    ]
    if not options:
        return None
    return max(options)[1].split("?")[0]


def _categories(page: dict) -> list[str]:
    return [c["title"] for c in page.get("categories") or []]


def page_languages(cats: list[str]) -> list[str]:
    if any(_SILENT_CAT.match(c) for c in cats):
        return [languages.NO_DIALOGUE]
    return languages.normalise_all([m.group(1) for c in cats if (m := _LANGUAGE_CAT.match(c))])


def page_countries(cats: list[str]) -> list[str]:
    out: list[str] = []
    for c in cats:
        m = _COUNTRY_CAT.match(c)
        code = languages.country(m.group(1)) if m else None
        if code and code not in out:
            out.append(code)
    return out


def build(cfg: dict, exclude_titles: str | None = None) -> tuple[list[Entry], list[Decision]]:
    excluded = re.compile(exclude_titles, re.I) if exclude_titles else None
    min_minutes, short_minutes = cfg.get("min_minutes", 5), cfg.get("short_minutes", 40)
    decisions: list[Decision] = []
    entries: list[Entry] = []
    seen: set[int] = set()
    for query in cfg["queries"]:
        for page in fetch(query, cfg.get("candidates", 3000)):
            if page.get("pageid") in seen:
                continue
            seen.add(page.get("pageid"))
            title = page["title"]
            info = (page.get("videoinfo") or [{}])[0]
            licence = _meta(info, "LicenseShortName")
            duration = info.get("duration") or 0
            if not FREE_LICENCE.search(licence):
                decisions.append(Decision(SOURCE, title, False, f"license:{licence or 'none'}"))
                continue
            if duration < min_minutes * 60:
                decisions.append(Decision(SOURCE, title, False, "too-short"))
                continue
            name = re.sub(r"^File:|\.(webm|ogv|ogg|mpg|mpeg|mp4)$", "", title, flags=re.I).replace("_", " ")
            if excluded and excluded.search(name):
                decisions.append(Decision(SOURCE, title, False, "excluded-title"))
                continue
            url = best_video(info, cfg.get("max_height", 720))
            if not url:
                decisions.append(Decision(SOURCE, title, False, "no-webm"))
                continue
            cats = _categories(page)
            year_match = _YEAR.search(_meta(info, "DateTimeOriginal")) or _YEAR.search(name)
            year = int(year_match.group(1)) if year_match else None
            if any(_DOC_CAT.search(c) for c in cats):
                group = cfg["groups"]["documentary"]
            elif duration < short_minutes * 60:
                group = cfg["groups"]["short"]
            else:
                group = cfg["groups"]["feature"]
            artist = _meta(info, "Artist")
            page_url = info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}"
            entries.append(Entry(
                id=f"commons.{_slug(name)}",
                title=_movie_title(clean_title(_meta(info, "ObjectName") or name), year),
                url=url,
                group=group,
                kind="movie",
                source=SOURCE,
                logo=info.get("thumburl"),
                duration=round(duration),
                year=year,
                languages=page_languages(cats),
                countries=page_countries(cats),
                license=licence,
                attribution=f"{name}{f' by {artist}' if artist else ''}, {licence}, via Wikimedia Commons",
                page=page_url,
                description=_meta(info, "ImageDescription") or None,
            ))
            decisions.append(Decision(SOURCE, title, True, "free-licence"))
    entries.sort(key=lambda e: -(e.duration or 0))
    return entries[: cfg.get("max", 800)], decisions
