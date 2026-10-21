from freeplaylist.sources import open_beelden as ob

RECORD = """<record><header><identifier>oai:openimages.eu:{id}</identifier></header><metadata><oai_oi:oi
 xmlns:oai_oi="http://www.openbeelden.nl/feeds/oai/" xmlns:oi="http://www.openbeelden.nl/oai/">
<oi:title>{title}</oi:title><oi:date>1929-11-01</oi:date><oi:extent>{extent}</oi:extent>
<oi:medium format="hd">https://www.openbeelden.nl/files/{id}.mp4</oi:medium>
<oi:medium format="thumbnail">/images/{id}.png</oi:medium><oi:language>nl</oi:language>
<oi:attributionName>Polygoon</oi:attributionName><oi:attributionURL>/media/{id}</oi:attributionURL>
<oi:license>{lic}</oi:license></oai_oi:oi></metadata></record>"""


def page(records, token=""):
    return ('<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>' + "".join(records)
            + f"<resumptionToken>{token}</resumptionToken></ListRecords></OAI-PMH>").encode()


PD = "https://creativecommons.org/publicdomain/mark/1.0/"
EMPTY = (b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
         b'<error code="noRecordsMatch">none</error></OAI-PMH>')


def feed(urls, slow_over_days=None):
    """A fake feed with three records dated 1929-11-01, two pages long; windows that hold them but are longer
    than a month still answer with a resumption token (more pages), and with slow_over_days, windows that hold
    them and are longer than that time out."""
    first = page([RECORD.format(id=1, title="Lang", extent="PT12M3S", lic=PD),
                  RECORD.format(id=2, title="Kort", extent="PT46S", lic=PD)], token="!f!u!2")
    second = page([RECORD.format(id=3, title="NC", extent="PT20M",
                                 lic="https://creativecommons.org/licenses/by-nc/3.0/")])

    def fetch(url, **kw):
        urls.append(url)
        if "resumptionToken" in url:
            return second
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        if not q["from"] <= "1929-11-01" <= q["until"]:
            return EMPTY
        if slow_over_days and ob._days([q["from"], q["until"]]) > slow_over_days:
            raise TimeoutError("timed out")
        return first

    return fetch


def test_harvest_and_build():
    urls = []
    state = {}
    entries, decisions = ob.build({"min_minutes": 3, "max": 10, "max_pages": 1000}, state, feed(urls), pause=0)
    assert [e.title for e in entries] == ["Lang (1929)"]
    e = entries[0]
    assert (e.duration, e.languages, e.countries) == (723, ["nld"], ["NL"])
    assert e.page == "https://www.openbeelden.nl/media/1" and "Polygoon" in e.attribution
    assert {d.item: d.reason for d in decisions}["oai:openimages.eu:3"] == "license:restricted"
    assert state["walked"] and not state["windows"]  # every window done
    assert any(u.endswith("resumptionToken=!f!u!2") for u in urls)  # "!" not percent-encoded
    assert len(urls) < 40  # empty stretches cost one request each, not one per month


def test_walk_carries_on_over_runs_and_repeats_monthly():
    urls = []
    state = {}
    ob.harvest(state, feed(urls), pause=0, max_pages=3)
    assert state["windows"] and "walked" not in state
    ob.harvest(state, feed(urls), pause=0, max_pages=1000)
    assert len(state["records"]) == 3 and state["walked"]
    asked = len(urls)
    ob.harvest(state, feed(urls), pause=0)
    assert len(urls) == asked  # walked recently: nothing to ask
    state["walked"] = "2000-01-01"
    ob.harvest(state, feed(urls), pause=0, max_pages=1000)
    assert len(urls) > asked and state["walked"] != "2000-01-01"


def test_windows_the_server_cant_answer_are_split():
    urls = []
    state = {}
    ob.harvest(state, feed(urls, slow_over_days=3650), pause=0, max_pages=1000)
    assert len(state["records"]) == 3 and state["walked"]  # found in the smaller windows it could answer
    assert "skipped" not in state


def test_a_day_that_never_answers_waits_for_the_next_walk():
    state = {}
    ob.harvest(state, feed([], slow_over_days=-1), pause=0, max_pages=1000)
    assert state["skipped"] == [["1929-11-01", "1929-11-01"]] and state["walked"]


def test_expired_token_is_not_taken_as_done():
    expired = (b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
               b'<error code="badResumptionToken">gone</error></OAI-PMH>')
    state = {}
    ob.harvest(state, lambda url, **kw: expired, pause=0, max_pages=5)
    assert state["windows"] and "walked" not in state


def test_seconds():
    assert ob.seconds("PT1H2M3S") == 3723 and ob.seconds("PT46S") == 46 and ob.seconds("") is None


def test_failed_harvest_keeps_partial_records():
    first = page([RECORD.format(id=1, title="Lang", extent="PT12M3S", lic=PD)], token="!t")

    def fetch(url, **kw):
        if "resumptionToken" in url:
            raise ValueError("garbled")
        return first

    state = {}
    ob.harvest(state, fetch, pause=0)
    assert list(state["records"]) == ["oai:openimages.eu:1"] and "walked" not in state and state["windows"]


def test_filling_until_the_first_walk_is_done():
    assert ob.filling({}) and ob.filling({"windows": [["1900-01-01", "1901-01-01"]]})
    assert not ob.filling({"walked": "2026-10-21"})
