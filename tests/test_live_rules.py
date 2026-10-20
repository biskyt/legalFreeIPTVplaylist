from pathlib import Path

import pytest

from freeplaylist import config
from freeplaylist.sources import iptv_org

FIXTURES = Path(__file__).parent / "fixtures" / "iptv_org"


@pytest.fixture(scope="module")
def built():
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    return iptv_org.build(iptv_org.fetch_api(FIXTURES), rules)


def reasons(decisions):
    return {d.item.split(" ", 1)[1]: d.reason for d in decisions}


def test_rejections(built):
    r = reasons(built[1])
    assert r["http://170.83.16.50/DW/index.m3u8"] == "ip-host"
    assert r["https://cdn-7.pishow.tv/live/431/master.m3u8"] == "unverified"
    assert r["https://adult.example/live.m3u8"] == "nsfw"
    assert r["https://old.example/live.m3u8"] == "closed"
    assert r["https://blocked.example/live.m3u8"] == "blocklist:dmca"
    assert r["https://unknown.example/live.m3u8"] == "no-channel"
    assert r["http://x.example.net/live/user/pass/123.ts"] == "credentials-in-url"
    assert r["https://live.example.co.uk/hls/ua.m3u8"] == "needs-spoofed-headers"


def test_acceptances(built):
    r = reasons(built[1])
    assert r["https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8"] == "official:cdn-named"
    assert r["https://live.example.co.uk/hls/main.m3u8"] == "official:website-domain"
    assert r["https://jmp2.uk/plu-5f12101f0b12f00007e4f00a.m3u8"] == "fast:pluto-tv"
    assert r["https://live-hls-apps-aje-fa.getaj.net/AJE/index.m3u8"] == "official:broadcaster-host"


def test_entries(built):
    by_id = {e.id: e for e in built[0]}
    assert set(by_id) == {"DW.de@SD", "Example.uk@SD", "Pluto1.us@SD", "AlJazeera.qa@English"}
    dw = by_id["DW.de@SD"]
    assert (dw.title, dw.group, dw.logo, dw.source) == ("DW", "Live: News", "https://i.imgur.com/dw.png", "iptv-org")
    assert by_id["Pluto1.us@SD"].group == "FAST: Pluto TV"
    assert by_id["Pluto1.us@SD"].source == "pluto-tv"
    assert by_id["AlJazeera.qa@English"].title == "Al Jazeera English"  # non-main feed named


def test_registrable():
    assert iptv_org.registrable("a.b.example.co.uk") == "example.co.uk"
    assert iptv_org.registrable("www.dw.com") == "dw.com"


def test_allowlist_overrides(built):
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), {
        "allow": [{"channel": "DW.de", "hosts": ["pishow.tv"], "catchup": {"mode": "append", "days": 1,
                                                                            "source": "?utc={utc}"}}],
        "deny": ["Example.uk"],
    })
    entries, decisions = iptv_org.build(iptv_org.fetch_api(FIXTURES), rules)
    r = reasons(decisions)
    assert r["https://cdn-7.pishow.tv/live/431/master.m3u8"] == "allowlist"
    assert r["https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8"] == "allowlist-other-host"
    assert r["https://live.example.co.uk/hls/main.m3u8"] == "denied-channel"
    dw = next(e for e in entries if e.id == "DW.de@SD")
    assert (dw.catchup, dw.catchup_days, dw.catchup_source) == ("append", 1, "?utc={utc}")
