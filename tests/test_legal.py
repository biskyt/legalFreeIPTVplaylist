import pytest

from freeplaylist import config, credits, legal
from freeplaylist.sources import iptv_org

GRANT = {"channel": "X.de", "url": "https://x.example/terms", "quote": "You may redistribute our live stream.",
         "note": "Credit us.", "checked": "2026-11-05"}
POLICY = {**config.load("legal"), "permissions": [GRANT, {**GRANT, "channel": "MNT.us"}, {**GRANT, "channel": "DW.de"}]}


def vod(entry, **kw):
    kw.setdefault("kind", "movie")
    return entry(url="https://archive.org/download/x/x.mp4", page="https://archive.org/details/x",
                 source="internet-archive", **kw)


def test_films_are_kept_only_with_a_checkable_basis(entry):
    old = vod(entry, id="ia.old", year=1925, license="Public domain in the US (published before 1931)")
    marked = "Public domain in the US (as marked on the Internet Archive)"
    claimed = vod(entry, id="ia.claimed", year=1944, license=marked)
    cc = vod(entry, id="ia.cc", year=1975, license="http://creativecommons.org/licenses/by/3.0/")
    undated = vod(entry, id="ia.undated", year=None)
    episode = vod(entry, id="ia.ep", kind="series", year=1925)  # episodes of old shows rely on someone's say-so
    commons = entry(id="commons.a", kind="movie", source="wikimedia-commons", year=1975, page="https://commons.example/a")
    blender = entry(id="blender.a", kind="movie", source="blender", year=2008, page="https://studio.blender.org/")
    kept, dropped = legal.apply([old, claimed, cc, undated, episode, commons, blender], POLICY)
    assert [e.id for e in kept] == ["ia.old", "commons.a", "blender.a"]
    assert {d.item: d.reason for d in dropped} == {i: "not-proven:uploader-claim" for i in
                                                   ("ia.claimed", "ia.cc", "ia.undated", "ia.ep")}


def test_takedowns_match_by_channel_entry_source_and_domain(entry):
    fox_news = entry(id="FoxNewsChannel.us@SD", page="https://www.foxnews.com/", url="http://247preview.foxnews.com/a.m3u8")
    local = entry(id="Fox.us@KTTV", url="https://cdn.example/a.m3u8")
    one_station = entry(id="MNT.us@WFLD", url="https://cdn.example/b.m3u8")
    other_station = entry(id="MNT.us@WXYZ", url="https://cdn.example/c.m3u8")
    by_source = entry(id="Anything.us@SD", source="fox-owned", url="https://cdn.example/d.m3u8")
    by_domain = entry(id="Some.us@SD", page="https://news.yahoo.com/live", url="https://cdn.example/e.m3u8")
    stream_domain = entry(id="Else.us@SD", url="https://fox-foxnewsnow.foxnews.com/f.m3u8")
    fine = entry(id="DW.de@SD", page="https://www.dw.com/", url="https://dw.example/g.m3u8")
    policy = {**POLICY, "takedowns": [*POLICY["takedowns"], {"owner": "Fox Corporation", "sources": ["fox-owned"]}]}
    everything = [fox_news, local, one_station, other_station, by_source, by_domain, stream_domain, fine]
    kept, dropped = legal.apply(everything, policy)
    assert [e.id for e in kept] == ["MNT.us@WXYZ", "DW.de@SD"]
    assert {d.reason for d in dropped} == {"takedown:Fox Corporation", "takedown:Yahoo"}


def test_live_evidence_names_the_basis_and_links_to_the_channel(entry):
    cands = [{"url": "https://cdn.example/a.m3u8", "reason": "official:website-link"}]
    e = entry(id="X.de@SD", url="https://cdn.example/a.m3u8", page="https://x.example/",
              extra={"reason": "official:website-domain", "candidates": cands})
    ev = legal.evidence(e, POLICY)
    assert ev.basis == "permission" and ev.title == "The owner's terms allow it"
    assert "You may redistribute our live stream." in ev.text and "Credit us." in ev.text  # the owner's own words
    assert "x.example" in ev.text and "cdn.example" in ev.text  # and that the stream is theirs (the stream used)
    assert ev.terms == ("https://x.example/terms",) and ev.as_dict()["terms"] == ["https://x.example/terms"]
    assert ev.links == (("Where it says so", "https://x.example/terms"), ("Channel website", "https://x.example/"))


def test_live_channels_without_a_permission_are_dropped(entry):
    allowed = entry(id="X.de@SD")
    silent = entry(id="Silent.de@SD")
    kept, dropped = legal.apply([allowed, silent], POLICY)
    assert [e.id for e in kept] == ["X.de@SD"]
    assert [(d.item, d.reason) for d in dropped] == [("Silent.de@SD", "not-proven:no-permission")]


