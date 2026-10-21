"""The whole build: sources -> filters -> health check -> feeds -> combined feeds -> site/."""

from __future__ import annotations

import html
import json
import logging
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from . import config, credits, enrich, epg, feeds, healthcheck, languages, m3u, net, schedule, snapshots
from .models import Decision, Entry
from .sources import curated, internet_archive, iptv_org, open_beelden, website_check, wikimedia_commons

log = logging.getLogger("freeplaylist")
PAGES = "https://biskyt.github.io/legalFreeIPTVplaylist"
REPO = "https://github.com/biskyt/legalFreeIPTVplaylist"


# The source names used by --only, config/schedule.yaml and the snapshots.
SOURCES = ("curated", "internet-archive-series", "wikimedia-commons", "internet-archive-movies", "open-beelden",
           "iptv-org")
# A build can run in parts (one per workflow step, so progress shows step by step), sharing state/: "harvest"
# one source into its snapshot; "check-live" / "check-vod" check tonight's streams from the snapshots; "publish"
# builds the site from the snapshots and the last checks. Without a phase, a build does all of it at once.
PHASES = ("harvest", "check-live", "check-vod", "publish")


class BuildError(Exception):
    pass


@dataclass
class Options:
    out: Path
    state_dir: Path
    config_dir: Path = config.CONFIG_DIR
    api_dir: Path | None = None  # local copy of the iptv-org API (tests / offline)
    health: bool = True
    website_check: bool = True  # fetch broadcasters' websites to confirm streams (see sources/website_check.py)
    extra_vod: bool = True  # Wikimedia Commons and Open Beelden
    enrich: bool = True  # TMDB/IMDb ids and posters from Wikidata
    live: bool = True
    vod: bool = True
    all: bool = False  # harvest and check everything, ignoring the schedule
    only: set[str] | None = None  # staged run: harvest just these sources (see SOURCES); others from snapshots
    day: date | None = None  # the night being built (UTC); defaults to today
    enforce_minimums: bool = True
    phase: str | None = None  # one part of the build (see PHASES); None for all of it
    source: str | None = None  # the source a "harvest" phase harvests


@dataclass
class Result:
    feeds: dict[str, feeds.Feed]
    decisions: list[Decision] = field(default_factory=list)


@dataclass
class Collected:
    entries: list[Entry]
    decisions: list[Decision]
    sources: dict  # credit records
    harvested: set[str]  # sources harvested tonight
    missing: set[str]  # sources with no results yet (a staged first harvest)


