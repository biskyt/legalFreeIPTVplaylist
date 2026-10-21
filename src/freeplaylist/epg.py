"""The TV guide (XMLTV) for the live channels, from fast sources nightly and slow ones in rotation.

* Fast: ready-made XMLTV files. iptv-epg.org publishes one per country (7 days, iptv-org channel ids) and
  i.mjh.nz one per service and region (Pluto TV, Samsung TV Plus, Plex...). Pluto TV and Samsung TV Plus
  channels are matched by the service's own channel id, which is in the stream URL, against i.mjh.nz's
  all-regions file, so they get a guide even where iptv-org doesn't link one. One download covers hundreds of
  channels, so these are fetched every night.
* Slow: channels none of those files has listings for, but which have a guide source in iptv-org's
  guides.json, are scraped channel by channel by iptv-org's grabber (https://github.com/iptv-org/epg). They're
  split into the same 7 nightly groups as the stream checks; each night the workflow grabs one group for 8 days
  ahead, so every channel always has listings. Each group's result is kept in state/epg/.

Three steps, so each can be watched (and can fail) on its own:
1. The build writes the plan: state/epg/plan.json (and a channels.xml of all tonight's slow channels).
2. `python -m freeplaylist epg fast` downloads the ready-made files and merges them, then writes the grabber's
   channels.xml with only tonight's slow channels that no file covered, so nothing is scraped that a file
   already provides.
3. After the grabber, `python -m freeplaylist epg merge` adds every saved grabber group and writes
   site/epg.xml.gz. Channel ids are renamed to our exact tvg-ids and finished programmes are dropped.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from . import languages, net, schedule
from .models import Entry
from .progress import Progress

log = logging.getLogger("freeplaylist")
IPTV_EPG = "https://iptv-epg.org/files/epg-{}.xml.gz"
MJH = "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/{}.xml"
# Services whose stream URLs carry the channel id i.mjh.nz uses: (pattern, i.mjh.nz file with every region).
SERVICE_IDS = (
    (re.compile(r"(?:jmp2\.uk/plu-|pluto\.tv/.*/channel/)([0-9a-f]{24})"), MJH.format("PlutoTV/all") + ".gz"),
    (re.compile(r"jmp2\.uk/stvp-([A-Z0-9]+)"), MJH.format("SamsungTVPlus/all") + ".gz"),
)
_REFRESH = re.compile(rb"""http-equiv=["']refresh["'][^>]*url=['"]?([^'">]+)""", re.I)


def _channel_country(channel_id: str) -> str:
    """iptv-epg.org file code for an iptv-org channel id: "3sat.de" -> "de", "BBCOne.uk" -> "gb"."""
    return languages.country_code(channel_id.rsplit(".", 1)[-1]).lower()


def plan(entries: list[Entry], guides: list[dict], tonight: schedule.Tonight) -> dict:
    """Which guide covers each live channel: {"iptv_epg": {cc: {their id: [our ids]}}, "mjh": {url: {...}},
    "slow": [[site, site_id, lang, our id, name], ...], "tonight": [...the slow ones in tonight's group]}.
    Every channel is offered to the ready-made files; "slow" is only where to scrape it if none has it."""
    live = [e for e in entries if e.kind == "live"]
    by_channel: dict[str, list[Entry]] = defaultdict(list)
    for e in live:
        by_channel[e.id.partition("@")[0]].append(e)
    guide_for: dict[tuple[str, str | None], dict] = {}
    for g in guides:
        if g.get("channel") and g.get("site") and g.get("site_id"):
            guide_for.setdefault((g["channel"], g.get("feed")), g)
            guide_for.setdefault((g["channel"], None), g)

    out = {"iptv_epg": defaultdict(dict), "mjh": defaultdict(dict), "slow": []}
    for channel, es in by_channel.items():
        # iptv-epg.org lists a channel once; give its listings to the channel's main feed (or its only one).
        main = [e for e in es if e.extra.get("main_feed")] or es[:1]
        out["iptv_epg"][_channel_country(channel)].setdefault(channel, []).extend(e.id for e in main)
        for e in es:
            service = next(((url, m.group(1)) for pattern, url in SERVICE_IDS if (m := pattern.search(e.url))), None)
            if service:
                out["mjh"][service[0]].setdefault(service[1], []).append(e.id)
                continue
            g = guide_for.get((channel, e.id.partition("@")[2] or None)) or guide_for.get((channel, None))
            if not g:
                continue
            if g["site"] == "i.mjh.nz":
                path, _, their_id = g["site_id"].partition("#")
                out["mjh"][MJH.format(path)].setdefault(their_id, []).append(e.id)
            else:
                out["slow"].append([g["site"], g["site_id"], g.get("lang") or "en", e.id, e.title])
    out["tonight"] = [s for s in out["slow"] if tonight.is_turn(s[3])]
    out["night"] = tonight.night
    return {k: dict(v) if isinstance(v, defaultdict) else v for k, v in out.items()}


def channels_xml(channels: list[list[str]]) -> str:
    """An iptv-org/epg channels.xml; xmltv_id is our tvg-id, so the grabber's output already matches."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<channels>"]
    for site, site_id, lang, our_id, name in channels:
        lines.append(f"  <channel site={quoteattr(site)} site_id={quoteattr(site_id)} lang={quoteattr(lang)} "
                     f"xmltv_id={quoteattr(our_id)}>{escape(name)}</channel>")
    lines.append("</channels>")
    return "\n".join(lines) + "\n"


def write_plan(state_dir: Path, the_plan: dict) -> None:
    folder = state_dir / "epg"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.json").write_text(json.dumps(the_plan), encoding="utf-8")
    # All of tonight's group for now, in case the next step fails; `fast` narrows it to the uncovered ones.
    (folder / "channels.xml").write_text(channels_xml(the_plan["tonight"]), encoding="utf-8")
    log.info("epg: %d channels with a guide site to scrape if no ready-made file has them (%d tonight)",
             len(the_plan["slow"]), len(the_plan["tonight"]))


# --- merging ---------------------------------------------------------------------------------------------------

def _download(url: str) -> bytes:
    """A guide file; follows iptv-epg.org's HTML meta-refresh redirect to the real file."""
    body = net.get_bytes(url, timeout=180)
    if body[:2] != b"\x1f\x8b" and (m := _REFRESH.search(body[:4096])):
        body = net.get_bytes(m.group(1).decode(), timeout=180)
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def _stop_time(value: str) -> float:
    try:
        return datetime.strptime(value[:20].strip(), "%Y%m%d%H%M%S %z").timestamp()
    except ValueError:
        return float("inf")  # unreadable: keep it


class Merger:
    """Collects channels and programmes from several XMLTV files under our ids. The first source to supply
    current programmes for a channel owns it, so a channel never gets two overlapping guides. A source's
    programmes are kept only if its whole file parses; they go to a temporary file, so memory holds only the
    channel list, however big the guides are."""

    def __init__(self, now: float | None = None):
        self.now = now or time.time()
        self.channels: dict[str, bytes] = {}
        self.owner: dict[str, str] = {}
        self._programmes = tempfile.TemporaryFile()  # noqa: SIM115 - spans add() calls; closed by write()

    def add(self, source: str, data: bytes, ids: dict[str, list[str]]) -> int:
        """Add one XMLTV document; `ids` maps its channel ids to ours. Returns how many channels it now owns."""
        channels: dict[str, bytes] = {}
        claimed: set[str] = set()
        with tempfile.TemporaryFile() as buf:
            for _, el in ET.iterparse(io.BytesIO(data), events=("end",)):
                if el.tag == "channel":
                    for ours in self._free(el.get("id", ""), ids):
                        el.set("id", ours)
                        channels.setdefault(ours, ET.tostring(el, encoding="utf-8"))
                    el.clear()
                elif el.tag == "programme":
                    if _stop_time(el.get("stop", "")) > self.now:
                        for ours in self._free(el.get("channel", ""), ids):
                            el.set("channel", ours)
                            buf.write(ET.tostring(el, encoding="utf-8"))
                            claimed.add(ours)
                    el.clear()
            buf.seek(0)
            shutil.copyfileobj(buf, self._programmes)
        for ours in claimed:
            self.owner[ours] = source
            self.channels[ours] = channels.get(ours) or (
                f'<channel id={quoteattr(ours)}><display-name>{escape(ours)}</display-name></channel>'.encode())
        return len(claimed)

    def _free(self, theirs: str, ids: dict[str, list[str]]) -> list[str]:
        return [ours for ours in ids.get(theirs, []) if ours not in self.owner]

    def write(self, path: Path) -> int:
        with gzip.open(path, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="freeplaylist">\n')
            for element in self.channels.values():
                f.write(element)
            self._programmes.seek(0)
            shutil.copyfileobj(self._programmes, f)
            f.write(b"</tv>\n")
        self._programmes.close()
        return len(self.channels)


def _covered_file(fast_file: Path) -> Path:
    return fast_file.with_name(fast_file.name + ".channels.json")


def fast_sources(the_plan: dict) -> list[tuple[str, str, dict]]:
    """(credit, url, id map) for each ready-made file, in order of preference."""
    out = [("iptv-epg.org", IPTV_EPG.format(cc), ids) for cc, ids in sorted(the_plan["iptv_epg"].items())]
    return out + [("i.mjh.nz", url, ids) for url, ids in sorted(the_plan["mjh"].items())]


def fast(state_dir: Path, out: Path) -> int:
    """Download and merge the ready-made files into `out` (and the ids of the channels covered next to it), then write
    state/epg/channels.xml: tonight's slow channels that none of them covered. Returns channels covered."""
    folder = state_dir / "epg"
    the_plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    merger = Merger()
    sources = fast_sources(the_plan)
    failed = []
    with Progress("epg: ready-made files", len(sources)) as progress:
        for source, url, ids in sources:
            try:
                merger.add(source, _download(url), ids)
            except Exception as e:  # noqa: BLE001 - not every country has a file; any one file may fail for a night
                failed.append(f"{'/'.join(url.rsplit('/', 2)[-2:])} ({e})")
            progress.done()
    if failed:  # mostly countries iptv-epg.org has no file for
        log.info("epg: %d files unavailable: %s", len(failed), "; ".join(failed)[:2000])
    covered = sorted(merger.owner)
    out.parent.mkdir(parents=True, exist_ok=True)
    merger.write(out)
    _covered_file(out).write_text(json.dumps(covered), encoding="utf-8")
    grab = [s for s in the_plan["tonight"] if s[3] not in merger.owner]
    (folder / "channels.xml").write_text(channels_xml(grab), encoding="utf-8")
    log.info("epg: ready-made files cover %d channels (%s); %d of tonight's %d slow channels left to grab",
             len(covered), ", ".join(f"{s} {n}" for s, n in Counter(merger.owner.values()).most_common()),
             len(grab), len(the_plan["tonight"]))
    return len(covered)


def merge(state_dir: Path, out: Path, fast_file: Path, grabbed: Path | None = None) -> int:
    """Build the published guide: the merged ready-made files (made by `fast` now if that step didn't finish),
    then every saved grabber group. Returns channels covered.

    `grabbed` is tonight's grabber output, saved as tonight's group before merging.
    """
    folder = state_dir / "epg"
    the_plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    if grabbed and grabbed.exists():
        night = the_plan.get("night", 0)
        (folder / f"group-{night}.xml.gz").write_bytes(grabbed.read_bytes())
    if not fast_file.exists() or not _covered_file(fast_file).exists():
        fast(state_dir, fast_file)
    covered = json.loads(_covered_file(fast_file).read_text(encoding="utf-8"))
    # Grabber output already uses our ids; keeping only channels still in the plan drops ones no longer published.
    slow_ids = {s[3]: [s[3]] for s in the_plan["slow"]}
    sources = [("ready-made", lambda: gzip.decompress(fast_file.read_bytes()), {c: [c] for c in covered},
                fast_file.name)]
    sources += [("iptv-org/epg", lambda f=f: gzip.decompress(f.read_bytes()), slow_ids, f.name)
                for f in sorted(folder.glob("group-*.xml.gz"))]
    merger = Merger()
    for source, load, ids, label in sources:
        try:
            log.info("epg: %s: %d channels", label, merger.add(source, load(), ids))
        except Exception as e:  # noqa: BLE001 - one bad group file shouldn't lose the rest
            log.info("epg: %s: %s", label, e)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = merger.write(out)
    log.info("epg: guide written for %d channels", count)
    return count
