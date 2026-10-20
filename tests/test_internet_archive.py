import pytest

from freeplaylist.sources import internet_archive as ia

RULES = dict(pd_max_year=1977, pre_year=1931)


@pytest.mark.parametrize("url,year,ok,reason", [
    ("http://creativecommons.org/licenses/publicdomain/", 1954, True, "pd"),
    ("http://creativecommons.org/publicdomain/mark/1.0/", 1950, True, "pd"),
    ("http://creativecommons.org/publicdomain/mark/1.0/", 1999, False, "pd-claim-too-recent"),
    ("http://creativecommons.org/publicdomain/mark/1.0/", None, False, "pd-claim-without-year"),
    ("https://creativecommons.org/licenses/by/4.0/", 2021, True, "cc-by"),
    ("http://creativecommons.org/licenses/by-sa/3.0/us/", 2010, True, "cc-by-sa"),
    ("http://creativecommons.org/licenses/by-nc/4.0/", 2010, False, "restricted-license"),
    ("https://creativecommons.org/licenses/by-nd/4.0/", 2010, False, "restricted-license"),
    (None, 1925, True, "pre-1931"),
    (None, 1944, False, "no-license"),
    (None, None, False, "no-license"),
])
def test_license_rules(url, year, ok, reason):
    assert ia.license_ok(url, year, **RULES) == (ok, reason)


def test_videos_picks_best_mp4_per_source():
    files = [
        {"name": "a.mpeg", "format": "MPEG2", "source": "original"},
        {"name": "a.mp4", "format": "h.264", "original": "a.mpeg", "length": "4533.5", "height": "480"},
        {"name": "a_512kb.mp4", "format": "512Kb MPEG4", "original": "a.mpeg", "length": "4533.4", "height": "240"},
        {"name": "b_512kb.mp4", "format": "512Kb MPEG4", "original": "b.avi", "length": "25:30"},
        {"name": "a.ogv", "format": "Ogg Video", "original": "a.mpeg"},
    ]
    assert ia.videos(files) == [
        {"name": "a.mp4", "length": 4533.5, "title": None},
        {"name": "b_512kb.mp4", "length": 1530.0, "title": None},
    ]


@pytest.mark.parametrize("text,expected", [
    ("The Andy Griffith Show: S3 E23, Andy Discovers America", (3, 23)),
    ("Steptoe and Son - 1x01 - The Bird", (1, 1)),
    ("Beverly Hillbillies Ep01 The Clampetts Strike Oil", (None, 1)),
    ("Dragnet - Episode # 18 The Big Seventeen", (None, 18)),
    ("Lucy Meets John Wayne", (None, None)),
])
def test_parse_episode(text, expected):
    assert ia.parse_episode(text) == expected


SHERLOCK = {"match": "sherlock[ _-]?holmes"}


@pytest.mark.parametrize("text,show,expected", [
    ("Beverly_Hillbillies_Ep01_The_Clampetts_Strike_Oil", {"match": "beverly[ _]hillbillies"},
     (None, 1, "The Clampetts Strike Oil")),
    ("Sherlock Holmes 02 The Case Of Lady Beryl.mp4", SHERLOCK, (None, 2, "The Case Of Lady Beryl")),
    ("SH - (23) The Christmas Pudding - 1955", {"match": "^SH\\b"}, (None, 23, "The Christmas Pudding")),
    ("( 1954) Sherlock Holmes Ep 1", SHERLOCK, (None, 1, "")),
    ("Sherlock Holmes 1955 S01E27 The Case of the Perfect Husband (1955-05-20 Color,MysSusp).mp4", SHERLOCK,
     (1, 27, "The Case of the Perfect Husband")),
    ("Bonanza s01e19.mp4", {"match": "bonanza"}, (1, 19, "")),
    ("s01e01.The.Speckled.Band.mp4", SHERLOCK, (1, 1, "The Speckled Band")),
    ("S04.mp4", SHERLOCK, (None, None, "")),
])
def test_episode_info(text, show, expected):
    assert ia.episode_info(text, show) == expected


