from datetime import date
from pathlib import Path

from freeplaylist import config, net, schedule
from freeplaylist.sources import iptv_org, website_check

FIXTURES = Path(__file__).parent / "fixtures" / "iptv_org"

HOME = """<html><a href="/en/live/">Watch live</a> <a href="https://other.example/live">elsewhere</a>
<a href="/about">About</a><script>var cfg = {"src":"https:\\/\\/edge.cdn-one.net\\/hls\\/main.m3u8"};</script></html>"""
LIVE = '<video src="https://stream.cdn-two.net/x/playlist.m3u8"></video>'


def fake(pages):
    def fetch(url, **kw):
        body = pages.get(url)
        return net.Probe(200 if body is not None else 404, url, (body or "").encode())
    return fetch


def test_hosts_from_home_and_live_pages():
    fetch = fake({"https://tv.example/": HOME, "https://tv.example/en/live/": LIVE})
    hosts, ok = website_check.site_hosts("https://tv.example/", fetch)
    assert ok
    assert {"edge.cdn-one.net", "stream.cdn-two.net"} <= hosts
    assert website_check.live_links(HOME, "https://tv.example/") == ["https://tv.example/en/live/"]


def test_cache_and_retry():
    calls = []

    def fetch(url, **kw):
        calls.append(url)
        return net.Probe(None, url, b"", "timeout")

    state = {}
    tonight = schedule.Tonight({}, date(2026, 10, 21))
    website_check.find_hosts({"https://down.example/"}, state, tonight, fetch=fetch)
    assert state["https://down.example/"]["ok"] is False
    website_check.find_hosts({"https://down.example/"}, state, tonight, fetch=fetch)
    assert len(calls) == 1  # not retried within a day


def test_website_link_accepts_unverified_stream():
    rules = iptv_org.Rules.from_config(config.load("live_hosts"), config.load("live_allowlist"))
    api = iptv_org.fetch_api(FIXTURES)
    # DW already has an accepted stream, so its site isn't fetched; the rule itself is tested here.
    assert "https://www.dw.com/" not in iptv_org.unverified_sites(api, rules)
    _, decisions = iptv_org.build(api, rules, {"https://www.dw.com/": {"cdn-7.pishow.tv"}})
    reasons = {d.item.split(" ", 1)[1]: d.reason for d in decisions}
    assert reasons["https://cdn-7.pishow.tv/live/431/master.m3u8"] == "official:website-link"
    assert reasons["http://170.83.16.50/DW/index.m3u8"] == "ip-host"  # hard rules still apply first


def test_malformed_links_and_failing_sites_dont_stop_the_check():
    home = '<a href="http://[broken/live">x</a><a href="/live">y</a>'
    assert website_check.live_links(home, "https://tv.example/") == ["https://tv.example/live"]

    def boom(url, **kw):
        raise ValueError("Invalid IPv6 URL")

    assert website_check.site_hosts("https://tv.example/", boom) == (set(), False)


FOOTER = """<footer><a href="/privacy">Privacy policy</a> <a href="/cookies">Cookie settings</a>
<a href="/en/terms-of-use">Terms of use</a> <a href="https://x.example/agb"><span>AGB</span></a>
<a href="/mentions-legales">Mentions légales</a> <a href="mailto:a@b.c">terms by mail</a>
<a href="/en/terms-of-use">Terms of use</a></footer>"""


def test_terms_links_in_any_language_without_privacy_pages():
    links = website_check.terms_links(FOOTER, "https://tv.example/")
    assert links == ["https://tv.example/en/terms-of-use", "https://x.example/agb",
                     "https://tv.example/mentions-legales"]  # privacy, cookies and mailto left out; no repeats
    assert website_check.terms_links("<a href='/about'>About</a>", "https://tv.example/") == []
    headlines = ('<a href="/2026/10/la-diputacio-amplia-fins-al-29-doctubre-el-termini-per-a-participar-en-el-concurs">'
                 "La Diputació amplia el termini per a participar en el concurs</a>"
                 '<a href="/media/the-ai-spending-frenzy-could-hit-a-political-roadblock">The AI spending frenzy and '
                 "the conditions of a political roadblock after the midterms</a>")
    assert website_check.terms_links(headlines, "https://tv.example/") == []  # news, not terms
    assert website_check.terms_links(FOOTER, "https://tv.example/", limit=1) == ["https://tv.example/en/terms-of-use"]


def test_find_terms_caches_and_retries():
    calls = []

    def fetch(url, **kw):
        calls.append(url)
        if "down" in url:
            return net.Probe(None, url, b"", "timeout")
        return net.Probe(200, url, FOOTER.encode())

    state = {}
    sites = {"https://tv.example/", "https://down.example/"}
    found = website_check.find_terms(sites, state, fetch=fetch)
    assert found == {"https://tv.example/": ["https://tv.example/en/terms-of-use", "https://x.example/agb",
                                             "https://tv.example/mentions-legales"]}
    assert state["https://down.example/"]["ok"] is False
    website_check.find_terms(sites, state, fetch=fetch)
    assert len(calls) == 2  # both remembered (the failure for a day, the answer for a month)
    state["https://down.example/"]["t"] -= 2 * 86400
    website_check.find_terms(sites, state, fetch=fetch)
    assert len(calls) == 3  # only the failed one is asked again
