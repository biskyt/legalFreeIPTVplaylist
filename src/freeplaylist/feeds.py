"""Per-kind feeds (live, movies, series), each rendered once, and combined and per-language feeds joined from
those renders."""

from __future__ import annotations

from dataclasses import dataclass

from . import languages, m3u
from .models import Decision, Entry


@dataclass
class Feed:
    name: str
    title: str
    entries: list[Entry]
    lines: list[str]  # the rendered #EXTINF/URL text of each entry, in order

    @property
    def body(self) -> str:
        return "".join(self.lines)

    def document(self, guide_urls=()) -> str:
        return m3u.document(m3u.header(guide_urls), self.body)


def _sort_key(e: Entry):
    if e.kind == "series":
        return (e.series_name or "").lower(), e.season or 0, e.episode or 0, e.title.lower()
    # By country; within a country, broadcasters' own channels before free streaming services (Pluto TV etc.);
    # then by group and name.
    return (e.countries or [""])[0], bool(e.extra.get("platform")), e.group.lower(), e.title.lower()


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
    return Feed(name, cfg.get("title", name), picked, [m3u.render_entry(e) for e in picked]), decisions


def combine(name: str, cfg: dict, feeds: dict[str, Feed]) -> Feed:
    """Join already-rendered member feeds; nothing is fetched, filtered or rendered again."""
    members = [feeds[m] for m in cfg["members"]]
    return Feed(name, cfg.get("title", name), [e for f in members for e in f.entries],
                [line for f in members for line in f.lines])


def by_language(feeds: dict[str, Feed], members: list[str], min_entries: int) -> dict[str, Feed]:
    """languages/<code>: the already-rendered lines of every entry in that language, from each member feed in
    turn. Films without dialogue (zxx) suit any audience, so they join every language's feed."""
    rows = [(e, line) for m in members for e, line in zip(feeds[m].entries, feeds[m].lines, strict=True)]
    by_code: dict[str, list[int]] = {}
    silent: list[int] = []
    for i, (e, _) in enumerate(rows):
        if e.kind != "live" and languages.NO_DIALOGUE in e.languages:
            silent.append(i)
        for code in e.languages:
            if code != languages.NO_DIALOGUE:
                by_code.setdefault(code, []).append(i)
    out = {}
    for code in sorted(c for c, idx in by_code.items() if len(idx) >= min_entries):
        picked = [rows[i] for i in sorted(set(by_code[code]) | set(silent))]  # in feed order
        out[f"languages/{code}"] = Feed(f"languages/{code}", languages.name(code), [e for e, _ in picked],
                                        [line for _, line in picked])
    return out
