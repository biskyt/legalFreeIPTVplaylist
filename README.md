# Legal free IPTV playlist

M3U playlists of **legally free** live TV (including free, ad-supported services such as Pluto TV), and public-domain or openly
licensed movies and TV series, for any IPTV app. A GitHub Action rebuilds them every day and publishes them to
GitHub Pages.

It started as demo content for [MyTVPlayer](https://github.com/biskyt/MyTVPlayer), but it's meant to be
useful to anyone who wants free TV without a subscription.

> This project only **links** to streams that their owners make freely available. It hosts no video.

## Playlists

| URL | Contents |
|---|---|
| `https://biskyt.github.io/legalFreeIPTVplaylist/playlist.m3u` | Everything: live, movies and series |
| `https://biskyt.github.io/legalFreeIPTVplaylist/live.m3u` | Live TV channels |
| `https://biskyt.github.io/legalFreeIPTVplaylist/vod.m3u` | Movies and series |
| `https://biskyt.github.io/legalFreeIPTVplaylist/movies.m3u` | Movies only |
| `https://biskyt.github.io/legalFreeIPTVplaylist/series.m3u` | Series only |
| `https://biskyt.github.io/legalFreeIPTVplaylist/languages/<code>.m3u` | Everything in one language, e.g. [`languages/fra.m3u`](https://biskyt.github.io/legalFreeIPTVplaylist/languages/fra.m3u) for French; [list](https://biskyt.github.io/legalFreeIPTVplaylist/) |
| `https://biskyt.github.io/legalFreeIPTVplaylist/epg.xml.gz` | TV guide (XMLTV) for the live channels |

Use `playlist.m3u` in apps that understand our [movie and series convention](FORMAT.md). Apps that take one
playlist per content type can use the separate feeds instead. Any app can play every entry: apps that don't
know the convention list films and episodes as channels, grouped as `Movies: …` and `Series: …`.

### Languages, TV guide and movie details
- **Languages:** every entry is tagged with `tvg-language` (e.g. `English;Spanish`) and `tvg-country` (e.g.
  `DE;AT`), the attributes iptv-org's playlists also use, so players can filter by them. There's also one
  playlist per language (any language with at least 10 entries). Silent films appear in every language's list.
  Live channels get their languages from iptv-org; films from their source, or a per-collection default.
- **Country in group names:** live channel groups start with a two-letter country code, e.g. `DE | News`,
  `US | Pluto TV`, so players that only filter on group names can still sort by country. Britain is written
  `UK` there, as IPTV players expect (`tvg-country` uses the ISO code, `GB`); channels without a country use
  `INT`.
- **TV guide:** playlists with live channels announce `epg.xml.gz` in their header (`url-tvg`), so most players
  load it automatically. It's built daily with [iptv-org's EPG grabber](https://github.com/iptv-org/epg) for
  every channel that has a known guide source (roughly half of them); the guide data belongs to those sources.
- **Movie details:** films carry `tmdb-id` and `imdb-id` when [Wikidata](https://www.wikidata.org) links the
  exact Archive item or Commons file to a film (about 70% of them), and a free poster from Wikimedia Commons
  when Wikidata has one. Episodes carry their show's ids. Players can use the ids to fetch artwork and details
  from TMDB. Descriptions, licences and credits are in `catalog.json`.

Each build also publishes:
- [`catalog.json`](https://biskyt.github.io/legalFreeIPTVplaylist/catalog.json): descriptions, licences and source pages;
- [`report.json`](https://biskyt.github.io/legalFreeIPTVplaylist/report.json): what was accepted or rejected, and why;
- [`credits.html`](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html): every broadcaster.

## What's included, and why it's legal

### Live TV
Channels come from the [iptv-org](https://github.com/iptv-org/iptv) database. iptv-org lists any public stream
it can find, including unofficial restreams, so **this project does not take its list as is**. A stream is
included only if the automatic rules in [`config/live_hosts.yaml`](config/live_hosts.yaml) find it official:

- **Rejected:** a stream with no identified channel; a channel on iptv-org's blocklist (DMCA or NSFW), marked
  NSFW, or closed; a stream on a bare IP address, with login details in its URL, or on a known restream host;
  and a stream that only plays with a spoofed user agent or referrer (unless the host is an official one).
- **Accepted:** a stream on the broadcaster's own domain, or on a delivery domain the broadcaster runs; on a
  free streaming service (Pluto TV, Samsung TV Plus, Plex, The Roku Channel, Tubi, Rakuten TV, Xumo Play; see
  below); on a licensed playout service (Amagi, Wurl and similar) or a US public-access platform; on a general CDN whose address
  names the broadcaster; or on any host that **the broadcaster's own website links to** (the build checks
  the sites of channels whose streams nothing else confirms, and caches the result for a week).
- **Never accepted:** state media under UK/EU sanctions.
- **Anything else is left out** and listed in `report.json`, so the rules can be improved over time.
- [`config/live_allowlist.yaml`](config/live_allowlist.yaml) holds manual decisions, which override the rules.

**Free streaming services (FAST).** Pluto TV, Samsung TV Plus, Plex, The Roku Channel, Tubi, Rakuten TV and
Xumo Play are *Free Ad-Supported Streaming Television* services, known in the industry as FAST. They license
their channels from the rights holders and pay for them with adverts, so they stream them to anyone for free, usually
without an account. That's why their channels count as legally free here. Their channels are grouped under the
service's name (e.g. `US | Pluto TV`). Most of them are only available in certain countries.

Every stream is then **health-checked**. For HLS, both the playlist and its first variant must load. Dead
streams are dropped; a channel with several streams falls back to the next working one.

### Movies
Movies come from [Wikimedia Commons](https://commons.wikimedia.org), the [Internet Archive](https://archive.org/),
Blender Studio's open movies and [Open Beelden](https://www.openbeelden.nl) (Dutch archive film).

**Wikimedia Commons** only keeps films that are free in the US *and* in their country of origin, so these are
the safest choice outside the US. When the same film is available from Commons and the Archive, the Commons
copy is used. **Open Beelden** items are public domain or CC BY / BY-SA, as stated on each item.

**Internet Archive** uploaders set licence and date details themselves, so an item is used only when:
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
you're outside the US, check what applies where you live. (Films from Wikimedia Commons are the exception:
they're free in their country of origin too.)

### Your responsibilities
- Free streaming services and many broadcasters limit their streams to certain countries (`tvg-country` shows where a
  live feed is meant to be watched). This project doesn't get around geo-blocking, and you shouldn't either.
- In the UK, you need a [TV Licence](https://www.tvlicensing.co.uk/) to watch or record live TV on any channel
  or service, including the live channels here. Other countries have their own rules.

## Sources and credits

<!-- credits:start -->
| Source | What we use | Licence / legal basis | Credit and notes |
|---|---|---|---|
| [iptv-org](https://github.com/iptv-org/iptv) | Database of publicly available live TV channels and streams (channels, streams, logos, blocklist) | Data published under the Unlicense (iptv-org/iptv and iptv-org/api) | iptv-org collects links; it does not host streams or check that they are licensed. This project keeps only the streams its rules find official. Each channel belongs to its broadcaster; see credits.html for the list. |
| [Internet Archive](https://archive.org/) | Public-domain and CC BY / BY-SA movies and TV episodes, their metadata and thumbnails (collections feature_films, Film_Noir, SciFi_Horror, Comedy_Films, silent_films, classic_cartoons, prelinger, classic_tv) | Public domain in the US, or the CC licence shown on each item; see each item's page | Files are streamed directly from archive.org. Consider donating at https://archive.org/donate |
| [Blender Studio (Blender Foundation) open movies](https://studio.blender.org/films/) | Big Buck Bunny, Elephants Dream, Sintel, Tears of Steel, Cosmos Laundromat, Spring, Sprite Fright, Wing It!, Caminandes | Creative Commons Attribution (CC BY 2.5 / 3.0 / 4.0, per film) | Credit: © Blender Foundation \| studio.blender.org. Streamed from the Internet Archive's copies. |
| [Pluto TV](https://pluto.tv/) | Free, ad-supported streaming channels | Free to watch from Pluto TV; content and trademarks belong to Pluto TV and its partners | Linked through jmp2.uk, a third-party redirector used by iptv-org, not an official Pluto TV service. Availability varies by country. |
| [Samsung TV Plus](https://www.samsungtvplus.com/) | Free, ad-supported streaming channels | Free to watch from Samsung TV Plus; content and trademarks belong to Samsung and its partners | Some streams are linked through jmp2.uk, a third-party redirector. Availability varies by country. |
| [Plex](https://www.plex.tv/live-tv/) | Free, ad-supported streaming channels | Free to watch from Plex; content and trademarks belong to Plex and its partners |  |
| [The Roku Channel](https://therokuchannel.roku.com/) | Free, ad-supported streaming channels | Free to watch from The Roku Channel; content and trademarks belong to Roku and its partners |  |
| [Tubi](https://tubitv.com/) | Free, ad-supported streaming channels | Free to watch from Tubi; content and trademarks belong to Tubi and its partners |  |
| [Rakuten TV](https://www.rakuten.tv/) | Free, ad-supported streaming channels | Free to watch from Rakuten TV; content and trademarks belong to Rakuten TV and its partners | Availability varies by country. |
| [Xumo Play](https://play.xumo.com/) | Free, ad-supported streaming channels | Free to watch from Xumo Play; content and trademarks belong to Xumo and its partners | Availability varies by country. |
| [Wikimedia Commons](https://commons.wikimedia.org/) | Public-domain and freely licensed films and videos (category "Films in the public domain") | Public domain in the US and in the country of origin, or CC0 / CC BY / CC BY-SA, per file | Each film's author and licence are listed in catalog.json and on its Commons page. |
| [Open Beelden (Netherlands Institute for Sound and Vision)](https://www.openbeelden.nl/) | Dutch archive films and newsreels | Public domain or CC BY / CC BY-SA, per item | Credit: Nederlands Instituut voor Beeld en Geluid / Open Beelden. Each item's maker and licence are listed in catalog.json and on its Open Beelden page. |

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
python -m freeplaylist build --out site --state state   # tonight's scheduled share (first run does everything)
python -m freeplaylist build --all                      # everything now (network; up to an hour or more)
python -m freeplaylist build --live-only --no-health    # quick partial build
python -m freeplaylist credits                          # regenerate the README credits table
ruff check . && pytest
```

`state/` keeps each source's last results (snapshots), stream health and other caches between runs. The GitHub
Action saves it on the `state` branch as a single compressed file, replaced each night by one commit, so it
never expires and the repository doesn't grow. Deleting that branch makes the next run start from scratch.

**Nightly schedule.** Harvesting and checking everything takes a long time and would put a lot of load on
other people's servers, so each night does a share of it ([`config/schedule.yaml`](config/schedule.yaml)):
- **Live channels:** the channel list is refreshed every night. Stream hosts are split into 7 groups, and each
  night checks one group plus any stream never seen before. The broadcasters' websites (the website rule above)
  rotate the same way.
- **Movies and series:** each source is harvested once a week, on its own day (curated films Monday, Archive
  series Tuesday, Wikimedia Commons Wednesday, Archive movies Thursday, Open Beelden Friday). On that day, its
  new items and a quarter of the rest are checked.
- **TV guide:** grabbed every night.

Each source's results are kept as a snapshot, and every night's playlists are rebuilt from all snapshots, so a
source refreshed tonight replaces exactly its own entries. If a harvest fails, the previous snapshot is used.
All requests share one per-host limiter (a few connections per host, a gap between requests, and back-off when
a server says it's busy), and the big checks go round the hosts in turn.
To refresh everything at once, run `python -m freeplaylist build --all`, or start the workflow by hand with
**full** ticked.

**Staged runs.** To fill the playlists a source at a time (for example the very first time, or after deleting
the `state` branch), start the workflow by hand with **only** set to one or more sources, e.g. `iptv-org`, then
`curated,internet-archive-series,internet-archive-movies`, then `wikimedia-commons`, then `open-beelden`
(`--only=...` locally). Each run publishes what has been harvested so far; sources not harvested yet are left
out until their stage runs.

**Publishing:** [`.github/workflows/build.yml`](.github/workflows/build.yml) builds daily at 04:17 UTC, on
manual runs, and on pushes that change code or config. It deploys to GitHub Pages. If a build comes out broken
(an upstream API down, too few entries), the job fails and the previous playlists stay online. To enable
it: **Settings → Pages → Source: GitHub Actions**.

Layout:

```
config/        what to include: sources, rules, allow/deny lists, feeds, credits
src/freeplaylist/
  sources/     iptv_org.py (live + rules), website_check.py, internet_archive.py (movies, series),
               wikimedia_commons.py, open_beelden.py, curated.py
  enrich.py (Wikidata ids)  epg.py  languages.py  healthcheck.py  feeds.py  m3u.py  credits.py  build.py
tests/         offline tests (fixtures only)
FORMAT.md      the M3U movie/series convention
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), which includes the checklist for proposing a new source.

## Licence

Code: [MIT](LICENSE). [FORMAT.md](FORMAT.md): CC0. Linked content belongs to its owners, as credited above.
