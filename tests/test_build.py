import json
from pathlib import Path

from freeplaylist import build, healthcheck, m3u
from freeplaylist.sources import internet_archive as ia

FIXTURES = Path(__file__).parent / "fixtures" / "iptv_org"
PD = "http://creativecommons.org/publicdomain/mark/1.0/"


def fake_archive(monkeypatch):
    # A 1925 film (public domain by age) and a 1944 one that only an uploader says is public domain.
    listing = {"Film_Noir": [{"identifier": "Detour", "year": 1925, "licenseurl": PD},
                             {"identifier": "Laura", "year": 1944, "licenseurl": PD}]}

    def search(query, limit, **kw):
        for name, items in listing.items():
            if name in query:
                return items
        return []

    def metadata(url, **kw):
        ident = url.rsplit("/", 1)[1]
        year = {"Detour": "1925", "Laura": "1944"}.get(ident, "2008")
        return {"metadata": {"title": ident, "year": year, "licenseurl": PD},
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
    # Only streams with a provable basis: the channel's own website domain, or a broadcaster-run host. The
    # fixture's free streaming services and CDN-name matches (DW, Euronews, teleSUR) are left out.
    assert {e["tvg-id"] for e in live} == {"Example.uk@SD", "AlJazeera.qa@English"}
    _, movies = m3u.parse((out / "movies.m3u").read_text())
    ids = {e["tvg-id"] for e in movies}
    assert "ia.Detour" in ids and "blender.BigBuckBunny_124" in ids
    assert "ia.Laura" not in ids  # 1944 and only the uploader's word: not provable
    assert all(e["tvg-type"] == "movie" for e in movies)

    playlist = (out / "playlist.m3u").read_text()
    head, _, body = playlist.partition("\n")
    assert head == '#EXTM3U url-tvg="https://biskyt.github.io/legalFreeIPTVplaylist/epg.xml.gz"'
    assert body == "".join(result.feeds[n].body for n in ("live", "movies", "series"))
    assert (out / "movies.m3u").read_text().startswith("#EXTM3U\n")  # no guide header without live channels
    plan = json.loads((tmp_path / "state" / "epg" / "plan.json").read_text())
    assert plan["iptv_epg"]["gb"] == {"Example.uk": ["Example.uk@SD"]} and "de" not in plan["iptv_epg"]
    assert (tmp_path / "state" / "epg" / "channels.xml").exists()

    catalog = json.loads((out / "catalog.json").read_text())
    blender = next(i for i in catalog["items"] if i["id"] == "blender.BigBuckBunny_124")
    assert blender["license"] == "CC BY 3.0" and "Blender Foundation" in blender["attribution"]
    example = next(i for i in catalog["items"] if i["id"] == "Example.uk@SD")
    assert example["legal"]["basis"] == "official:website-domain" and example["legal"]["links"]
    credits_page = (out / "credits.html").read_text()
    assert "Example" in credits_page and "ia.Detour" not in credits_page and "Published in 1925" in credits_page
    assert "who uploaded them" in credits_page and "(1 left out)" in credits_page  # what's left out, and why
    reasons = {d for d in json.loads((out / "report.json").read_text())["decisions"]["legal"]}
    assert "rejected:not-proven:uploader-claim" in reasons
    index = (out / "index.html").read_text()
    assert 'href="epg.xml.gz"' in index and '<a href="https://iptv-epg.org/">IPTV-EPG.org</a>' in index
    assert (tmp_path / "state" / "ia_cache.json").exists()
    assert 'tvg-language="English"' in (out / "live.m3u").read_text()


def test_phased_build_matches_a_single_build(tmp_path, monkeypatch):
    fake_archive(monkeypatch)
    checked = []

    def check(self, url, *a, **kw):
        checked.append(url)
        return healthcheck.Result("ok")

    monkeypatch.setattr(healthcheck.Checker, "check", check)

    def run(name, **kw):
        return build.run(build.Options(out=tmp_path / name, state_dir=tmp_path / f"state-{name}", api_dir=FIXTURES,
                                       website_check=False, extra_vod=False, enrich=False, enforce_minimums=False,
                                       **kw))

    whole = run("whole")
    one_go = len(checked)
    for source in build.SOURCES:
        run("parts", phase="harvest", source=source)
    assert not checked[one_go:]  # harvesting checks nothing
    run("parts", phase="check-live")
    run("parts", phase="check-vod")
    assert len(checked) == 2 * one_go
    parts = run("parts", phase="publish")
    assert len(checked) == 2 * one_go  # publishing uses the checks already made
    assert {n: f.body for n, f in parts.feeds.items()} == {n: f.body for n, f in whole.feeds.items()}


def test_dedupe_prefers_earlier_source(entry):
    curated = entry(id="blender.BBB", kind="movie", url="https://archive.org/download/BBB/bbb.mp4", source="blender")
    again = entry(id="ia.BBB", kind="movie", url="https://archive.org/download/BBB/bbb.mp4")
    kept, dropped = build._dedupe([curated, again])
    assert kept == [curated] and dropped[0].item == "ia.BBB"


def test_wikimedia_files_tell_players_to_identify(entry):
    from freeplaylist import net

    film = entry(id="commons.x", kind="movie", url="https://upload.wikimedia.org/wikipedia/commons/a/ab/X.webm")
    other = entry(id="ia.y", kind="movie", url="https://archive.org/download/y/y.mp4")
    build._identify([film, other])
    assert film.user_agent == net.USER_AGENT and other.user_agent is None
    line = m3u.render_entry(film)
    assert f'http-user-agent="{net.USER_AGENT}"' in line and f"#EXTVLCOPT:http-user-agent={net.USER_AGENT}" in line
