"""The one record every source produces and every feed renders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["live", "movie", "series"]


@dataclass
class Entry:
    """One playable item: a live channel, a movie or a series episode."""

    id: str  # tvg-id; unique within its feed, prefixed by source (e.g. "ia.", "blender.")
    title: str  # display name after the #EXTINF comma
    url: str
    group: str  # group-title
    kind: Kind
    source: str  # key into config/credits.yaml
    logo: str | None = None
    duration: int | None = None  # seconds; None renders as -1 (live / unknown)
    year: int | None = None
    series_name: str | None = None
    season: int | None = None
    episode: int | None = None
    user_agent: str | None = None
    referrer: str | None = None
    catchup: str | None = None
    catchup_days: int | None = None
    catchup_source: str | None = None
    languages: list[str] = field(default_factory=list)  # ISO 639-3 codes; "zxx" = no dialogue
    countries: list[str] = field(default_factory=list)  # ISO 3166-1 alpha-2: where it's from / meant to be watched
    tmdb: str | None = None  # TMDB id: the movie's, or the series' (TV) id for an episode
    imdb: str | None = None  # IMDb id (tt...): the movie's, or the series' for an episode
    # Metadata for catalog.json and credits; not written to the M3U.
    license: str | None = None
    attribution: str | None = None
    page: str | None = None
    description: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Decision:
    """Why a candidate was kept or dropped; collected into report.json."""

    source: str
    item: str
    accepted: bool
    reason: str
