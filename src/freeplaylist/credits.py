"""Source credits: the README section (from config/credits.yaml) and the per-broadcaster list on the site."""

from __future__ import annotations

import html
from pathlib import Path

from . import legal
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
                "published with each build in [credits.html](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html).")
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


def _links(links) -> str:
    return " · ".join(f'<a href="{html.escape(u)}">{html.escape(label)}</a>' for label, u in links)


def credits_html(entries: list[Entry], sources: dict, policy: dict) -> str:
    """credits.html: what is accepted as proof, the sources, and the basis for every live channel and every film or
    episode that is included, with links to the evidence."""
    esc = html.escape
    live = [e for e in entries if e.kind == "live"]
    vod = [e for e in entries if e.kind != "live"]
    evid = {e.id: legal.evidence(e, policy, sources) for e in entries}

    def count_by(rows) -> list[tuple[str, str, int]]:
        out: dict[str, list] = {}
        for e in rows:
            ev = evid[e.id]
            out.setdefault(ev.basis, [ev.title, 0])[1] += 1
        return sorted(((b, t, n) for b, (t, n) in out.items()), key=lambda x: -x[2])

    bases = "".join(f"<li>{esc(t)}: <strong>{n}</strong></li>" for _, t, n in count_by(live) + count_by(vod))

    used = {e.source for e in entries}
    items = "".join(
        f'<li><a href="{esc(s["url"])}">{esc(s["name"])}</a>: {esc(" ".join(str(s["provides"]).split()))}. '
        f'<em>{esc(" ".join(str(s["license"]).split()))}</em>'
        + (f" {esc(s['attribution'])}" if s.get("attribution") else "")
        + (f"<br><strong>Why we keep it:</strong> {esc(' '.join(str(s['proof']).split()))}" if s.get("proof") else "")
        + "</li>"
        for key, s in sources.items()
        if (key in used or key == "iptv-org" and live or key == "internet-archive" and vod)
    )

    def terms(ev) -> str:
        if ev.terms:
            return " · ".join(f'<a href="{esc(u)}">Terms and conditions</a>' for u in ev.terms[:2])
        return "<small>None found on the site: check the channel website</small>"

    def live_row(e: Entry) -> str:
        ev = evid[e.id]
        name = e.extra.get("broadcaster") or e.title
        return "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            esc(name), esc(e.extra.get("country") or ""), esc(ev.text), _links(ev.links), terms(ev))

    def vod_row(e: Entry) -> str:
        ev = evid[e.id]
        credit = f"<br><small>{esc(e.attribution)}</small>" if e.attribution else ""
        return "<tr><td>{}{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            esc(e.title), credit, e.year or "", esc(ev.text), _links(ev.links), terms(ev))

    name = lambda e: (e.extra.get("broadcaster") or e.title).lower()  # noqa: E731
    live_rows = "".join(live_row(e) for e in sorted(live, key=name))
    vod_rows = "".join(vod_row(e) for e in sorted(vod, key=lambda e: e.title.lower()))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sources, credits and legal basis</title>
<style>body{{font-family:system-ui,sans-serif;max-width:70rem;margin:auto;padding:1rem;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ccc;padding:.3rem;text-align:left;vertical-align:top}}
small{{color:#555}}</style>
</head><body>
<h1>Sources, credits and legal basis</h1>
<p>This project only links to streams and files; it hosts no video. Each channel, film and episode belongs to its
owner. <strong>Films</strong> are public domain or openly licensed: the basis and evidence for each are below.
<strong>Live channels</strong> are streams that their owners serve openly (no login) from their own websites.
We link to them; we do not claim a licence to play them in other apps, and we have not verified that every owner's
terms allow it. Each channel's terms and conditions are linked below where its website has them (many small
broadcasters publish none). If you own
something listed here and want it removed, <a href="https://github.com/biskyt/legalFreeIPTVplaylist/issues">tell us</a>
and it will be removed.</p>
<h2>Basis for what is included</h2><ul>{bases}</ul>
<h2>Sources</h2><ul>{items}</ul>
<h2 id="live">Live channels ({len(live)})</h2>
<table><thead><tr><th>Channel</th><th>Country</th><th>Basis</th><th>Evidence</th><th>Terms</th></tr></thead>
<tbody>{live_rows}</tbody></table>
<h2 id="films">Films and episodes ({len(vod)})</h2>
<table><thead><tr><th>Title</th><th>Year</th><th>Basis</th><th>Evidence</th><th>Terms</th></tr></thead>
<tbody>{vod_rows}</tbody></table>
</body></html>
"""