def collect(opts: Options, tonight: schedule.Tonight) -> Collected:
    """All candidate entries from every source, before health checks.

    A source that isn't due tonight (config/schedule.yaml) is taken from its snapshot; see snapshots.py.
    """
    load = lambda name: config.load(name, opts.config_dir)  # noqa: E731
    day = tonight.day
    ia_state_path = opts.state_dir / "ia_cache.json"
    cache = internet_archive.MetadataCache(config.load_state(ia_state_path))
    entries: list[Entry] = []
    decisions: list[Decision] = []
    harvested: set[str] = set()
    missing: set[str] = set()

    def section(key: str, harvest, filling: bool = False) -> None:
        """One source's entries: harvested if due (or forced, or never harvested, or `filling`: a first harvest
        spread over several nights), otherwise its snapshot.
        A failed harvest falls back to the snapshot, so one broken source doesn't stop the build."""
        if opts.phase == "harvest" and key != opts.source:
            return
        snap = snapshots.load(opts.state_dir, key)
        found = None
        if (opts.only is not None and key not in opts.only) or opts.phase not in (None, "harvest"):
            # A staged run (--only): other sources come from their snapshots, or wait for their own stage.
            # Checking and publishing phases use the snapshots their harvest phases left.
            if snap is None:
                missing.add(key)
                log.info("%s: no snapshot yet; left out until it's harvested", key)
                return
            if snap[2] == day.isoformat():
                harvested.add(key)
        elif opts.all or opts.only is not None or snap is None or filling or tonight.due(key):
            log.info("%s: harvesting", key)
            try:
                found = harvest()
            except Exception as e:  # noqa: BLE001 - fall back to the last good results
                if snap is None:
                    raise
                log.warning("%s: harvest failed (%s); using the snapshot from %s", key, e, snap[2])
            else:
                snapshots.save(opts.state_dir, key, found[0], found[1], day.isoformat())
                harvested.add(key)
                log.info("%s: harvested %d entries", key, len(found[0]))
        if found is None:
            found = snap[0], snap[1]
            log.info("%s: %d entries from the snapshot of %s", key, len(found[0]), snap[2])
        for e in found[0]:
            e.extra["section"] = key
        entries.extend(found[0])
        decisions.extend(found[1])

    # iptv-org also supplies the language and country names every source uses.
    names = iptv_org.fetch_api(opts.api_dir, ("languages", "countries"))
    languages.load(names["languages"])
    languages.load_countries(names["countries"])

    if opts.vod:
        # Order matters: when two sources offer the same film, the earlier one wins (see _dedupe), so curated
        # items keep their attribution, an episode isn't also listed as a movie, and Commons (free in the
        # film's own country too) wins over the Internet Archive.
        deny = set(load("denylist").get("identifiers") or [])
        movies_cfg = load("movies")
        section("curated", lambda: curated.build(load("curated"), cache))
        section("internet-archive-series", lambda: internet_archive.series(load("series"), cache, deny))
        if opts.extra_vod:
            exclude = (movies_cfg.get("rules") or {}).get("exclude_titles")
            section("wikimedia-commons", lambda: wikimedia_commons.build(load("commons"), exclude))
        section("internet-archive-movies", lambda: internet_archive.movies(movies_cfg, cache, deny))
        config.save_state(ia_state_path, cache.data)
        if opts.extra_vod:
            ob_path = opts.state_dir / "open_beelden.json"
            ob_state = config.load_state(ob_path)
            try:
                section("open-beelden", lambda: open_beelden.build(load("open_beelden"), ob_state),
                        filling=open_beelden.filling(ob_state))
            finally:
                config.save_state(ob_path, ob_state)
    elif opts.live:
        # Curated live items still belong in a live-only build.
        found = curated.build({"direct": load("curated").get("direct")}, cache)
        entries.extend(e for e in found[0] if e.kind == "live")
    if opts.live:
        section("iptv-org", lambda: _live(opts, load, tonight))
    if opts.phase == "harvest":
        return Collected(entries, decisions, {}, harvested, missing)
    entries, dropped = _dedupe(entries)
    if opts.vod and opts.enrich and opts.phase in (None, "publish"):
        wd_path = opts.state_dir / "wikidata.json"
        wd_state = config.load_state(wd_path)
        matched = enrich.apply(entries, enrich.load(wd_state))
        config.save_state(wd_path, wd_state)
        log.info("wikidata: ids for %d movies", matched)
    return Collected(entries, decisions + dropped, load("credits").get("sources") or {}, harvested, missing)


def _live(opts: Options, load, tonight: schedule.Tonight) -> tuple[list[Entry], list[Decision]]:
    # Language and country names were already fetched (and loaded) by collect().
    api = iptv_org.fetch_api(opts.api_dir, tuple(f for f in iptv_org.FILES if f not in ("languages", "countries")))
    hosts_cfg = load("live_hosts")
    rules = iptv_org.Rules.from_config(hosts_cfg, load("live_allowlist"))
    site_links = None
    check = hosts_cfg.get("website_check") or {}
    if opts.website_check and check.get("enabled", True):
        path = opts.state_dir / "website_links.json"
        state = config.load_state(path)
        sites = iptv_org.unverified_sites(api, rules)
        site_links = website_check.find_hosts(sites, state, tonight, everything=opts.all,
                                              max_sites=check.get("max_sites", 2500))
        config.save_state(path, {s: v for s, v in state.items() if s in sites})
        log.info("website check: %d sites with unverified streams", len(sites))
    return iptv_org.build(api, rules, site_links)


def _title_key(e: Entry) -> tuple | None:
    if e.kind != "movie" or not e.year:
        return None
    title = re.sub(r"\s*\(\d{4}\)$", "", e.title).lower()
    # Letters and digits in any script, so "Цирк" keeps its own key instead of collapsing to "".
    key = re.sub(r"^(the|a|an) ", "", " ".join(re.sub(r"[^\w ]|_", " ", title).split()))
    return (key, e.year) if key else None


