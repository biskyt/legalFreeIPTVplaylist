"""The channel list for the TV guide (EPG).

The guide itself is downloaded by iptv-org's grabber (https://github.com/iptv-org/epg) in the build workflow.
This module tells it which channels to fetch: every live channel we publish that iptv-org knows a guide
source for (guides.json), with our tvg-id as the guide's channel id so the two match exactly.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .models import Entry


def channels_xml(entries: list[Entry], guides: list[dict]) -> tuple[str, int]:
    """(an iptv-org/epg channels.xml for the live entries that have a guide source, how many channels it lists)."""
    by_feed: dict[tuple[str, str | None], dict] = {}
    by_channel: dict[str, dict] = {}
    for g in guides:
        if g.get("channel") and g.get("site") and g.get("site_id"):
            by_feed.setdefault((g["channel"], g.get("feed")), g)
            by_channel.setdefault(g["channel"], g)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<channels>"]
    count = 0
    for e in entries:
        if e.kind != "live":
            continue
        channel, _, feed = e.id.partition("@")
        g = by_feed.get((channel, feed or None)) or by_channel.get(channel)
        if not g:
            continue
        lines.append(
            f"  <channel site={quoteattr(g['site'])} site_id={quoteattr(g['site_id'])} "
            f"lang={quoteattr(g.get('lang') or 'en')} xmltv_id={quoteattr(e.id)}>{escape(e.title)}</channel>"
        )
        count += 1
    lines.append("</channels>")
    return "\n".join(lines) + "\n", count
