"""TMDB and IMDb ids and free posters for movies, from Wikidata.

Wikidata (CC0) links many films to the Internet Archive item (P724) or Wikimedia Commons video (P10) they're
published as, and to their TMDB (P4947) and IMDb (P345) ids and film poster (P3383, a free image on Commons).
Matching on those links, not on titles, means a film only gets ids when Wikidata says they're the same film.
Results are cached in state/wikidata.json for a week; if Wikidata is unavailable the cached copy is used.
"""

from __future__ import annotations

import logging
import time
import urllib.parse

from . import net
from .models import Entry

SPARQL = "https://query.wikidata.org/sparql"
log = logging.getLogger("freeplaylist")

QUERIES = {
    # Internet Archive identifier -> ids and poster
    "ia": """SELECT ?key ?tmdb ?imdb ?poster WHERE { ?f wdt:P724 ?key .
        OPTIONAL { ?f wdt:P4947 ?tmdb } OPTIONAL { ?f wdt:P345 ?imdb } OPTIONAL { ?f wdt:P3383 ?poster }
        FILTER(BOUND(?tmdb) || BOUND(?imdb) || BOUND(?poster)) }""",
    # Commons video file -> ids and poster
    "commons": """SELECT ?key ?tmdb ?imdb ?poster WHERE { ?f wdt:P10 ?key .
        OPTIONAL { ?f wdt:P4947 ?tmdb } OPTIONAL { ?f wdt:P345 ?imdb } OPTIONAL { ?f wdt:P3383 ?poster }
        FILTER(BOUND(?tmdb) || BOUND(?imdb) || BOUND(?poster)) }""",
}


def _query(sparql: str) -> list[dict]:
    """Rows of {variable: value} from the Wikidata Query Service."""
    url = f"{SPARQL}?{urllib.parse.urlencode({'query': sparql, 'format': 'json'})}"
    data = net.get_json(url, timeout=180)
    return [{k: v["value"] for k, v in b.items()} for b in data["results"]["bindings"]]


def _commons_name(url: str) -> str:
    """'http://commons.wikimedia.org/wiki/Special:FilePath/The%20Kid%20%281921%29.webm' -> 'The_Kid_(1921).webm'."""
    return urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace(" ", "_")


def load(state: dict, ttl_days: int = 7) -> dict[str, dict[str, dict]]:
    """{"ia": {identifier: ids}, "commons": {file name: ids}}, from cache when fresh or when Wikidata fails."""
    now = time.time()
    for name, sparql in QUERIES.items():
        cached = state.get(name)
        if cached and now - cached.get("t", 0) < ttl_days * 86400:
            continue
        try:
            rows = _query(sparql)
        except Exception as e:  # noqa: BLE001 - keep the cached copy; enrichment is optional
            log.warning("wikidata %s query failed: %s", name, e)
            continue
        table: dict[str, dict] = {}
        for r in rows:
            key = _commons_name(r["key"]) if name == "commons" else r["key"]
            rec = table.setdefault(key, {})
            for field in ("tmdb", "imdb", "poster"):
                if r.get(field) and field not in rec:
                    rec[field] = r[field]
        state[name] = {"t": now, "rows": table}
    return {name: (state.get(name) or {}).get("rows", {}) for name in QUERIES}


def poster_url(commons_file_url: str, width: int = 400) -> str:
    """A thumbnail of a Commons image, via Special:FilePath."""
    return f"{commons_file_url.replace('http://', 'https://', 1)}?width={width}"


def apply(entries: list[Entry], tables: dict[str, dict[str, dict]]) -> int:
    """Add ids and posters to movies whose source item Wikidata knows; returns how many matched."""
    matched = 0
    for e in entries:
        if e.kind != "movie" or not e.page:
            continue
        if "archive.org/details/" in e.page:
            rec = tables["ia"].get(urllib.parse.unquote(e.page.rsplit("/", 1)[-1]))
        elif "commons.wikimedia.org" in e.page:
            rec = tables["commons"].get(urllib.parse.unquote(e.page.rsplit("File:", 1)[-1]).replace(" ", "_"))
        else:
            rec = None
        if not rec:
            continue
        matched += 1
        e.tmdb = e.tmdb or rec.get("tmdb")
        e.imdb = e.imdb or rec.get("imdb")
        if rec.get("poster"):
            e.logo = poster_url(rec["poster"])  # a real poster beats a video frame
    return matched
