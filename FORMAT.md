# M3U VOD convention (version 1)

This is a small, open convention for publishing **movies and TV series in an ordinary extended M3U playlist**,
so that IPTV apps can put them in Movies and Series sections instead of listing them as channels.
Anyone may use or implement it. This document is dedicated to the public domain
([CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)).

It adds a few attributes and introduces no new syntax. An app that doesn't know the convention still reads
the playlist as usual, and plays every entry; it just shows films and episodes as channels in groups such as
`Movies: Noir` or `Series: Bonanza`.

## Example

```
#EXTM3U
#EXTINF:-1 tvg-id="DW.de@SD" tvg-name="DW" group-title="Live: News",DW
https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8
#EXTINF:4020 tvg-type="movie" tvg-id="ia.Detour" tvg-name="Detour (1945)" tvg-logo="https://archive.org/services/img/Detour" year="1945" group-title="Movies: Noir",Detour (1945)
https://archive.org/download/Detour/Detour.mp4
#EXTINF:1530 tvg-type="series" series-name="The Beverly Hillbillies" season="1" episode="2" tvg-id="ia.Beverly_Hillbillies_Ep02_Getting_Settled" tvg-name="The Beverly Hillbillies S01E02 - Getting Settled" tvg-logo="https://archive.org/services/img/Beverly_Hillbillies_Ep02_Getting_Settled" group-title="Series: The Beverly Hillbillies",The Beverly Hillbillies S01E02 - Getting Settled
https://archive.org/download/Beverly_Hillbillies_Ep02_Getting_Settled/Beverly_Hillbillies_Ep02_Getting_Settled.mp4
```

## Attributes

| Attribute | Values | Meaning |
|---|---|---|
| `tvg-type` | `live`, `movie`, `series` | The entry's content type. **Missing means `live`.** `series` marks one episode of a series. Unknown values must be treated as `live`. |
| `series-name` | text | The series an episode belongs to. Required when `tvg-type="series"`; episodes with the same `series-name` form one series. |
| `season` | integer ≥ 1 | Season number. Missing means season 1 when `episode` is given. |
| `episode` | integer ≥ 1 | Episode number within the season. Optional; episodes without numbers keep playlist order. |
| `year` | 4-digit integer | Release or first-broadcast year. Optional. |
| `#EXTINF` duration | `-1`, or positive whole seconds | The standard M3U meaning: `-1` for live streams or unknown length, otherwise the running time. |

The usual attributes keep their usual meaning:
- `tvg-id`: a stable id;
- `tvg-name`: the full title, e.g. `Show S01E02 - Title` for an episode;
- `tvg-logo`: the poster or thumbnail;
- `group-title`: the category. For movies this is the genre; for episodes, conventionally `Series: <series-name>`.

The `catchup`, `catchup-days` and `catchup-source` attributes are the existing de facto catch-up convention
(Kodi IPTV Simple, TiviMate and others), not part of this one. They appear on live entries only, and only when
the source supports catch-up.

## Rules for publishers

These keep playlists readable by every parser, including simple ones:

1. UTF-8 without a byte-order mark, LF line endings, and `#EXTM3U` as the first line.
2. Each entry is one `#EXTINF` line followed by its URL line. The only lines in between are optional
   `#EXTVLCOPT:http-user-agent=` and `#EXTVLCOPT:http-referrer=` lines.
3. Attributes are `key="value"`, always double-quoted. Values contain no `"`, no comma and no line break.
4. The display name after the comma contains no comma and no line break. That way parsers that split on the
   first comma and parsers that split on the last comma read the same name.
5. VOD URLs point directly at a playable file or stream: no redirects that need special handling, and no
   nested playlists.
6. Give every entry a `group-title`, so apps without support still show something sensible.

## Rules for apps

1. Classify only on explicit evidence, so that existing playlists keep working exactly as before:
   1. `tvg-type="movie"` makes the entry a movie. `tvg-type="series"` with a `series-name` makes it an episode.
   2. Optionally, recognise Xtream-panel M3U exports by their URL shape: `/movie/<user>/<pass>/<id>.<ext>`
      and `/series/<user>/<pass>/<id>.<ext>`.
   3. Everything else is live, as before.
2. Don't treat a file extension or a positive duration alone as proof of VOD. Some live services publish
   `.mp4` loops or durations.
3. Ignore attributes you don't know.

## Versioning

New optional attributes may be added in later versions. Existing ones won't change meaning.