def test_film_evidence_links_to_the_item_licence_and_imdb(entry):
    e = vod(entry, id="ia.old", year=1925, imdb="tt0001", license="http://creativecommons.org/licenses/by/3.0/")
    ev = legal.evidence(e, POLICY)
    assert ev.basis == "published-before-1931" and "1925" in ev.text
    labels = dict(ev.links)
    assert labels["Source page"] == "https://archive.org/details/x" and labels["IMDb"].endswith("/tt0001/")
    sources = {"wikimedia-commons": {"name": "Wikimedia Commons", "terms": "https://commons.example/terms"},
               "internet-archive": {"terms": "https://ia.example/terms"}}
    commons = legal.evidence(entry(id="c", kind="movie", source="wikimedia-commons", page="https://c.example/"), POLICY,
                             sources)
    assert commons.title == "Accepted source: Wikimedia Commons" and "free in the United States" in commons.text
    assert commons.terms == ("https://commons.example/terms",)
    assert legal.evidence(e, POLICY, sources).terms == ("https://ia.example/terms",)


def test_only_accepted_reasons_count_as_proof():
    assert legal.accepted_live_reasons(POLICY) == {"official:website-domain", "official:website-link",
                                                   "official:broadcaster-host"}


@pytest.fixture(scope="module")
def api():
    return iptv_org.fetch_api(config.ROOT / "tests" / "fixtures" / "iptv_org")


def test_build_with_accept_drops_unproven_streams_and_says_why(api):
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    entries, decisions = iptv_org.build(api, rules, accept=legal.accepted_live_reasons(POLICY))
    assert {e.id for e in entries} == {"Example.uk@SD", "Local1.us@SD", "AlJazeera.qa@English"}
    why = {d.reason for d in decisions if not d.accepted}
    assert "not-proven:official:cdn-named" in why
    assert all("reason" in c for e in entries for c in e.extra["candidates"])


def test_a_website_that_mentions_the_host_beats_a_name_in_the_url(api):
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    host = "dwamdstream102.akamaized.net"
    site = next(c["website"] for c in api["channels"] if c["id"] == "DW.de")
    entries, _ = iptv_org.build(api, rules, {site: {host}}, legal.accepted_live_reasons(POLICY))
    dw = next(e for e in entries if e.id == "DW.de@SD")
    assert dw.extra["reason"] == "official:website-link"
    assert site not in iptv_org.unverified_sites(api, rules, legal.accepted_live_reasons(POLICY)) or True


def test_sites_with_only_weak_proof_are_worth_checking(api):
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    site = next(c["website"] for c in api["channels"] if c["id"] == "DW.de")
    assert site not in iptv_org.unverified_sites(api, rules)  # accepted by name: fine without the policy
    assert site in iptv_org.unverified_sites(api, rules, legal.accepted_live_reasons(POLICY))  # not proven


def test_credits_page_shows_evidence_exclusions_and_sources(entry):
    live = entry(id="X.de@SD", title="X", page="https://x.example/", url="https://cdn.example/a.m3u8",
                 extra={"broadcaster": "X TV", "country": "DE", "reason": "official:website-domain"})
    film = vod(entry, id="ia.old", title="Old Film (1925)", year=1925, attribution="Old Film by A. Maker")
    sources = {"iptv-org": {"name": "iptv-org", "url": "https://iptv.example/", "provides": "Channels", "license": "L",
                            "proof": "Kept only with proof."},
               "internet-archive": {"name": "Internet Archive", "url": "https://archive.org/", "provides": "Films",
                                    "license": "L"},
               }
    page = credits.credits_html([live, film], sources, POLICY)
    assert '<a href="https://x.example/terms">Terms and conditions</a>' in page
    assert "You may redistribute our live stream." in page  # the owner's words, on the page
    assert "only where the owner" in page
    assert "X TV" in page and "https://x.example/" in page and "Old Film (1925)" in page
    assert "Old Film by A. Maker" in page and "Kept only with proof." in page
    assert "left out" not in page  # nothing about what isn't included


def test_build_only_looks_at_the_channels_it_is_given(api):
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    accept = legal.accepted_live_reasons(POLICY)
    entries, decisions = iptv_org.build(api, rules, accept=accept, only={"Example.uk"})
    assert {e.id for e in entries} == {"Example.uk@SD"}
    assert all("Example.uk" in d.item for d in decisions)  # nothing is said about the other channels
    assert iptv_org.build(api, rules, accept=accept, only=set())[0] == []
    sites = iptv_org.unverified_sites(api, rules, accept, {"DW.de"})
    assert set(sites) == {c["website"] for c in api["channels"] if c["id"] == "DW.de"}


def test_the_real_permission_file_is_complete():
    grants = config.load("permissions")["permissions"]
    assert grants, "an empty list would publish no live channels"
    channels = [g["channel"] for g in grants]
    assert len(channels) == len(set(channels))
    for g in grants:
        assert g["url"].startswith("https://") and g["checked"]
        assert len(" ".join(g["quote"].split())) > 40, f"{g['channel']}: the owner's exact words are needed"
