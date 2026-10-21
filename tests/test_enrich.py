from freeplaylist import build, enrich


def test_apply_matches_by_source_item(entry):
    ia = entry(kind="movie", page="https://archive.org/details/night_of_the_living_dead", logo="frame.jpg")
    commons = entry(kind="movie", page="https://commons.wikimedia.org/wiki/File:The_Kid_(1921).webm")
    other = entry(kind="movie", page="https://archive.org/details/unknown")
    tables = {
        "ia": {"night_of_the_living_dead": {"tmdb": "10331", "imdb": "tt0063350",
                                            "poster": "http://commons.wikimedia.org/wiki/Special:FilePath/P.jpg"}},
        "commons": {"The_Kid_(1921).webm": {"tmdb": "10098"}},
    }
    assert enrich.apply([ia, commons, other], tables) == 2
    assert (ia.tmdb, ia.imdb) == ("10331", "tt0063350")
    assert ia.logo == "https://commons.wikimedia.org/wiki/Special:FilePath/P.jpg?width=500"
    assert commons.tmdb == "10098" and other.tmdb is None


def test_cached_tables_used_when_wikidata_fails(monkeypatch):
    def fail(q):
        raise OSError("down")
    monkeypatch.setattr(enrich, "_query", fail)
    state = {"ia": {"t": 0, "rows": {"x": {"tmdb": "1"}}}}
    assert enrich.load(state)["ia"] == {"x": {"tmdb": "1"}}


def test_title_year_dedupe(entry):
    commons = entry(id="commons.Kid", kind="movie", title="The Kid (1921)", year=1921, url="https://c/kid.webm")
    ia = entry(id="ia.kid", kind="movie", title="The Kid (1921)", year=1921, url="https://ia/kid.mp4")
    remake = entry(id="ia.kid2", kind="movie", title="The Kid (1950)", year=1950, url="https://ia/kid2.mp4")
    kept, dropped = build._dedupe([commons, ia, remake])
    assert [e.id for e in kept] == ["commons.Kid", "ia.kid2"]
