"""The TV guide (XMLTV) for the live channels, from fast sources nightly and slow ones in rotation.

* Fast: ready-made XMLTV files. iptv-epg.org publishes one per country (7 days, iptv-org channel ids) and
  i.mjh.nz one per service and region (Pluto TV, Samsung TV Plus, Plex...). One download covers hundreds of
  channels, so these are fetched every night.
* Slow: the remaining channels with a guide source in iptv-org's guides.json, which iptv-org's grabber
  (https://github.com/iptv-org/epg) scrapes channel by channel. They're split into the same 7 nightly groups
  as the stream checks; each night the workflow grabs one group for 8 days ahead, so every channel always has
  listings. Each group's result is kept in state/epg/.

The build writes the plan (state/epg/plan.json and tonight's channels.xml); after the grabber has run,
`python -m freeplaylist epg` downloads the fast files and merges everything into site/epg.xml.gz, with each
channel's id renamed to our exact tvg-id and finished programmes dropped.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from . import net, schedule
from .models import Entry

log = logging.getLogger("freeplaylist")
IPTV_EPG = "https://iptv-epg.org/files/epg-{}.xml.gz"
MJH = "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/{}.xml"
_REFRESH = re.compile(rb"""http-equiv=["']refresh["'][^>]*url=['"]?([^'">]+)""", re.I)


def _channel_country(channel_id: str) -> str:
    """iptv-epg.org file code for an iptv-org channel id: "3sat.de" -> "de", "BBCOne.uk" -> "gb"."""
    cc = channel_id.rsplit(".", 1)[-1].lower()
    return "gb" if cc == "uk" else cc


def plan(entries: list[Entry], guides: list[dict], groups: int, night: int) -> dict:
    """Which guide covers each live channel: {"iptv_epg": {cc: {their id: [our ids]}}, "mjh": {url: {...}},
    "slow": [[site, site_id, lang, our id, name], ...], "tonight": [...the slow ones in tonight's group]}."""
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
            g = guide_for.get((channel, e.id.partition("@")[2] or None)) or guide_for.get((channel, None))
            if not g:
                continue
            if g["site"] == "i.mjh.nz":
                path, _, their_id = g["site_id"].partition("#")
                out["mjh"][MJH.format(path)].setdefault(their_id, []).append(e.id)
            else:
                out["slow"].append([g["site"], g["site_id"], g.get("lang") or "en", e.id, e.title])
    out["tonight"] = [s for s in out["slow"] if schedule.group(s[3], groups) == night]
    out["night"] = night
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
    (folder / "channels.xml").write_text(channels_xml(the_plan["tonight"]), encoding="utf-8")
    log.info("epg: %d channels in ready-made guides, %d to grab (%d tonight)",
             sum(len(v) for m in (the_plan["iptv_epg"], the_plan["mjh"]) for v in m.values()),
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
    """Collects channels and programmes from several XMLTV files under our ids; the first source to cover a
    channel wins, so a channel never gets two overlapping guides."""

    def __init__(self, now: float | None = None):
        self.now = now or time.time()
        self.channels: dict[str, bytes] = {}
        self.programmes: dict[str, list[bytes]] = defaultdict(list)
        self.owner: dict[str, str] = {}

    def add(self, source: str, data: bytes, ids: dict[str, list[str]] | None) -> int:
        """Add one XMLTV document; `ids` maps its channel ids to ours (None: they're already ours)."""
        added: set[str] = set()
        for _, el in ET.iterparse(io.BytesIO(data), events=("end",)):
            if el.tag == "channel":
                for ours in self._ours(source, el.get("id", ""), ids):
                    el.set("id", ours)
                    self.channels.setdefault(ours, ET.tostring(el, encoding="utf-8"))
                el.clear()
            elif el.tag == "programme":
                ours_list = self._ours(source, el.get("channel", ""), ids)
                if ours_list and _stop_time(el.get("stop", "")) > self.now:
                    for ours in ours_list:
                        el.set("channel", ours)
                        self.programmes[ours].append(ET.tostring(el, encoding="utf-8"))
                        added.add(ours)
                el.clear()
        return len(added)

    def _ours(self, source: str, theirs: str, ids: dict[str, list[str]] | None) -> list[str]:
        out = []
        for ours in ([theirs] if ids is None else ids.get(theirs, [])):
            if self.owner.setdefault(ours, source) == source:
                out.append(ours)
        return out

    def write(self, path: Path) -> int:
        covered = [c for c in self.channels if self.programmes.get(c)]
        with gzip.open(path, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="freeplaylist">\n')
            for c in covered:
                f.write(self.channels[c])
            for c in covered:
                for p in self.programmes[c]:
                    f.write(p)
            f.write(b"</tv>\n")
        return len(covered)


def merge(state_dir: Path, out: Path, grabbed: Path | None = None) -> int:
    """Build the published guide: fast files first, then every saved grabber group. Returns channels covered.

    `grabbed` is tonight's grabber output, saved as tonight's group before merging.
    """
    folder = state_dir / "epg"
    the_plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    if grabbed and grabbed.exists():
        night = the_plan.get("night", 0)
        (folder / f"group-{night}.xml.gz").write_bytes(grabbed.read_bytes())
    merger = Merger()
    for cc, ids in sorted(the_plan["iptv_epg"].items()):
        try:
            n = merger.add("iptv-epg.org", _download(IPTV_EPG.format(cc)), ids)
            log.info("epg: iptv-epg.org %s: %d channels", cc, n)
        except Exception as e:  # noqa: BLE001 - not every country has a file; others may fail for a night
            log.info("epg: iptv-epg.org %s: %s", cc, e)
    for url, ids in sorted(the_plan["mjh"].items()):
        try:
            n = merger.add("i.mjh.nz", _download(url), ids)
            log.info("epg: %s: %d channels", url, n)
        except Exception as e:  # noqa: BLE001
            log.warning("epg: %s: %s", url, e)
    # Grabber output already uses our ids; keeping only channels still in the plan drops ones no longer published.
    slow_ids = {s[3]: [s[3]] for s in the_plan["slow"]}
    for group_file in sorted(folder.glob("group-*.xml.gz")):
        try:
            n = merger.add("iptv-org/epg", gzip.decompress(group_file.read_bytes()), slow_ids)
            log.info("epg: %s: %d channels", group_file.name, n)
        except Exception as e:  # noqa: BLE001
            log.warning("epg: %s: %s", group_file.name, e)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = merger.write(out)
    log.info("epg: guide written for %d channels", count)
    return count
