# MyTVPlayer: movies and series from M3U playlists

A brief for implementing [FORMAT.md](../FORMAT.md) (the open M3U VOD convention) in
[biskyt/MyTVPlayer](https://github.com/biskyt/MyTVPlayer). It was written from a read of MyTVPlayer at commit
`8ada1b5`; check the paths against the current code.

## Goal

Movies and series in an M3U playlist should appear in MyTVPlayer's **Movies** and **Series** sections, the same
way they do for Xtream accounts, **without changing behaviour for any existing provider M3U**. Test playlist:
`https://biskyt.github.io/legalFreeIPTVplaylist/playlist.m3u`.

## Current state

- `core/.../m3u/M3uParser.kt` emits `M3uEntry(name, url, tvgId, logo, group, number, userAgent, referrer)`.
  It ignores the `#EXTINF` duration and all other attributes.
- `PlaylistRepository.syncM3u` stores every entry as a `ChannelEntity`, with categories from `group-title`.
- `VodRepository.sync` returns straight away for M3U playlists (`if (p.isM3u) return`, around line 141), so the
  Movies and Series tabs are filled only from Xtream.
- The movie and series details screens fetch Xtream's `get_vod_info` and `get_series_info`.

## Requirements

1. **Parser.** Add `type`, `durationSec`, `seriesName`, `season`, `episode` and `year` to `M3uEntry`. Read them
   from the `#EXTINF:<duration>` prefix and the `tvg-type`, `series-name`, `season`, `episode` and `year`
   attributes. Keep the hand-written attribute scan; don't add a regex on the hot path. Bad or missing numbers
   become `null`.

2. **Classification, in this order. Only explicit evidence moves an entry out of Live:**
   1. `tvg-type="movie"` makes the entry a movie. `tvg-type="series"` with a non-empty `series-name` makes it an
      episode. An unknown `tvg-type` value means live.
   2. With no `tvg-type`: an Xtream-panel URL shape, i.e. path segments `/movie/<u>/<p>/<id>.<ext>` or
      `/series/<u>/<p>/<id>.<ext>`, makes it a movie, or an episode whose series name comes from `group-title`.
      This also helps real providers' M3U exports.
   3. Everything else is live, exactly as today.

   Do **not** classify by file extension or positive duration alone (some live services publish `.mp4` loops).
   If that heuristic is wanted, add it later as an opt-in setting.

3. **Storage.**
   - Write VOD entries to the existing movie and series tables. Their categories come from `group-title`,
     stored with `CAT_MOVIE` / `CAT_SERIES` and `groupByName = true`, as live groups are now.
   - Use stable ids: `stableId(tvgId ?: url)` for a movie or episode, and `stableId(seriesName)` for a series. That way
     favourites, resume positions, hidden categories and backups survive refreshes.
   - Episodes are ordered by season, then episode, then playlist order.
   - Remove entries that disappear from the playlist, the same way stale channels are removed.
   - `VodRepository.sync` should do this for M3U playlists instead of returning early, or `syncM3u` can write
     VOD rows in the same pass. Prefer the single pass, because large playlists are streamed only once.

4. **Details and playback.**
   - For M3U VOD, build the details from the stored M3U fields: poster from `tvg-logo`, runtime from the
     duration, year, and the season/episode list from the stored rows.
   - Never call Xtream endpoints for an M3U playlist.
   - Play the entry's URL directly, honouring `http-user-agent` / `http-referrer`, as live channels do.
   - Optional TMDB enrichment, from the roadmap, can add plots and cast later.

5. **Must not regress:**
   - an M3U without the convention (e.g. iptv-org `index.country.m3u`) gives an identical channel list, the
     same ids and the same categories as before;
   - existing users' hidden channels, channel order and category choices;
   - EPG from `url-tvg` / `x-tvg-url`;
   - Xtream playlists (untouched);
   - streaming parse and memory use on playlists of 50k+ entries.

6. **Tests.**
   - `M3uParserTest`: the new attributes; missing, garbage and negative values; names with commas.
   - Classification table: `tvg-type` movie/series/live/unknown; Xtream URL shapes; and a plain `.mp4` with a
     positive duration but no `tvg-type` stays **live**.
   - Repository test: one mixed playlist fills Live, Movies and Series correctly, and a second sync keeps the ids.
   - Golden test: an iptv-org sample produces exactly the same channels before and after the change.

## Notes

- Live entries in our playlists use iptv-org ids (`Channel.cc@Feed`), and MyTVPlayer already cuts at `@` when
  matching guides.
- Our playlists set catch-up attributes (`catchup`, `catchup-days`, `catchup-source`) only when a source
  supports catch-up; today none do. Catch-up for M3U is already on MyTVPlayer's roadmap.
