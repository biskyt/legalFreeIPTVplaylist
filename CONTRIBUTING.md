# Contributing

Thanks for helping. Issues and pull requests are welcome, especially:
- reports of streams that aren't official, or films that aren't public domain (these are removed quickly);
- official free streams that the rules miss;
- new sources that pass the checklist below.

## Proposing a source, channel or show

Every addition must be **free to watch and free to link to**. Please check each point:

1. **Who owns it?** Name the rights holder.
2. **Why is it free?** One of these:
   - the owner streams it for free themselves (a broadcaster's own site, or a free streaming service such as Pluto TV);
   - it's in the public domain in the US (give the reason, e.g. "published 1925", "copyright not renewed",
     or "US government work");
   - it's under an open licence that allows redistribution unchanged (CC BY or CC BY-SA). NC and ND licences
     aren't accepted for automatic sources.
3. **Is the URL the owner's?** No restreams, no scraped tokens, no URLs that only work with a spoofed user
   agent or referrer, and nothing behind a login or paywall.
4. **Credit:** add or update an entry in [`config/credits.yaml`](config/credits.yaml), then run
   `python -m freeplaylist credits` to regenerate the README table.

Where to make the change:

| You want to… | Edit |
|---|---|
| Accept a broadcaster's own delivery domain | `config/live_hosts.yaml` → `broadcaster_hosts` |
| Accept or block a specific channel | `config/live_allowlist.yaml` |
| Block a restream host | `config/live_hosts.yaml` → `denied_domains` |
| Add an Internet Archive collection | `config/movies.yaml` |
| Add a public-domain TV show | `config/series.yaml` (include the `basis` and `max_year`) |
| Add a specific film or stream | `config/curated.yaml` |
| Remove an Archive item | `config/denylist.yaml` |

## Development

```sh
pip install -e ".[dev]"
ruff check . && pytest
python -m freeplaylist build --live-only --no-health --out site   # quick look at the live feed
```

The tests run offline. Build changes should keep the playlists inside the [FORMAT.md](FORMAT.md)
compatibility rules. `tests/test_m3u.py` checks them.
