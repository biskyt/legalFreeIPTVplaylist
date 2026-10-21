import json
from pathlib import Path

from freeplaylist import build, m3u
from freeplaylist.sources import internet_archive as ia

FIXTURES = Path(__file__).parent / "fixtures" / "iptv_org"
PD = "http://creativecommons.org/publicdomain/mark/1.0/"


def fake_archive(monkeypatch):
    listing = {"Film_Noir": [{"identifier": "Detour", "year": 1945, "licenseurl": PD}]}

    def search(query, limit, **kw):
        for name, items in listing.items():
            if name in query:
                return items
        return []

    def metadata(url, **kw):
        ident = url.rsplit("/", 1)[1]
        return {"metadata": {"title": ident, "year": "1945" if ident == "Detour" else "2008", "licenseurl": PD},
                "files": [{"name": f"{ident}.mp4", "format": "h.264", "length": "4020"}]}

    monkeypatch.setattr(ia, "search", search)
    monkeypatch.setattr(ia.net, "get_json", metadata)


def test_offline_build_writes_site(tmp_path, monkeypatch):
    fake_archive(monkeypatch)
    out = tmp_path / "site"
    opts = build.Options(out=out, state_dir=tmp_path / "state", api_dir=FIXTURES, health=False,
                         website_check=False, extra_vod=False, enrich=False, enforce_minimums=False)
    result = build.run(opts)

    names = {p.name for p in out.iterdir()}
    assert {"live.m3u", "movies.m3u", "series.m3u", "vod.m3u", "playlist.m3u", "catalog.json", "report.json",
            "credits.html", "index.html"} <= names

    _, live = m3u.parse((out / "live.m3u").read_text())
    assert {e["tvg-id"] for e in live} == {"DW.de@SD", "Example.uk@SD", "Pluto1.us@SD", "AlJazeera.qa@English",
                                           "Euronews.fr@Polish", "Telesur.ve@SD", "Xumo1.us@SD"}
    _, movies = m3u.parse((out / "movies.m3u").read_text())
    ids = {e["tvg-id"] for e in movies}
    assert "ia.Detour" in ids and "blender.BigBuckBunny_124" in ids
    assert all(e["tvg-type"] == "movie" for e in movies)

    playlist = (out / "playlist.m3u").read_text()
    head, _, body = playlist.partition("\n")
    assert head == '#EXTM3U url-tvg="https://biskyt.github.io/legalFreeIPTVplaylist/epg.xml.gz"'
    assert body == "".join(result.feeds[n].body for n in ("live", "movies", "series"))
    assert (out / "movies.m3u").read_text().startswith("#EXTM3U\n")  # no guide header without live channels
    plan = json.loads((tmp_path / "state" / "epg" / "plan.json").read_text())
    mjh = "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/de/epg.xml"
    assert plan["mjh"][mjh] == {"dw": ["DW.de@SD"]}
    assert (tmp_path / "state" / "epg" / "channels.xml").exists()

    catalog = json.loads((out / "catalog.json").read_text())
    blender = next(i for i in catalog["items"] if i["id"] == "blender.BigBuckBunny_124")
    assert blender["license"] == "CC BY 3.0" and "Blender Foundation" in blender["attribution"]
    assert "DW" in (out / "credits.html").read_text()
    assert (tmp_path / "state" / "ia_cache.json").exists()
    _, english = m3u.parse((out / "languages" / "eng.m3u").read_text())
    assert "DW.de@SD" in {e["tvg-id"] for e in english}
    assert 'tvg-language="English"' in (out / "live.m3u").read_text()


def test_dedupe_prefers_earlier_source(entry):
    curated = entry(id="blender.BBB", kind="movie", url="https://archive.org/download/BBB/bbb.mp4", source="blender")
    again = entry(id="ia.BBB", kind="movie", url="https://archive.org/download/BBB/bbb.mp4")
    kept, dropped = build._dedupe([curated, again])
    assert kept == [curated] and dropped[0].item == "ia.BBB"
