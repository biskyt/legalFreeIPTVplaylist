# Legal free IPTV playlist

M3U playlists of **legally free** live TV, free ad-supported (FAST) channels, and public-domain or openly
licensed movies and TV series, for any IPTV app. A GitHub Action rebuilds them every day and publishes them to
GitHub Pages.

It started as demo content for [MyTVPlayer](https://github.com/biskyt/MyTVPlayer), but it's meant to be
useful to anyone who wants free TV without a subscription.

> This project only **links** to streams that their owners make freely available. It hosts no video.

## Playlists

| URL | Contents |
|---|---|
| `https://biskyt.github.io/legalFreeIPTVplaylist/playlist.m3u` | Everything: live, movies and series |
| `https://biskyt.github.io/legalFreeIPTVplaylist/live.m3u` | Live TV and FAST channels |
| `https://biskyt.github.io/legalFreeIPTVplaylist/vod.m3u` | Movies and series |
| `https://biskyt.github.io/legalFreeIPTVplaylist/movies.m3u` | Movies only |
| `https://biskyt.github.io/legalFreeIPTVplaylist/series.m3u` | Series only |

Use `playlist.m3u` in apps that understand our [movie and series convention](FORMAT.md). Apps that take one
playlist per content type can use the separate feeds instead. Any app can play every entry: apps that don't
know the convention list films and episodes as channels, grouped as `Movies: …` and `Series: …`.

Live channel ids are [iptv-org](https://github.com/iptv-org/iptv) ids, so guides keyed on those ids (for
example from [iptv-epg.org](https://iptv-epg.org) or the
[iptv-org/epg](https://github.com/iptv-org/epg) grabber) match them. A published guide is planned.

Each build also publishes:
- [`catalog.json`](https://biskyt.github.io/legalFreeIPTVplaylist/catalog.json): descriptions, licences and source pages;
- [`report.json`](https://biskyt.github.io/legalFreeIPTVplaylist/report.json): what was accepted or rejected, and why;
- [`credits.html`](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html): every broadcaster.

## What's included, and why it's legal

### Live TV and FAST channels
Channels come from the [iptv-org](https://github.com/iptv-org/iptv) database. iptv-org lists any public stream
it can find, including unofficial restreams, so **this project does not take its list as is**. A stream is
included only if the automatic rules in [`config/live_hosts.yaml`](config/live_hosts.yaml) find it official:

- **Rejected:** a stream with no identified channel; a channel on iptv-org's blocklist (DMCA or NSFW), marked
  NSFW, or closed; a stream on a bare IP address, with login details in its URL, or on a known restream host;
  and a stream that only plays with a spoofed user agent or referrer (unless the host is an official one).
- **Accepted:** a stream on the broadcaster's own domain, or on a delivery domain the broadcaster runs; on a
  FAST service (Pluto TV, Samsung TV Plus, Plex, The Roku Channel, Tubi); on a licensed playout service
  (Amagi, Wurl and similar); or on a general CDN whose address names the broadcaster.
- **Anything else is left out** and listed in `report.json`, so the rules can be improved over time.
- [`config/live_allowlist.yaml`](config/live_allowlist.yaml) holds manual decisions, which override the rules.

Every stream is then **health-checked**. For HLS, both the playlist and its first variant must load. Dead
streams are dropped; a channel with several streams falls back to the next working one.

### Movies
Movies come from the [Internet Archive](https://archive.org/) and from Blender Studio's open movies. Archive
uploaders set licence and date details themselves, so an item is used only when:
- it has a public-domain mark and is dated **1977 or earlier**; or
- it has a CC BY or CC BY-SA licence (NC and ND licences are never used); or
- it has no licence but is dated **before 1931**, which makes it public domain in the US by age.

The item's own page must confirm the licence, it must have an MP4 file, and it must not be on the
[denylist](config/denylist.yaml).

### Series
Series come only from shows listed in [`config/series.yaml`](config/series.yaml), whose episodes are known to
be in the US public domain, mostly because their copyright was never renewed. Each episode must also carry a
public-domain or CC BY / BY-SA licence on its Archive page.

### Important: "public domain" means public domain in the United States
The films and episodes here are public domain under **US** law. Copyright terms differ between countries.
In the UK and EU, for example, a film can stay protected for 70 years after its director or writers died. If
you're outside the US, check what applies where you live. FAST channels and some broadcasters also limit
their streams to certain countries.

## Sources and credits

<!-- credits:start -->
| Source | What we use | Licence / legal basis | Credit and notes |
|---|---|---|---|
| [iptv-org](https://github.com/iptv-org/iptv) | Database of publicly available live TV channels and streams (channels, streams, logos, blocklist) | Data published under the Unlicense (iptv-org/iptv and iptv-org/api) | iptv-org collects links; it does not host streams or check that they are licensed. This project keeps only the streams its rules find official. Each channel belongs to its broadcaster; see credits.html for the list. |
| [Internet Archive](https://archive.org/) | Public-domain and CC BY / BY-SA movies and TV episodes, their metadata and thumbnails (collections feature_films, Film_Noir, SciFi_Horror, Comedy_Films, silent_films, classic_cartoons, prelinger, classic_tv) | Public domain in the US, or the CC licence shown on each item; see each item's page | Files are streamed directly from archive.org. Consider donating at https://archive.org/donate |
| [Blender Studio (Blender Foundation) open movies](https://studio.blender.org/films/) | Big Buck Bunny, Elephants Dream, Sintel, Tears of Steel, Cosmos Laundromat, Spring, Sprite Fright, Wing It!, Caminandes | Creative Commons Attribution (CC BY 2.5 / 3.0 / 4.0, per film) | Credit: © Blender Foundation \| studio.blender.org. Streamed from the Internet Archive's copies. |
| [Pluto TV](https://pluto.tv/) | Free, ad-supported (FAST) channels | Free to watch from Pluto TV; content and trademarks belong to Pluto TV and its partners | Linked through jmp2.uk, a third-party redirector used by iptv-org, not an official Pluto TV service. Availability varies by country. |
| [Samsung TV Plus](https://www.samsungtvplus.com/) | Free, ad-supported (FAST) channels | Free to watch from Samsung TV Plus; content and trademarks belong to Samsung and its partners | Some streams are linked through jmp2.uk, a third-party redirector. Availability varies by country. |
| [Plex](https://www.plex.tv/live-tv/) | Free, ad-supported (FAST) channels | Free to watch from Plex; content and trademarks belong to Plex and its partners |  |
| [The Roku Channel](https://therokuchannel.roku.com/) | Free, ad-supported (FAST) channels | Free to watch from The Roku Channel; content and trademarks belong to Roku and its partners |  |
| [Tubi](https://tubitv.com/) | Free, ad-supported (FAST) channels | Free to watch from Tubi; content and trademarks belong to Tubi and its partners |  |

Every live channel belongs to its broadcaster. The full list of broadcasters, with links, is published with each build in [credits.html](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html).
<!-- credits:end -->

This table is generated from [`config/credits.yaml`](config/credits.yaml). Every source the build uses must
have an entry there; the build and the tests fail otherwise.

## Takedowns and corrections

If something here shouldn't be (a stream that isn't official, a film that isn't public domain, or anything
else), please [open an issue](https://github.com/biskyt/legalFreeIPTVplaylist/issues). It will be removed from
the next build. Rights holders can expect removal without discussion.

## Building it yourself

Requires Python 3.12 or later.

```sh
pip install -e ".[dev]"
python -m freeplaylist build --out site --state state   # full build (network; ~15–30 min on first run)
python -m freeplaylist build --live-only --no-health    # quick partial build
python -m freeplaylist credits                          # regenerate the README credits table
ruff check . && pytest
```

`state/` caches Internet Archive metadata and stream health between runs; the GitHub Action keeps it in the
Actions cache.

**Publishing:** [`.github/workflows/build.yml`](.github/workflows/build.yml) builds daily at 04:17 UTC, on
manual runs, and on pushes that change code or config. It deploys to GitHub Pages. If a build comes out broken
(an upstream API down, too few entries), the job fails and the previous playlists stay online. To enable
it: **Settings → Pages → Source: GitHub Actions**.

Layout:

```
config/        what to include: sources, rules, allow/deny lists, feeds, credits
src/freeplaylist/
  sources/     iptv_org.py (live + rules), internet_archive.py (movies, series), curated.py
  healthcheck.py  feeds.py  m3u.py  credits.py  build.py
tests/         offline tests (fixtures only)
FORMAT.md      the M3U movie/series convention
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), which includes the checklist for proposing a new source.

## Licence

Code: [MIT](LICENSE). [FORMAT.md](FORMAT.md): CC0. Linked content belongs to its owners, as credited above.
