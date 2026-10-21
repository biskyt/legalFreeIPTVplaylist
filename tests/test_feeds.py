from freeplaylist import build, config, feeds, m3u


def test_feed_deduplicates_and_orders(entry):
    entries = [
        entry(id="b", title="B", group="DE | Pluto TV", countries=["DE"], extra={"platform": "Pluto TV"}),
        entry(id="a", title="A", group="DE | News", countries=["DE"], url="https://x/a.m3u8"),
        entry(id="f", title="F", group="FR | News", countries=["FR"], url="https://x/f.m3u8"),
        entry(id="a", title="A again", countries=["DE"], url="https://x/other.m3u8"),
        entry(id="c", title="C", countries=["DE"], url="https://x/a.m3u8"),
        entry(id="m", title="Movie", kind="movie"),
    ]
    feed, decisions = feeds.build("live", {"kind": "live"}, entries)
    assert [e.id for e in feed.entries] == ["a", "b", "f"]  # by country code, broadcasters before streaming services
    assert len(decisions) == 2


def test_series_order(entry):
    eps = [entry(id=f"e{s}{n}", kind="series", series_name="Show", season=s, episode=n, title=f"Show {s}x{n}",
                 url=f"https://x/{s}{n}.mp4") for s, n in [(2, 1), (1, 2), (1, 1)]]
    feed, _ = feeds.build("series", {"kind": "series"}, eps)
    assert [(e.season, e.episode) for e in feed.entries] == [(1, 1), (1, 2), (2, 1)]


def test_combined_is_members_joined_byte_for_byte(entry):
    entries = [entry(id="l", url="https://x/l.m3u8"), entry(id="ia.m", kind="movie", url="https://x/m.mp4"),
               entry(id="ia.s", kind="series", series_name="S", episode=1, url="https://x/s.mp4")]
    cfg = config.load("feeds")
    built, _ = build.make_feeds(entries, cfg)
    for name, combined in cfg["combined"].items():
        expected = m3u.header() + "\n" + "".join(built[m].body for m in combined["members"])
        assert built[name].document() == expected
    assert [e.id for e in built["playlist"].entries] == ["l", "ia.m", "ia.s"]
    assert build.validate(built, cfg, enforce_minimums=False) == []


def test_validate_flags_small_feeds(entry):
    cfg = config.load("feeds")
    built, _ = build.make_feeds([entry()], cfg)
    problems = build.validate(built, cfg)
    assert any("movies: only 0 entries" in p for p in problems)