def test_movie_title_moves_trailing_article():
    assert ia._movie_title("Monster Walks, The", 1932) == "The Monster Walks (1932)"
    assert ia._movie_title("Blonde Ice (1948)", 1948) == "Blonde Ice (1948)"


def _fake_ia(monkeypatch, listing, metadata):
    monkeypatch.setattr(ia, "search", lambda query, limit, **kw: listing)
    monkeypatch.setattr(ia.net, "get_json", lambda url, **kw: metadata[url.rsplit("/", 1)[1]])


def _meta(title, year, licenseurl, length):
    return {"metadata": {"title": title, "year": str(year), "licenseurl": licenseurl, "description": "<b>A</b> film"},
            "files": [{"name": f"{title}.mp4", "format": "h.264", "length": str(length)}]}


def test_movies_rechecks_metadata_and_groups_shorts(monkeypatch):
    pd = "http://creativecommons.org/publicdomain/mark/1.0/"
    listing = [
        {"identifier": "good", "year": 1950, "licenseurl": pd},
        {"identifier": "short", "year": 1950, "licenseurl": pd},
        {"identifier": "liar", "year": 1950, "licenseurl": pd},  # item page says otherwise
        {"identifier": "modern", "year": 1999, "licenseurl": pd},
        {"identifier": "banned", "year": 1950, "licenseurl": pd},
    ]
    metadata = {
        "good": _meta("Good (1950)", 1950, pd, 5400),
        "short": _meta("Short", 1950, pd, 600),
        "liar": _meta("Liar", 1950, "https://creativecommons.org/licenses/by-nc/4.0/", 5400),
    }
    _fake_ia(monkeypatch, listing, metadata)
    cfg = {"collections": [{"collection": "Film_Noir", "group": "Movies: Noir"}]}
    entries, decisions = ia.movies(cfg, ia.MetadataCache({}), {"banned"})
    by_id = {e.id: e for e in entries}
    assert set(by_id) == {"ia.good", "ia.short"}
    good = by_id["ia.good"]
    assert (good.title, good.duration, good.group, good.kind) == ("Good (1950)", 5400, "Movies: Noir", "movie")
    assert good.url == "https://archive.org/download/good/Good%20%281950%29.mp4"
    assert good.description == "A film"
    assert by_id["ia.short"].group == "Movies: Shorts"
    reasons = {d.item: d.reason for d in decisions}
    assert reasons["liar"] == "metadata:restricted-license"
    assert reasons["modern"] == "pd-claim-too-recent"
    assert reasons["banned"] == "denylist"


def test_series_only_listed_show_with_free_licence(monkeypatch):
    pd = "http://creativecommons.org/publicdomain/mark/1.0/"
    listing = [{"identifier": "Beverly_Hillbillies_Ep02_Getting_Settled"}, {"identifier": "Other_Show"},
               {"identifier": "Beverly_Hillbillies_Ep03_Unlicensed"}]
    metadata = {
        "Beverly_Hillbillies_Ep02_Getting_Settled": _meta("Beverly Hillbillies Ep02 Getting Settled", 1962, pd, 1500),
        "Other_Show": _meta("Other Show", 1962, pd, 1500),
        "Beverly_Hillbillies_Ep03_Unlicensed": _meta("Beverly Hillbillies Ep03 Unlicensed", 1962, None, 1500),
    }
    _fake_ia(monkeypatch, listing, metadata)
    show = {"name": "The Beverly Hillbillies", "query": "q", "match": "beverly[ _]hillbillies", "max_year": 1971}
    entries, _ = ia.series({"shows": [show]}, ia.MetadataCache({}), set())
    assert len(entries) == 1
    e = entries[0]
    assert (e.kind, e.series_name, e.season, e.episode) == ("series", "The Beverly Hillbillies", 1, 2)
    assert e.title == "The Beverly Hillbillies S01E02 - Getting Settled"
    assert e.group == "Series: The Beverly Hillbillies"


def test_cache_reuses_fresh_records(monkeypatch):
    calls = []
    monkeypatch.setattr(ia.net, "get_json", lambda url, **kw: calls.append(url) or _meta("A", 1950, None, 60))
    cache = ia.MetadataCache({})
    cache.get_many(["a"])
    cache.get_many(["a"])
    assert len(calls) == 1
