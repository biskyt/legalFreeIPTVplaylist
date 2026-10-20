"""Extended M3U writer (and a small reader for validation).

Everything written here follows the compatibility rules in FORMAT.md: one #EXTINF line plus one URL line per
entry, double-quoted attribute values without quotes, commas or newlines, and a display name without newlines or
commas, so that naive first-comma / last-comma parsers read the same name as careful ones.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Entry

HEADER = "#EXTM3U"
_SPACE = re.compile(r"\s+")


def clean_attr(value: str) -> str:
    """An attribute value that can't break out of its quotes or split a naive parser."""
    return _SPACE.sub(" ", value.replace('"', "'").replace(",", " ")).strip()


def clean_name(value: str) -> str:
    """A display name on one line, without commas (some parsers take the text after the last comma)."""
    return _SPACE.sub(" ", value.replace(",", " –")).strip()


def header(guide_urls: Iterable[str] = ()) -> str:
    urls = [u for u in guide_urls if u]
    return f'{HEADER} url-tvg="{",".join(urls)}"' if urls else HEADER


def _attrs(e: Entry) -> list[tuple[str, str | int | None]]:
    attrs: list[tuple[str, str | int | None]] = []
    if e.kind != "live":
        attrs.append(("tvg-type", e.kind))
    if e.kind == "series":
        attrs += [("series-name", e.series_name), ("season", e.season), ("episode", e.episode)]
    attrs += [
        ("tvg-id", e.id),
        ("tvg-name", e.title),
        ("tvg-logo", e.logo),
        ("year", e.year),
        ("catchup", e.catchup),
        ("catchup-days", e.catchup_days),
        ("catchup-source", e.catchup_source),
        ("http-user-agent", e.user_agent),
        ("http-referrer", e.referrer),
        ("group-title", e.group),
    ]
    return attrs


def _quoted(key: str, value: str | int) -> str:
    # catchup-source is a URL template, so it is percent-encoded rather than having characters dropped.
    if key == "catchup-source":
        text = str(value).strip().replace('"', "%22").replace(",", "%2C")
    else:
        text = clean_attr(str(value))
    return f'{key}="{text}"'


def render_entry(e: Entry) -> str:
    duration = round(e.duration) if e.duration and e.duration >= 1 else -1  # whole seconds; -1 = live/unknown
    attrs = " ".join(_quoted(k, v) for k, v in _attrs(e) if v is not None and v != "")
    lines = [f"#EXTINF:{duration} {attrs},{clean_name(e.title)}"]
    # VLC and many Android players read these instead of (or as well as) the attributes.
    if e.user_agent:
        lines.append(f"#EXTVLCOPT:http-user-agent={e.user_agent}")
    if e.referrer:
        lines.append(f"#EXTVLCOPT:http-referrer={e.referrer}")
    lines.append(e.url.strip())
    return "\n".join(lines) + "\n"


def render_body(entries: Iterable[Entry]) -> str:
    return "".join(render_entry(e) for e in entries)


def document(head: str, body: str) -> str:
    return f"{head}\n{body}"


# --- reading, for validation and tests -------------------------------------------------------------------------

_ATTR = re.compile(r'([A-Za-z0-9-]+)="([^"]*)"')


def parse(text: str) -> tuple[dict[str, str], list[dict]]:
    """(header attributes, entries) where each entry has 'duration', 'name', 'url' and its attributes."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith(HEADER):
        raise ValueError("playlist must start with #EXTM3U")
    head = dict(_ATTR.findall(lines[0]))
    entries: list[dict] = []
    info: dict | None = None
    for line in lines[1:]:
        if line.startswith("#EXTINF:"):
            meta, _, name = line[len("#EXTINF:") :].partition(",")
            duration, _, rest = meta.partition(" ")
            info = {"duration": int(duration), "name": name, **dict(_ATTR.findall(rest))}
        elif line.startswith("#") or not line.strip():
            continue
        else:
            if info is None:
                raise ValueError(f"URL without #EXTINF: {line[:80]}")
            info["url"] = line
            entries.append(info)
            info = None
    if info is not None:
        raise ValueError("#EXTINF without URL at end of playlist")
    return head, entries
