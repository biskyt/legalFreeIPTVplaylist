import http.server
import threading

import pytest

from freeplaylist import net
from freeplaylist.sources import browser, website_check

# The stream address never appears in the HTML the server sends: script builds it, and the page requests another
# host ("localhost", while the page is on 127.0.0.1) the way a player asks its CDN for a manifest.
PAGE = b"""<html><body><a href="/watch/live">Live</a><div id="p"></div><script>
const host = ["stream", "example", "com"].join(".");
document.getElementById("p").textContent = "https://" + host + "/live/main.m3u8";
fetch("http://localhost:" + location.port + "/live/playlist.m3u8").catch(() => {});
</script></body></html>"""


@pytest.fixture(scope="module")
def site():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html" if not self.path.endswith("m3u8") else "text/plain")
            self.end_headers()
            self.wfile.write(PAGE if not self.path.endswith("m3u8") else b"#EXTM3U")

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


def test_the_plain_fetch_cant_see_a_host_that_script_builds(site):
    hosts, ok = website_check.site_hosts(site)
    assert ok and "stream.example.com" not in hosts


def test_a_browser_sees_the_host_and_what_the_page_requests(site, monkeypatch):
    pytest.importorskip("playwright")
    monkeypatch.setattr(browser, "SETTLE_MS", 500)
    out = browser.render([site], {site: {"stream.example.com", "localhost", "unrelated.example.org"}}, concurrency=1,
                         budget=60)
    if not out:
        pytest.skip("no browser installed")
    mentioned, requested, ok = out[site]
    assert ok and mentioned == {"stream.example.com"} and requested == {"localhost"}  # only wanted hosts are kept


def test_without_playwright_nothing_is_read(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_playwright(name, *a, **kw):
        if name == "playwright":
            raise ImportError(name)
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_playwright)
    assert browser.render(["https://tv.example/"], {"https://tv.example/": {"a.example"}}) == {}
    assert browser.render([], {}) == {}


def test_browser_results_reach_the_cache_and_the_rules(tmp_path):
    from datetime import date

    from freeplaylist import schedule

    site = "https://tv.example/"
    calls = []

    def render(urls, wanted):
        calls.append((urls, wanted))
        return {site: ({"cdn.example"}, {"cdn.example"}, True)}

    def fetch(url, **kw):
        return net.Probe(200, url, b"<html>no streams here</html>")

    state = {}
    tonight = schedule.Tonight({}, date(2026, 10, 21))
    links = website_check.find_hosts({site}, state, tonight, fetch=fetch, wanted={site: {"cdn.example"}},
                                     render=render)
    assert calls == [([site], {site: {"cdn.example"}})] and links[site] == {"cdn.example"}
    assert website_check.page_hosts({site}, state) == {site: {"cdn.example"}}
    assert state[site]["rendered"] and state[site]["ok"]
    # Read recently: the browser isn't asked again; and a site whose plain page already shows the host isn't read.
    website_check.find_hosts({site}, state, tonight, fetch=fetch, wanted={site: {"other.example"}}, render=render)
    assert len(calls) == 1
    other = "https://other.example/"
    website_check.find_hosts({other}, state, tonight, wanted={other: {"seen.example"}}, render=render,
                             fetch=lambda url, **kw: net.Probe(200, url, b"<a>https://seen.example/x.m3u8</a>"))
    assert len(calls) == 1
