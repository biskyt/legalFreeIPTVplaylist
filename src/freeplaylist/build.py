"""The whole build: sources -> filters -> health check -> feeds -> combined feeds -> site/."""

from __future__ import annotations

import html
import json
import logging
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import config, credits, feeds, healthcheck, m3u
from .models import Decision, Entry
from .sources import curated, internet_archive, iptv_org

log = logging.getLogger("freeplaylist")
PAGES = "https://biskyt.github.io/licenseFreeIPTVplaylist"
REPO = "https://github.com/biskyt/licenseFreeIPTVplaylist"


class BuildError(Exception):
    pass


@dataclass
class Options:
    out: Path
    state_dir: Path
    config_dir: Path = config.CONFIG_DIR
    api_dir: Path | None = None  # local copy of the iptv-org API (tests / offline)
    health: bool = True
    live: bool = True
    vod: bool = True
    vod_sample: float = 0.05
    enforce_minimums: bool = True


@dataclass
class Result:
    feeds: dict[str, feeds.Feed]
    decisions: list[Decision] = field(default_factory=list)


def collect(opts: Options) -> tuple[list[Entry], list[Decision], dict]:
    """All candidate entries from every source, before health checks."""
    load = lambda name: config.load(name, opts.config_dir)  # noqa: E731
    ia_state_path = opts.state_dir / "ia_cache.json"
    cache = internet_archive.MetadataCache(config.load_state(ia_state_path))
    entries: list[Entry] = []
    decisions: list[Decision] = []

    def add(found: tuple[list[Entry], list[Decision]], label: str) -> None:
        entries.extend(found[0])
        decisions.extend(found[1])
        log.info("%s: %d entries", label, len(found[0]))

    if opts.vod:
        # Order matters: when two sources offer the same file, the earlier one wins (see _dedupe), so curated
        # items keep their attribution and an episode isn't also listed as a movie.
        add(curated.build(load("curated"), cache), "curated")
        deny = set(load("denylist").get("identifiers") or [])
        add(internet_archive.series(load("series"), cache, deny), "internet archive series")
        add(internet_archive.movies(load("movies"), cache, deny), "internet archive movies")
        config.save_state(ia_state_path, cache.data)
        log.info("internet archive: fetched metadata for %d items", cache.fetched)
    elif opts.live:
        # Curated live items still belong in a live-only build.
        found = curated.build({"direct": load("curated").get("direct")}, cache)
        add(([e for e in found[0] if e.kind == "live"], found[1]), "curated live")
    if opts.live:
        rules = iptv_org.Rules.from_config(load("live_hosts"), load("live_allowlist"))
        add(iptv_org.build(iptv_org.fetch_api(opts.api_dir), rules), "iptv-org")
    entries, dropped = _dedupe(entries)
    return entries, decisions + dropped, load("credits").get("sources") or {}


def _dedupe(entries: list[Entry]) -> tuple[list[Entry], list[Decision]]:
    """Drop entries whose URL an earlier source already provides."""
    seen: set[str] = set()
    kept, dropped = [], []
    for e in entries:
        if e.url in seen:
            dropped.append(Decision("dedupe", e.id, False, "same-file-as-earlier-source"))
            continue
        seen.add(e.url)
        kept.append(e)
    return kept, dropped


def check_health(entries: list[Entry], opts: Options) -> tuple[list[Entry], list[Decision]]:
    path = opts.state_dir / "health.json"
    state = config.load_state(path)
    checker = healthcheck.Checker()
    live = [e for e in entries if e.kind == "live"]
    vod = [e for e in entries if e.kind != "live"]
    live, d1 = healthcheck.run(live, state, checker)
    vod, d2 = healthcheck.run(vod, state, healthcheck.Checker(per_host=4, timeout=20), sample=opts.vod_sample,
                              rng=random.Random(), keep_on_error=True)
    urls = {c["url"] for e in entries for c in (e.extra.get("candidates") or [{"url": e.url}])}
    config.save_state(path, healthcheck.prune(state, urls))
    log.info("health: kept %d live, %d vod", len(live), len(vod))
    return live + vod, d1 + d2


def make_feeds(entries: list[Entry], feed_cfg: dict) -> tuple[dict[str, feeds.Feed], list[Decision]]:
    out: dict[str, feeds.Feed] = {}
    decisions: list[Decision] = []
    for name, cfg in feed_cfg["feeds"].items():
        out[name], d = feeds.build(name, cfg, entries)
        decisions += d
    for name, cfg in (feed_cfg.get("combined") or {}).items():
        out[name] = feeds.combine(name, cfg, out)
    return out, decisions


