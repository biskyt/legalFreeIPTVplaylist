"""Source credits: the README section (from config/credits.yaml) and the per-broadcaster list on the site."""

from __future__ import annotations

import html
from pathlib import Path

from .models import Entry

START, END = "<!-- credits:start -->", "<!-- credits:end -->"


def missing(entries: list[Entry], sources: dict) -> set[str]:
    """Sources used by entries that have no credit record."""
    return {e.source for e in entries} - set(sources)


def _md(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def readme_section(sources: dict) -> str:
    rows = ["| Source | What we use | Licence / legal basis | Credit and notes |", "|---|---|---|---|"]
    for s in sources.values():
        notes = " ".join(x for x in (s.get("attribution") and f"Credit: {s['attribution']}.", s.get("note")) if x)
        rows.append(f"| [{_md(s['name'])}]({s['url']}) | {_md(s['provides'])} | {_md(s['license'])} | {_md(notes)} |")
    rows.append("")
    rows.append("Every live channel belongs to its broadcaster. The full list of broadcasters, with links, is "
                "published with each build in [credits.html](https://biskyt.github.io/licenseFreeIPTVplaylist/credits.html).")
    return "\n".join(rows)


def update_readme(path: Path, sources: dict) -> bool:
    """Rewrite the credits block in the README; True when the file changed."""
    text = path.read_text(encoding="utf-8")
    head, sep, rest = text.partition(START)
    if not sep or END not in rest:
        raise ValueError(f"{path} has no {START} ... {END} block")
    new = f"{head}{START}\n{readme_section(sources)}\n{END}{rest.partition(END)[2]}"
    if new != text:
        path.write_text(new, encoding="utf-8")
    return new != text


def broadcasters_html(entries: list[Entry], sources: dict) -> str:
    """credits.html: every source, then every live channel's broadcaster with its website."""
    esc = html.escape
    items = "".join(
        f'<li><a href="{esc(s["url"])}">{esc(s["name"])}</a>: {esc(s["provides"])}. <em>{esc(s["license"])}</em>'
        + (f' {esc(s["attribution"])}' if s.get("attribution") else "") + "</li>"
        for s in sources.values()
    )
    seen: dict[str, Entry] = {}
    for e in entries:
        if e.kind == "live":
            seen.setdefault(e.extra.get("broadcaster") or e.title, e)
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            esc(name), esc(e.extra.get("country") or ""), esc(e.group),
            f'<a href="{esc(e.page)}">{esc(e.page)}</a>' if e.page else "",
        )
        for name, e in sorted(seen.items(), key=lambda kv: kv[0].lower())
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Credits</title>
<style>body{{font-family:system-ui,sans-serif;max-width:60rem;margin:auto;padding:1rem;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ccc;padding:.3rem;text-align:left}}</style>
</head><body>
<h1>Credits</h1>
<p>This project only links to streams; it hosts no video. Each channel, film and episode belongs to its owner.</p>
<h2>Sources</h2><ul>{items}</ul>
<h2>Broadcasters ({len(seen)})</h2>
<table><thead><tr><th>Channel</th><th>Country</th><th>Group</th><th>Website</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>
"""
