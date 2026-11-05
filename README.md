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
player for Android TV and Fire TV. Testing an IPTV app needs a realistic playlist: live channels in several
countries and languages, and movies with artwork, all of which can be shared and shown in screenshots without
anyone needing a paid subscription.

I've published it in case it's useful to other people too: anyone who wants free, legal TV without a
subscription, or other developers who need a test playlist for their own app. The playlists work in any IPTV app;
their extras (movies and series sections, languages) are tried out in
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

Use `playlist.m3u` in apps that understand our [movie and series convention](FORMAT.md). Apps that take one
playlist per content type can use the separate feeds instead. Any app can play every entry: apps that don't
know the convention list films and episodes as channels, grouped as `Movies: …` and `Series: …`.

### Languages and movie details
- **Languages:** every entry is tagged with `tvg-language` (e.g. `English;Spanish`) and `tvg-country` (e.g.
  `DE;AT`), the de facto attributes many playlists use, so players can filter by them. There's also one
  playlist per language (any language with at least 10 entries). Silent films appear in every language's list.
  Films get their languages from their source, or a per-collection default; live channels from their entry in
  `config/curated.yaml`.
- **Country in group names:** live channel groups start with a two-letter country code, e.g. `DE | News`,
  `US | News`, so players that only filter on group names can still sort by country. Britain is written
  `UK` there, as IPTV players expect (`tvg-country` uses the ISO code, `GB`); channels without a country use
  `INT`.
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
A channel is included only if **its owner's own terms or pages say others may use it**. Each such channel is
listed in [`config/permissions.yaml`](config/permissions.yaml) with the owner's exact words and the page they're
on, and [`credits.html`](https://biskyt.github.io/legalFreeIPTVplaylist/credits.html) shows both. Terms that allow
use only for some purposes we don't meet (journalism, education), only non-commercial use, only embedding the
owner's own player, or only on request don't count, and neither do terms that forbid it. Very few broadcasters say
anything at all, so this is a short list; it grows as owners' terms are found or permission is given. We remove
any channel whose owner objects.

The stream address comes straight from the owner's own page (the page is named in the same file), and the channel's
logo from the owner's own site. A channel is set up in [`config/curated.yaml`](config/curated.yaml).

Every stream is **health-checked**. For HLS, both the playlist and its first variant must load. Dead streams are
dropped.

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
| [Voice of America](https://www.voanews.com/) | The live TV channels VOA Persian TV and VOA Chinese TV | Public domain: material produced exclusively by the Voice of America | Material licensed to VOA from others (news agencies) is not covered and may appear in the channels. |
| [Government of the District of Columbia](https://entertainment.dc.gov/) | The live TV channel District of Columbia Network (DCN) | Creative Commons Attribution 3.0, apart from third-party content | Credit: Government of the District of Columbia, Office of Cable Television, Film, Music and Entertainment. |
| [Internet Archive](https://archive.org/) | Films published before 1931, their metadata and thumbnails (collections feature_films, Film_Noir, SciFi_Horror, Comedy_Films, silent_films, classic_cartoons, prelinger) | Public domain in the US by age: works published in 1930 or earlier entered it on 1 January 2026 | Files are streamed directly from archive.org. Consider donating at https://archive.org/donate |
| [Blender Studio (Blender Foundation) open movies](https://studio.blender.org/films/) | Big Buck Bunny, Elephants Dream, Sintel, Tears of Steel, Cosmos Laundromat, Spring, Sprite Fright, Wing It!, Caminandes | Creative Commons Attribution (CC BY 2.5 / 3.0 / 4.0, per film) | Credit: © Blender Foundation \| studio.blender.org. Streamed from the Internet Archive's copies. |
| [Wikimedia Commons](https://commons.wikimedia.org/) | Public-domain and freely licensed films and videos (category "Films in the public domain") | Public domain in the US and in the country of origin, or CC0 / CC BY / CC BY-SA, per file | Each film's author and licence are listed in catalog.json and on its Commons page. |

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
python -m freeplaylist build --live-only --no-health    # quick partial build (live channels only)
python -m freeplaylist credits                          # regenerate the README credits table
ruff check . && pytest
```

`state/` keeps each source's last results (snapshots), stream health and other caches between runs. The GitHub
Action saves it on the `state` branch as a single compressed file, replaced each night by one commit, so it
never expires and the repository doesn't grow. Deleting that branch makes the next run start from scratch.

**Nightly schedule.** Harvesting and checking everything takes a long time and would put a lot of load on
other people's servers, so each night does a share of it ([`config/schedule.yaml`](config/schedule.yaml)):
- **Live channels:** their streams are split into groups by host, and each night checks one group plus any
  stream never seen before.
- **Movies and series:** each source is harvested once a week, on its own day (curated films Monday, Archive
  series Tuesday, Wikimedia Commons Wednesday, Archive movies Thursday). On that day, its new items and a
  quarter of the rest are checked.

Each source's results are kept as a snapshot, and every night's playlists are rebuilt from all snapshots, so a
source refreshed tonight replaces exactly its own entries. If a harvest fails, the previous snapshot is used.
All requests share one per-host limiter (a few connections per host, a gap between requests, and back-off when
a server says it's busy), and the big checks go round the hosts in turn.
To refresh everything at once, run `python -m freeplaylist build --all`, or start the workflow by hand with
**full** ticked.

**Staged runs.** To fill the playlists a source at a time (for example the very first time, or after deleting
the `state` branch), start the workflow by hand with **only** set to one or more sources, e.g. `curated,internet-archive-series,internet-archive-movies`, then `wikimedia-commons` (`--only=...` locally). Each run publishes what has been harvested so far; sources not harvested yet are left
out until their stage runs.

**Publishing:** [`.github/workflows/build.yml`](.github/workflows/build.yml) builds daily at 04:17 UTC and on
manual runs (Actions tab → Build playlists → Run workflow); merges don't start a build. The build runs as
separate steps (one harvest per source, then the live and the movie checks, then the playlists),
the same as `python -m freeplaylist build --phase ...` locally, so the run's page shows how far it has got. It deploys to GitHub Pages. If a build comes out broken
(an upstream API down, too few entries), the job fails and the previous playlists stay online. To enable
it: **Settings → Pages → Source: GitHub Actions**.

Layout:

```
config/        what to include: sources, rules, allow/deny lists, feeds, credits
src/freeplaylist/
  sources/     internet_archive.py (movies, series), wikimedia_commons.py, curated.py (Blender films, live channels)
  legal.py (what may be published)  enrich.py (Wikidata ids)  languages.py  healthcheck.py  feeds.py  m3u.py
  credits.py  build.py
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
