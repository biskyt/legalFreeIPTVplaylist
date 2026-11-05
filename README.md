[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/biskyt) [![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-ea4aaa?style=for-the-badge&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/biskyt)

_This work is free, with no ads and no tracking and no data collection. If you find it useful, you can support its
development by buying me a coffee with the links above._

# Legal free IPTV playlist

M3U playlists of **legally free** live TV (channels their owners publish) and public-domain or openly
licensed movies, for any IPTV app, with the reason for every entry published. A GitHub Action rebuilds them every day
and publishes them to GitHub Pages.

> This project only **links** to streams that their owners make freely available. It hosts no video.

## Why this project exists

I built this mainly to test [MyTVPlayer](https://github.com/biskyt/MyTVPlayer), my free and open-source IPTV
player for Android TV and Fire TV. Testing an IPTV app needs a realistic playlist: thousands of live channels in
many countries and languages, a TV guide, and movies and series with artwork, all of which can be shared and
shown in screenshots without anyone needing a paid subscription.

I've published it in case it's useful to other people too: anyone who wants free, legal TV without a
subscription, or other developers who need a test playlist for their own app. The playlists work in any IPTV app;
their extras (movies and series sections, languages, the TV guide) are tried out in
[MyTVPlayer](https://github.com/biskyt/MyTVPlayer) first.

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
  `US | News`, so players that only filter on group names can still sort by country. Britain is written
  `UK` there, as IPTV players expect (`tvg-country` uses the ISO code, `GB`); channels without a country use
  `INT`.
- **Channel logos** are links to images hosted by others, mostly from iptv-org's list, and mostly on Imgur, which
  has refused the UK since September 2025 (it shows an image saying so instead of the logo). Where iptv-org lists
  another logo for a channel and it loads, the playlist uses that one; about half the channels have no
  alternative and stay on Imgur.
- **TV guide:** playlists with live channels announce `epg.xml.gz` in their header (`url-tvg`), so most players
  load it automatically. Its channel ids are our `tvg-id`s exactly. It's merged nightly from the ready-made
  guides at [IPTV-EPG.org](https://iptv-epg.org) (one file per country), plus
  [iptv-org's grabber](https://github.com/iptv-org/epg) for the channels those files don't cover, which grabs one
  seventh of them each night, 8 days ahead. A channel a ready-made file covers is never scraped. The listings
  belong to those sources.
- **Movie details:** films carry `tmdb-id` and `imdb-id` when [Wikidata](https://www.wikidata.org) links the
  exact Archive item or Commons file to a film (about 70% of them), and a free poster from Wikimedia Commons
  when Wikidata has one. Episodes carry their show's ids. Players can use the ids to fetch artwork and details
  from TMDB. Descriptions, licences and credits are in `catalog.json`.

Each build also publishes:
- [`catalog.json`](https://biskyt.github.io/legalFreeIPTVplaylist/catalog.json): descriptions, licences and source pages;
- [`report.json`](https://biskyt.github.io/legalFreeIPTVplaylist/report.json): what was accepted or rejected, and why;
- [`credits.html`](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html): the legal basis for every channel and film, with links to the evidence.

## What's included, and why it's legal

**The rule: an entry is published only if we can show why it may be.** For every live channel, film and
episode, [`credits.html`](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html) states the reason and links
to the evidence, and `catalog.json` carries the same under `legal`. Anything we cannot prove is left out, however
likely it seems to be fine, and `report.json` lists what was left out and why. The rules are in
[`config/legal.yaml`](config/legal.yaml), and owners' removal requests (takedowns) are listed there too.

### Live TV
Channels come from the [iptv-org](https://github.com/iptv-org/iptv) database. iptv-org lists any public stream
it can find, including unofficial restreams, so **this project does not take its list as is**. A stream is
kept only if its owner serves it openly (no login), shown by one of these:

- **Its own domain:** the stream is served from a domain of the channel's own website.
- **Its own website:** the channel's own website refers to the stream's host (the build reads the sites of
  channels nothing else confirms, and caches the result).
- **Its own server:** the host is a delivery domain run by the broadcaster itself
  ([`config/live_hosts.yaml`](config/live_hosts.yaml)).

This shows the owner serves the stream openly; it is **not a licence** to play it in other apps. Each channel's
terms and conditions are linked on [`credits.html`](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html)
where its website has them (many small broadcasters publish none), and we remove any channel whose owner objects.

Also rejected: a stream with no identified channel; a channel on iptv-org's blocklist (DMCA or NSFW), marked NSFW
or closed; a stream on a bare IP address, with login details in its URL, or on a known restream host; one that
only plays with a spoofed user agent or referrer; and state media under UK/EU sanctions.

**Left out because nothing proves them:** streams on playout vendors' servers (a host name says nothing about
who may use a feed), streams where only a name in a shared CDN's address matches the channel, and anything an
owner has asked us to remove.

Every stream is then **health-checked**. For HLS, both the playlist and its first variant must load. Dead
streams are dropped; a channel with several streams falls back to the next working one.

### Movies
Movies come from [Wikimedia Commons](https://commons.wikimedia.org), the [Internet Archive](https://archive.org/),
and Blender Studio's open movies.

**Wikimedia Commons** only keeps films that are free in the US *and* in their country of origin, and each
file's page shows its licence and who vouched for it, so every Commons film is kept. When the same film is
available from Commons and the Archive, the Commons copy is used.

**Blender Studio's open movies** are published by the Blender Foundation itself under CC BY.

**Internet Archive** items are kept only when the Archive's own record dates them **before 1931**: a work
published in 1930 or earlier is in the US public domain by age. The Archive's public-domain marks and Creative
Commons labels are set by whoever uploaded an item (a 1975 ABC TV movie carries a CC BY label there), so they are
not relied on. The item must also have an MP4 file and not be on the [denylist](config/denylist.yaml).

### Series
No series episodes are included at the moment. The episodes we had came from the Internet Archive with nothing
but an uploader's public-domain claim, and no episode is old enough to be public domain by age. The series feed
exists and is empty; episodes will be added if a source can show why they are free.

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
| [iptv-org](https://github.com/iptv-org/iptv) | Database of publicly available live TV channels and streams (channels, streams, logos, blocklist) | Data published under the Unlicense (iptv-org/iptv and iptv-org/api) | iptv-org collects links; it does not host streams or check that they are licensed. This project keeps only the streams it can show the owner publishes. Each channel belongs to its broadcaster; see credits.html for every channel and why it is included. |
| [Internet Archive](https://archive.org/) | Films published before 1931, their metadata and thumbnails (collections feature_films, Film_Noir, SciFi_Horror, Comedy_Films, silent_films, classic_cartoons, prelinger) | Public domain in the US by age: works published in 1930 or earlier entered it on 1 January 2026 | Files are streamed directly from archive.org. Consider donating at https://archive.org/donate |
| [Blender Studio (Blender Foundation) open movies](https://studio.blender.org/films/) | Big Buck Bunny, Elephants Dream, Sintel, Tears of Steel, Cosmos Laundromat, Spring, Sprite Fright, Wing It!, Caminandes | Creative Commons Attribution (CC BY 2.5 / 3.0 / 4.0, per film) | Credit: © Blender Foundation \| studio.blender.org. Streamed from the Internet Archive's copies. |
| [Wikimedia Commons](https://commons.wikimedia.org/) | Public-domain and freely licensed films and videos (category "Films in the public domain") | Public domain in the US and in the country of origin, or CC0 / CC BY / CC BY-SA, per file | Each film's author and licence are listed in catalog.json and on its Commons page. |
| [IPTV-EPG.org](https://iptv-epg.org/) | TV guide listings (XMLTV) for 75 countries, merged into our epg.xml.gz for the channels we list | Free service; listings belong to the broadcasters. Ask us and we'll remove them | Downloaded once a night, per country. |
| [iptv-org/epg](https://github.com/iptv-org/epg) | The grabber that collects listings for the remaining channels from the guide sites it supports | Software under the Unlicense; listings belong to the sites they come from | Each channel is grabbed once a week, 8 days ahead, in a nightly rotation. |

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
  series Tuesday, Wikimedia Commons Wednesday, Archive movies Thursday). On that day, its new items and a
  quarter of the rest are checked.
- **TV guide:** the ready-made guides are fetched every night; the grabber's channels (only those no ready-made
  guide covers) rotate, one group a night, 8 days ahead each time.

Each source's results are kept as a snapshot, and every night's playlists are rebuilt from all snapshots, so a
source refreshed tonight replaces exactly its own entries. If a harvest fails, the previous snapshot is used.
All requests share one per-host limiter (a few connections per host, a gap between requests, and back-off when
a server says it's busy), and the big checks go round the hosts in turn.
To refresh everything at once, run `python -m freeplaylist build --all`, or start the workflow by hand with
**full** ticked.

**Staged runs.** To fill the playlists a source at a time (for example the very first time, or after deleting
the `state` branch), start the workflow by hand with **only** set to one or more sources, e.g. `iptv-org`, then
`curated,internet-archive-series,internet-archive-movies`, then `wikimedia-commons` (`--only=...` locally). Each run publishes what has been harvested so far; sources not harvested yet are left
out until their stage runs.

**Publishing:** [`.github/workflows/build.yml`](.github/workflows/build.yml) builds daily at 04:17 UTC and on
manual runs (Actions tab → Build playlists → Run workflow); merges don't start a build. The build runs as
separate steps (one harvest per source, then the live and the movie checks, the playlists and the TV guide),
the same as `python -m freeplaylist build --phase ...` locally, so the run's page shows how far it has got. It deploys to GitHub Pages. If a build comes out broken
(an upstream API down, too few entries), the job fails and the previous playlists stay online. To enable
it: **Settings → Pages → Source: GitHub Actions**.

Layout:

```
config/        what to include: sources, rules, allow/deny lists, feeds, credits
src/freeplaylist/
  sources/     iptv_org.py (live + rules), website_check.py, internet_archive.py (movies, series),
               wikimedia_commons.py, curated.py
  enrich.py (Wikidata ids)  epg.py  languages.py  healthcheck.py  feeds.py  m3u.py  credits.py  build.py
tests/         offline tests (fixtures only)
FORMAT.md      the M3U movie/series convention
```

## Support

This project is free, with no ads and no tracking. If you find it useful, you can support its development:

- [Ko-fi](https://ko-fi.com/biskyt)
- [GitHub Sponsors](https://github.com/sponsors/biskyt)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), which includes the checklist for proposing a new source.

## Licence

Code: [MIT](LICENSE). [FORMAT.md](FORMAT.md): CC0. Linked content belongs to its owners, as credited above.