def _dedupe(entries: list[Entry]) -> tuple[list[Entry], list[Decision]]:
    """Drop entries whose file, or (for movies) whose title and year, an earlier source already provides."""
    seen_urls: set[str] = set()
    seen_titles: set[tuple] = set()
    kept, dropped = [], []
    for e in entries:
        key = _title_key(e)
        if e.url in seen_urls:
            dropped.append(Decision("dedupe", e.id, False, "same-file-as-earlier-source"))
            continue
        if key and key in seen_titles:
            dropped.append(Decision("dedupe", e.id, False, "same-film-as-earlier-source"))
            continue
        seen_urls.add(e.url)
        if key:
            seen_titles.add(key)
        kept.append(e)
    return kept, dropped


def check_health(entries: list[Entry], opts: Options, tonight: schedule.Tonight,
                 harvested: set[str]) -> tuple[list[Entry], list[Decision]]:
    """Checks tonight's share of streams (see config/schedule.yaml); the rest keep their last result."""
    recheck = tonight.cfg.get("vod_recheck", 0.25)
    rng = random.Random()
    path = opts.state_dir / "health.json"
    state = config.load_state(path)

    def live_due(e: Entry) -> bool:
        return opts.all or tonight.is_turn(net.host_of(healthcheck.candidates(e)[0]["url"]))

    def vod_due(e: Entry) -> bool:
        return opts.all or (e.extra.get("section") in harvested and rng.random() < recheck)

    live = [e for e in entries if e.kind == "live"]
    vod = [e for e in entries if e.kind != "live"]
    # In a phased build each kind is checked in its own phase; the others use the last checks.
    live, d1 = healthcheck.run(live, state, healthcheck.Checker(), due=live_due,
                               check=opts.phase in (None, "check-live"))
    vod, d2 = healthcheck.run(vod, state, healthcheck.Checker(timeout=20, files=True), due=vod_due, keep_on_error=True,
                              check=opts.phase in (None, "check-vod"))
    urls = {c["url"] for e in entries for c in healthcheck.candidates(e)}
    config.save_state(path, healthcheck.prune(state, urls))
    log.info("health: kept %d live, %d vod (live host group %d of %d checked tonight)", len(live), len(vod),
             tonight.night + 1, tonight.groups)
    return live + vod, d1 + d2


def make_feeds(entries: list[Entry], feed_cfg: dict) -> tuple[dict[str, feeds.Feed], list[Decision]]:
    out: dict[str, feeds.Feed] = {}
    decisions: list[Decision] = []
    for name, cfg in feed_cfg["feeds"].items():
        out[name], d = feeds.build(name, cfg, entries)
        decisions += d
    for name, cfg in (feed_cfg.get("combined") or {}).items():
        out[name] = feeds.combine(name, cfg, out)
    lang_cfg = feed_cfg.get("languages") or {}
    if lang_cfg:
        out.update(feeds.by_language(out, lang_cfg.get("members", ["live", "movies", "series"]),
                                     lang_cfg.get("min_entries", 10)))
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
            "languages", "countries", "tmdb", "imdb", "license", "attribution", "page", "description", "source")
    items = []
    for name in ("live", "movies", "series"):
        for e in built[name].entries:
            item = {k: getattr(e, k) for k in keys if getattr(e, k) not in (None, "", [])}
            items.append(item)
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "format": f"{REPO}/blob/main/FORMAT.md",
        "feeds": {n: f"{PAGES}/{n}.m3u" for n in built},
        "items": items,
    }


