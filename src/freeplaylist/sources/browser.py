"""Reads websites in a real browser, for pages that build their player with JavaScript.

A plain page fetch (website_check.py) only sees the HTML the server sends. Many broadcasters' sites put the stream
address in by script, so the host never appears in it. A browser runs the scripts, so this records two things for
each site: the hosts mentioned in the page as it ends up, and the hosts the page itself requests while it loads
(a player asking a host for its stream is the owner's own page publishing that stream, which is better proof
than a mention). Only hosts we are trying to prove for that site (`wanted`) are kept.

Playwright is optional (pip install "freeplaylist[browser]", then `playwright install chromium`); without it
nothing is read here and the plain fetch is all that is used.
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse

from .. import net
from .website_check import hosts_in, live_links

log = logging.getLogger("freeplaylist")
SKIP = {"image", "font", "stylesheet", "media"}  # not needed to see which hosts a page talks to
SETTLE_MS = 6000  # let the player start and ask for its stream
PAGE_MS = 20000
UA_SUFFIX = f" ({net.USER_AGENT})"


async def _visit(context, url: str, hosts: set[str], requested: set[str]) -> str:
    page = await context.new_page()
    page.on("request", lambda r: requested.add((urllib.parse.urlparse(r.url).hostname or "").lower()))
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_MS)
        await page.wait_for_timeout(SETTLE_MS)
        html = await page.content()
        hosts |= hosts_in(html)
        return html
    finally:
        await page.close()


async def _read_site(browser, ua: str, url: str, wanted: set[str]) -> tuple[set[str], set[str], bool]:
    context = await browser.new_context(ignore_https_errors=True, user_agent=ua + UA_SUFFIX)

    async def block(route):
        await (route.abort() if route.request.resource_type in SKIP else route.continue_())

    await context.route("**/*", block)
    hosts: set[str] = set()
    requested: set[str] = set()
    ok = False
    try:
        home = await _visit(context, url, hosts, requested)
        ok = True
        for link in live_links(home, url):
            await _visit(context, link, hosts, requested)
    except Exception as e:  # noqa: BLE001 - one odd site never stops the rest; it's retried another night
        log.debug("browser: %s: %s", url, e)
    finally:
        await context.close()
    return hosts & wanted, requested & wanted, ok


async def _run(urls: list[str], wanted: dict[str, set[str]], concurrency: int, budget: float):
    from playwright.async_api import async_playwright

    out: dict[str, tuple[set[str], set[str], bool]] = {}
    deadline = time.monotonic() + budget
    queue: asyncio.Queue = asyncio.Queue()
    for u in urls:
        queue.put_nowait(u)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        probe = await browser.new_context()
        ua = await (await probe.new_page()).evaluate("navigator.userAgent")  # the browser's own, plus our name
        await probe.close()

        async def worker():
            while time.monotonic() < deadline:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                out[url] = await _read_site(browser, ua, url, wanted.get(url, set()))

        await asyncio.gather(*(worker() for _ in range(concurrency)))
        await browser.close()
    return out


def render(urls: list[str], wanted: dict[str, set[str]], *, concurrency: int = 4,
           budget: float = 900) -> dict[str, tuple[set[str], set[str], bool]]:
    """{site: (wanted hosts its page mentions, wanted hosts its page requests, whether it loaded)} for as many of
    `urls` as fit in `budget` seconds. {} when Playwright or its browser isn't installed."""
    if not urls:
        return {}
    try:
        import playwright  # noqa: F401
    except ImportError:
        log.info("browser: Playwright isn't installed; JavaScript sites are not read")
        return {}
    try:
        return asyncio.run(_run(urls, wanted, concurrency, budget))
    except Exception as e:  # noqa: BLE001 - e.g. the browser itself isn't installed
        log.warning("browser: couldn't run (%s); JavaScript sites are not read", str(e).splitlines()[0][:150])
        return {}
