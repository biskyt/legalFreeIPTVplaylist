"""Per-kind feeds (live, movies, series), each rendered once, and combined feeds joined from those renders."""

from __future__ import annotations

from dataclasses import dataclass

from . import m3u
from .models import Decision, Entry


@dataclass
class Feed:
    name: str
    title: str
    entries: list[Entry]
    body: str  # the rendered #EXTINF/URL lines, without a header

    def document(self, guide_urls=()) -> str:
        return m3u.document(m3u.header(guide_urls), self.body)


def _sort_key(e: Entry):
    if e.kind == "series":
        return (e.series_name or "").lower(), e.season or 0, e.episode or 0, e.title.lower()
    # Broadcasters' own channels before FAST services; then by group and name.
    return e.group.startswith("FAST:"), e.group.lower(), e.title.lower()


def build(name: str, cfg: dict, entries: list[Entry]) -> tuple[Feed, list[Decision]]:
    """The feed for one kind: its entries de-duplicated (by id and by URL), ordered, and rendered."""
    decisions = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    picked = []
    for e in sorted((e for e in entries if e.kind == cfg["kind"]), key=_sort_key):
        if e.id in seen_ids or e.url in seen_urls:
            decisions.append(Decision(f"feed:{name}", e.id, False, "duplicate"))
            continue
        seen_ids.add(e.id)
        seen_urls.add(e.url)
        picked.append(e)
    return Feed(name, cfg.get("title", name), picked, m3u.render_body(picked)), decisions


def combine(name: str, cfg: dict, feeds: dict[str, Feed]) -> Feed:
    """Join already-rendered member feeds; nothing is fetched, filtered or rendered again."""
    members = [feeds[m] for m in cfg["members"]]
    return Feed(name, cfg.get("title", name), [e for f in members for e in f.entries],
                "".join(f.body for f in members))