def index_html(built: dict[str, feeds.Feed], sources: dict | None = None) -> str:
    def rows(names):
        return "".join(
            f'<tr><td><a href="{n}.m3u">{n}.m3u</a></td><td>{html.escape(built[n].title)}</td>'
            f"<td>{len(built[n].entries)}</td></tr>"
            for n in names
        )

    main = [n for n in built if not n.startswith("languages/")]
    by_lang = sorted((n for n in built if n.startswith("languages/")), key=lambda n: built[n].title)
    lang_rows = rows(by_lang)
    guide_sources = "".join(
        f'<li><a href="{html.escape(s["url"])}">{html.escape(s["name"])}</a>: '
        f'{html.escape(" ".join(s["provides"].split()))}. <small>{html.escape(s["license"])}.</small></li>'
        for s in (sources or {}).values() if s.get("guide"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legal free IPTV playlist</title>
<style>body{{font-family:system-ui,sans-serif;max-width:50rem;margin:auto;padding:1rem;line-height:1.5}}
table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #ccc;padding:.3rem .8rem;text-align:left}}</style>
</head><body>
<h1>Legal free IPTV playlist</h1>
<p>Legally free live TV (including free streaming services such as Pluto TV), public-domain and openly
licensed movies and series, as M3U playlists.
Rebuilt daily. This site only links to streams; it hosts no video.</p>
<table><thead><tr><th>Playlist</th><th>Contents</th><th>Entries</th></tr></thead><tbody>{rows(main)}</tbody></table>
<p>Add <code>{PAGES}/playlist.m3u</code> (everything) to your IPTV app, or the separate feeds if your app
takes one playlist per type. Movies and series use an open
<a href="{REPO}/blob/main/FORMAT.md">M3U convention</a>; apps that don't know it show them as groups.</p>
<h2>TV guide</h2>
<p><a href="epg.xml.gz">epg.xml.gz</a>: programme listings (XMLTV, gzipped) for the live channels, about a week
ahead, rebuilt every night. It's named in the header of every playlist with live channels
(<code>url-tvg</code>), so most apps load it automatically; otherwise add <code>{PAGES}/epg.xml.gz</code> as
the EPG source. Its channel ids are the playlists' <code>tvg-id</code>s. Not every channel has listings.</p>
<p>Listings come from these sources, merged in this order (a channel takes its listings from the first that
has them; the listings belong to the broadcasters and services):</p>
<ul>{guide_sources}</ul>
<h2>By language</h2>
<p>Everything in one language: live channels, then movies and series. Every entry is also tagged with
<code>tvg-language</code> and <code>tvg-country</code>, so players can filter the main playlists too. Silent films
appear in every language's playlist.</p>
<table><thead><tr><th>Playlist</th><th>Language</th><th>Entries</th></tr></thead><tbody>{lang_rows}</tbody></table>
<p><a href="credits.html">Credits</a> · <a href="catalog.json">catalog.json</a> ·
<a href="report.json">build report</a> · <a href="{REPO}">source code and issues</a></p>
</body></html>
"""


def write_site(out: Path, built: dict[str, feeds.Feed], decisions: list[Decision], sources: dict,
               guide: str | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, feed in built.items():
        path = out / f"{name}.m3u"
        path.parent.mkdir(parents=True, exist_ok=True)
        has_live = any(e.kind == "live" for e in feed.entries)
        path.write_text(feed.document([guide] if guide and has_live else []), encoding="utf-8", newline="\n")
    (out / "catalog.json").write_text(json.dumps(catalog(built), ensure_ascii=False), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report(decisions, built), indent=1, ensure_ascii=False),
                                     encoding="utf-8")
    everything = [e for n in ("live", "movies", "series") for e in built[n].entries]
    (out / "credits.html").write_text(credits.broadcasters_html(everything, sources), encoding="utf-8")
    (out / "index.html").write_text(index_html(built, sources), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def run(opts: Options) -> Result:
    tonight = schedule.Tonight(config.load("schedule", opts.config_dir), opts.day or datetime.now(UTC).date())
    got = collect(opts, tonight)
    entries, decisions, sources = got.entries, got.decisions, got.sources
    if opts.phase == "harvest":
        return Result({}, decisions)
    absent = credits.missing(entries, sources)
    if absent:
        raise BuildError(f"no credit record in credits.yaml for: {', '.join(sorted(absent))}")
    if opts.health:
        entries, d = check_health(entries, opts, tonight, got.harvested)
        decisions += d
    if opts.phase in ("check-live", "check-vod"):
        return Result({}, decisions)
    feed_cfg = config.load("feeds", opts.config_dir)
    built, d = make_feeds(entries, feed_cfg)
    decisions += d
    # During a staged first harvest some feeds only fill up in later stages, so their minimums can't apply yet.
    problems = validate(built, feed_cfg, opts.enforce_minimums and not got.missing)
    if problems:
        raise BuildError("; ".join(problems))
    guide = feed_cfg.get("guide")
    if guide and opts.live:
        # The guide is built after this, by the workflow: iptv-org's grabber for tonight's group of slow channels,
        # then `freeplaylist epg`, which adds the ready-made guides and merges everything (see epg.py).
        guides = iptv_org.fetch_api(opts.api_dir, ("guides",))["guides"]
        epg.write_plan(opts.state_dir, epg.plan(built["live"].entries, guides, tonight))
    write_site(opts.out, built, decisions, sources, f"{PAGES}/{guide}" if guide else None)
    return Result(built, decisions)
