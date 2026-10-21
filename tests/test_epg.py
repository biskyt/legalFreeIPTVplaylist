import gzip
import json
import xml.etree.ElementTree as ET
from datetime import date

import pytest

from freeplaylist import epg, net, schedule

XMLTV = b"""<?xml version="1.0"?><tv>
<channel id="{a}"><display-name>A</display-name></channel>
<programme start="20261020000000 +0000" stop="20261020010000 +0000" channel="{a}"><title>Old</title></programme>
<programme start="20991020000000 +0000" stop="20991020010000 +0000" channel="{a}"><title>{title}</title></programme>
<programme start="20991020000000 +0000" stop="20991020010000 +0000" channel="other"><title>X</title></programme>
</tv>"""


def doc(a, title):
    return XMLTV.replace(b"{a}", a.encode()).replace(b"{title}", title.encode())


def test_plan_routes_channels_to_fast_and_slow_sources(entry):
    entries = [
        entry(id="3sat.de@SD", title="3sat", extra={"main_feed": True}),
        entry(id="3sat.de@HD", title="3sat HD", extra={"main_feed": False}),
        entry(id="Pluto1.us@SD", title="Pluto 1"),
        entry(id="Local.fr@SD", title="Local & Co"),
    ]
    guides = [
        {"channel": "Pluto1.us", "feed": None, "site": "i.mjh.nz", "site_id": "PlutoTV/us#abc", "lang": "en"},
        {"channel": "Local.fr", "feed": "SD", "site": "tv.example", "site_id": "42", "lang": "fr"},
    ]
    plan = epg.plan(entries, guides, schedule.Tonight({"live_groups": 1}, date(2026, 10, 19)))
    assert plan["iptv_epg"]["de"] == {"3sat.de": ["3sat.de@SD"]}  # main feed only
    assert plan["mjh"]["https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/PlutoTV/us.xml"] == {
        "abc": ["Pluto1.us@SD"]}
    assert plan["slow"] == plan["tonight"] == [["tv.example", "42", "fr", "Local.fr@SD", "Local & Co"]]
    xml = epg.channels_xml(plan["slow"])
    assert 'xmltv_id="Local.fr@SD">Local &amp; Co</channel>' in xml


def test_merger_renames_drops_finished_and_first_source_wins(tmp_path):
    m = epg.Merger(now=1_800_000_000)  # 2027
    assert m.add("iptv-epg.org", doc("3sat.de", "Fast"), {"3sat.de": ["3sat.de@SD"]}) == 1
    assert m.add("grabber", doc("3sat.de@SD", "Slow"), {"3sat.de@SD": ["3sat.de@SD"]}) == 0  # already covered
    out = tmp_path / "g.xml.gz"
    assert m.write(out) == 1
    text = gzip.decompress(out.read_bytes()).decode()
    assert 'channel id="3sat.de@SD"' in text and ">Fast<" in text
    assert ">Old<" not in text and ">Slow<" not in text and 'channel="other"' not in text


def test_download_follows_meta_refresh(monkeypatch):
    page = b"<!DOCTYPE html><meta http-equiv=\"refresh\" content=\"0;url='https://x/real.xml.gz'\" />"
    files = {"https://x/epg-de.xml.gz": page, "https://x/real.xml.gz": gzip.compress(b"<tv/>")}
    monkeypatch.setattr(net, "get_bytes", lambda url, **kw: files[url])
    assert epg._download("https://x/epg-de.xml.gz") == b"<tv/>"


def test_merge_saves_tonights_group_and_combines(tmp_path, monkeypatch):
    folder = tmp_path / "epg"
    folder.mkdir()
    slow = [["s", "1", "fr", "Old.fr@SD", "Old"], ["s", "2", "fr", "Local.fr@SD", "Local"]]
    plan = {"iptv_epg": {"de": {"3sat.de": ["3sat.de@SD"]}}, "mjh": {}, "slow": slow, "tonight": [], "night": 2}
    (folder / "plan.json").write_text(json.dumps(plan))
    (folder / "group-5.xml.gz").write_bytes(gzip.compress(doc("Old.fr@SD", "Earlier night")))
    grabbed = tmp_path / "grabbed.xml.gz"
    grabbed.write_bytes(gzip.compress(doc("Local.fr@SD", "Tonight")))
    monkeypatch.setattr(epg, "_download", lambda url: doc("3sat.de", "Fast"))
    assert epg.merge(tmp_path, tmp_path / "site" / "epg.xml.gz", grabbed) == 3
    assert (folder / "group-2.xml.gz").exists()


def test_listing_without_current_programmes_doesnt_block_a_later_source(tmp_path):
    m = epg.Merger(now=1_800_000_000)
    empty = b'<tv><channel id="X"><display-name>X</display-name></channel></tv>'
    assert m.add("iptv-epg.org", empty, {"X": ["X.us@SD"]}) == 0
    assert m.add("grabber", doc("X.us@SD", "Grabbed"), {"X.us@SD": ["X.us@SD"]}) == 1


def test_broken_source_leaves_nothing_behind(tmp_path):
    m = epg.Merger(now=1_800_000_000)
    broken = doc("3sat.de", "Partial").replace(b"</tv>", b"<programme")
    with pytest.raises(ET.ParseError):
        m.add("iptv-epg.org", broken, {"3sat.de": ["3sat.de@SD"]})
    assert m.add("grabber", doc("3sat.de@SD", "Whole"), {"3sat.de@SD": ["3sat.de@SD"]}) == 1
    out = tmp_path / "g.xml.gz"
    m.write(out)
    text = gzip.decompress(out.read_bytes()).decode()
    assert ">Whole<" in text and ">Partial<" not in text
