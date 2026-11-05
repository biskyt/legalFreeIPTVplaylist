import pytest

from freeplaylist import config, feeds, languages, m3u
from freeplaylist.sources import curated, internet_archive


@pytest.mark.parametrize("value,code", [
    ("eng", "eng"), ("English", "eng"), ("en", "eng"), ("fre", "fra"), ("French language", "fra"),
    ("Silent", "zxx"), ("Klingon", None), ("", None), (None, None),
])
def test_normalise(value, code):
    assert languages.normalise(value) == code


def test_normalise_all_splits_and_dedupes():
    assert languages.normalise_all(["English; French", "eng", "xx"]) == ["eng", "fra"]


def test_attributes_written(entry):
    line = m3u.render_entry(entry(languages=["eng", "spa"], countries=["US", "MX"])).split("\n")[0]
    assert 'tvg-country="US;MX" tvg-language="English;Spanish"' in line
    assert "tvg-language" not in m3u.render_entry(entry()).split("\n")[0]


def test_the_vendored_name_lists_cover_what_we_use():
    languages.load(config.load("languages")["languages"])
    languages.load_countries(config.load("countries")["countries"])
    assert languages.name("fas") == "Persian" and languages.name("quc") != "quc"  # a rare language too
    assert languages.normalise("Persian") == "fas" and languages.normalise("Welsh") == "cym"
    assert languages.country("the United States") == "US" and languages.country("United Kingdom") == "GB"
    assert languages.country_code("UK") == "GB" and languages.country("Atlantis") is None


def test_live_channels_are_curated_with_languages_and_countries():
    languages.load(config.load("languages")["languages"])
    entries, _ = curated.build({"direct": config.load("curated")["direct"]}, internet_archive.MetadataCache({}))
    by_id = {e.id: e for e in entries}
    assert by_id["VoATVPersian.us@SD"].languages == ["fas"] and by_id["VoATVPersian.us@SD"].countries == ["IR"]
    assert by_id["VoATVChina.cn@SD"].languages == ["zho"] and by_id["VoATVChina.cn@SD"].countries == ["CN"]
    assert by_id["DistrictofColumbiaNetwork.us@SD"].languages == ["eng"]
    assert all(e.kind == "live" and e.page and e.logo.startswith("https://") for e in entries)


def _feed(name, kind, items, entry):
    es = [entry(id=f"{name}{i}", kind=kind, url=f"https://x/{name}{i}", languages=langs) for i, langs in
          enumerate(items)]
    return feeds.Feed(name, name, es, [m3u.render_entry(e) for e in es])


def test_language_feeds_reuse_rendered_lines(entry):
    built = {
        "live": _feed("live", "live", [["eng"], ["fra"], ["eng", "fra"], ["deu"]], entry),
        "movies": _feed("movies", "movie", [["eng"], ["zxx"]], entry),
        "series": _feed("series", "series", [], entry),
    }
    out = feeds.by_language(built, ["live", "movies", "series"], min_entries=2)
    assert set(out) == {"languages/eng", "languages/fra"}  # German has only one entry
    eng = out["languages/eng"]
    assert [e.id for e in eng.entries] == ["live0", "live2", "movies0", "movies1"]  # silent film joins every language
    assert eng.lines[0] is built["live"].lines[0]  # joined, not rendered again
    assert [e.id for e in out["languages/fra"].entries] == ["live1", "live2", "movies1"]
