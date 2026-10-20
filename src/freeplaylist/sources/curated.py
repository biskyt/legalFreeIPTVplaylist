"""Hand-picked items from config/curated.yaml (Blender open movies, and any direct streams)."""

from __future__ import annotations

from ..models import Decision, Entry
from . import internet_archive as ia

SOURCE = "curated"


def build(cfg: dict, cache: ia.MetadataCache) -> tuple[list[Entry], list[Decision]]:
    entries: list[Entry] = []
    decisions: list[Decision] = []

    defaults = cfg.get("ia_defaults") or {}
    items = cfg.get("ia_movies") or []
    summaries = cache.get_many([i["ia"] for i in items])
    for item in items:
        opts = {**defaults, **item}
        summary = summaries.get(item["ia"])
        vids = (summary or {}).get("videos") or []
        if not vids:
            decisions.append(Decision(SOURCE, item["ia"], False, "no-playable-video"))
            continue
        video = max(vids, key=lambda v: v.get("length") or 0)
        entries.append(ia.movie_entry(
            item["ia"], summary, video,
            group=opts["group"], source=opts["source"], license=opts.get("license"),
            attribution=opts.get("attribution"), title=opts.get("title"), year=opts.get("year"),
            id_prefix=opts.get("id_prefix", "ia"),
        ))
        decisions.append(Decision(SOURCE, item["ia"], True, "curated"))

    for item in cfg.get("direct") or []:
        entries.append(Entry(
            id=item["id"], title=item["title"], url=item["url"], group=item["group"], kind=item["kind"],
            source=item["source"], logo=item.get("logo"), duration=item.get("duration"), year=item.get("year"),
            series_name=item.get("series_name"), season=item.get("season"), episode=item.get("episode"),
            license=item.get("license"), attribution=item.get("attribution"), page=item.get("page"),
            description=item.get("description"),
        ))
        decisions.append(Decision(SOURCE, item["id"], True, "curated"))
    return entries, decisions
