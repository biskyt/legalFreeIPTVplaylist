from pathlib import Path

import pytest

from freeplaylist import config, feeds, languages, m3u
from freeplaylist.sources import iptv_org

FIXTURES = Path(__file__).parent / "fixtures" / "iptv_org"


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


def test_live_languages_and_countries():
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    entries, _ = iptv_org.build(iptv_org.fetch_api(FIXTURES), rules)
    by_id = {e.id: e for e in entries}
    assert by_id["Example.uk@SD"].countries == ["GB"]  # iptv-org's UK is ISO GB
    assert by_id["Pluto1.us@SD"].countries == ["US"]  # s/US-CA counts as the US, once
    assert by_id["DW.de@SD"].countries == ["DE"]  # regions only: falls back to the channel's country
    assert by_id["Euronews.fr@Polish"].languages == ["pol"]


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