def validate(built: dict[str, feeds.Feed], feed_cfg: dict, enforce_minimums: bool = True) -> list[str]:
    problems = []
    for name, feed in built.items():
        _, parsed = m3u.parse(feed.document())
        if len(parsed) != len(feed.entries):
            problems.append(f"{name}: wrote {len(feed.entries)} entries but parsed {len(parsed)}")
        dupes = [k for k, n in Counter(p.get("tvg-id") for p in parsed).items() if n > 1]
        if dupes:
            problems.append(f"{name}: duplicate tvg-id {dupes[:5]}")
        minimum = feed_cfg["feeds"].get(name, {}).get("min_entries", 0)
        if enforce_minimums and len(feed.entries) < minimum:
            problems.append(f"{name}: only {len(feed.entries)} entries (minimum {minimum})")
    return problems


def report(decisions: list[Decision], built: dict[str, feeds.Feed]) -> dict:
    counts: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for d in decisions:
        key = f"{'accepted' if d.accepted else 'rejected'}:{d.reason}"
        counts[d.source][key] += 1
        if len(samples[d.source][key]) < 50:
            samples[d.source][key].append(d.item)
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "feeds": {n: len(f.entries) for n, f in built.items()},
        "groups": {n: dict(Counter(e.group for e in f.entries).most_common()) for n, f in built.items()
                   if n in ("live", "movies", "series")},
        "decisions": {s: dict(c.most_common()) for s, c in counts.items()},
        "samples": samples,
    }


def catalog(built: dict[str, feeds.Feed]) -> dict:
    keys = ("id", "kind", "title", "group", "url", "year", "duration", "series_name", "season", "episode", "logo",
            "license", "attribution", "page", "description", "source")
    items = []
    for name in ("live", "movies", "series"):
        for e in built[name].entries:
            item = {k: getattr(e, k) for k in keys if getattr(e, k) not in (None, "")}
            items.append(item)
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "format": f"{REPO}/blob/main/FORMAT.md",
        "feeds": {n: f"{PAGES}/{n}.m3u" for n in built},
        "items": items,
    }


def index_html(built: dict[str, feeds.Feed]) -> str:
    rows = "".join(
        f'<tr><td><a href="{n}.m3u">{n}.m3u</a></td><td>{html.escape(f.title)}</td><td>{len(f.entries)}</td></tr>'
        for n, f in built.items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Free IPTV playlist</title>
<style>body{{font-family:system-ui,sans-serif;max-width:50rem;margin:auto;padding:1rem;line-height:1.5}}
table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #ccc;padding:.3rem .8rem;text-align:left}}</style>
</head><body>
<h1>Free IPTV playlist</h1>
<p>Legally free live TV, FAST channels, public-domain and openly licensed movies and series, as M3U playlists.
Rebuilt daily. This site only links to streams; it hosts no video.</p>
<table><thead><tr><th>Playlist</th><th>Contents</th><th>Entries</th></tr></thead><tbody>{rows}</tbody></table>
<p>Add <code>{PAGES}/playlist.m3u</code> (everything) to your IPTV app, or the separate feeds if your app
takes one playlist per type. Movies and series use an open <a href="{REPO}/blob/main/FORMAT.md">M3U
convention</a>; apps that don't know it show them as groups.</p>
<p><a href="credits.html">Credits</a> · <a href="catalog.json">catalog.json</a> ·
<a href="report.json">build report</a> · <a href="{REPO}">source code and issues</a></p>
</body></html>
"""


def write_site(out: Path, built: dict[str, feeds.Feed], decisions: list[Decision], sources: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, feed in built.items():
        (out / f"{name}.m3u").write_text(feed.document(), encoding="utf-8", newline="\n")
    (out / "catalog.json").write_text(json.dumps(catalog(built), ensure_ascii=False), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report(decisions, built), indent=1, ensure_ascii=False),
                                     encoding="utf-8")
    everything = [e for n in ("live", "movies", "series") for e in built[n].entries]
    (out / "credits.html").write_text(credits.broadcasters_html(everything, sources), encoding="utf-8")
    (out / "index.html").write_text(index_html(built), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def run(opts: Options) -> Result:
    entries, decisions, sources = collect(opts)
    absent = credits.missing(entries, sources)
    if absent:
        raise BuildError(f"no credit record in credits.yaml for: {', '.join(sorted(absent))}")
    if opts.health:
        entries, d = check_health(entries, opts)
        decisions += d
    feed_cfg = config.load("feeds", opts.config_dir)
    built, d = make_feeds(entries, feed_cfg)
    decisions += d
    problems = validate(built, feed_cfg, opts.enforce_minimums)
    if problems:
        raise BuildError("; ".join(problems))
    write_site(opts.out, built, decisions, sources)
    return Result(built, decisions)
