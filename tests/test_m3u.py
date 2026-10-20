import re

from freeplaylist import m3u


def naive_first_comma(line: str) -> str:
    return line.split(",", 1)[1]


def naive_last_comma(line: str) -> str:
    return line.rsplit(",", 1)[1]


def test_live_entry_has_no_vod_attributes(entry):
    text = m3u.render_entry(entry(id="DW.de@SD", title="DW English"))
    first, url = text.rstrip("\n").split("\n")
    assert first == '#EXTINF:-1 tvg-id="DW.de@SD" tvg-name="DW English" group-title="Live: News",DW English'
    assert url == "https://example.org/a.m3u8"


def test_movie_entry(entry):
    e = entry(id="ia.detour", title="Detour (1945)", kind="movie", group="Movies: Noir", duration=4020.4,
              year=1945, logo="https://archive.org/services/img/detour", url="https://archive.org/download/d/d.mp4")
    first = m3u.render_entry(e).split("\n")[0]  # durations are written as whole seconds
    assert first.startswith('#EXTINF:4020 tvg-type="movie" tvg-id="ia.detour"')
    assert 'year="1945"' in first and first.endswith(",Detour (1945)")


def test_series_entry(entry):
    e = entry(kind="series", series_name="Bonanza", season=1, episode=3, title="Bonanza S01E03 - The Newcomers",
              group="Series: Bonanza", duration=3000)
    first = m3u.render_entry(e).split("\n")[0]
    assert 'tvg-type="series" series-name="Bonanza" season="1" episode="3"' in first


def test_names_and_attributes_survive_naive_parsers(entry):
    e = entry(title='Lucy, Desi & "Friends"\nnext line', group='News, "Live"', logo="https://x/y.png?a=1,2")
    first = m3u.render_entry(e).split("\n")[0]
    assert "\n" not in first
    assert naive_first_comma(first) == naive_last_comma(first) == "Lucy – Desi & \"Friends\" next line"
    for value in re.findall(r'="([^"]*)"', first):
        assert "," not in value


def test_catchup_written_only_when_given(entry):
    plain = m3u.render_entry(entry())
    assert "catchup" not in plain
    with_catchup = m3u.render_entry(entry(catchup="append", catchup_days=2, catchup_source="?utc={utc},x"))
    assert 'catchup="append" catchup-days="2" catchup-source="?utc={utc}%2Cx"' in with_catchup


def test_headers_also_written_as_vlc_options(entry):
    lines = m3u.render_entry(entry(user_agent="UA/1", referrer="https://ref/")).rstrip("\n").split("\n")
    assert lines[1:] == ["#EXTVLCOPT:http-user-agent=UA/1", "#EXTVLCOPT:http-referrer=https://ref/",
                         "https://example.org/a.m3u8"]
    assert 'http-user-agent="UA/1"' in lines[0]


def test_document_round_trip(entry):
    entries = [entry(id=f"c{i}", title=f"Channel {i}") for i in range(3)]
    doc = m3u.document(m3u.header(), m3u.render_body(entries))
    assert doc.startswith("#EXTM3U\n") and "\r" not in doc and not doc.startswith("﻿")
    head, parsed = m3u.parse(doc)
    assert head == {}
    assert [p["tvg-id"] for p in parsed] == ["c0", "c1", "c2"]
    assert all(p["duration"] == -1 for p in parsed)


def test_header_guides():
    assert m3u.header(["https://a/epg.xml.gz"]) == '#EXTM3U url-tvg="https://a/epg.xml.gz"'
    assert m3u.header([]) == "#EXTM3U"
