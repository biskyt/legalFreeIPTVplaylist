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


def test_harvest_and_build():
    pd = "https://creativecommons.org/publicdomain/mark/1.0/"
    pages = {
        "first": page([RECORD.format(id=1, title="Lang", extent="PT12M3S", lic=pd),
                       RECORD.format(id=2, title="Kort", extent="PT46S", lic=pd)], token="!f!u!2"),
        "second": page([RECORD.format(id=3, title="NC", extent="PT20M", lic="https://creativecommons.org/licenses/by-nc/3.0/")]),
    }
    urls = []

    def fetch(url, **kw):
        urls.append(url)
        return pages["second" if "resumptionToken" in url else "first"]

    state = {}
    entries, decisions = ob.build({"min_minutes": 3, "max": 10, "max_pages": 1000}, state, fetch, pause=0)
    assert urls[1].endswith("resumptionToken=!f!u!2")  # "!" not percent-encoded
    assert [e.title for e in entries] == ["Lang (1929)"]
    e = entries[0]
    assert (e.duration, e.languages, e.countries) == (723, ["nld"], ["NL"])
    assert e.page == "https://www.openbeelden.nl/media/1" and "Polygoon" in e.attribution
    assert {d.item: d.reason for d in decisions}["oai:openimages.eu:3"] == "license:restricted"
    assert state["last"] and state["years"][0] == 2007  # all year windows done: changes only from now on
    assert "from=2007-01-01&until=2007-12-31" in urls[0]


def test_page_budget_spreads_first_harvest_over_runs():
    pd = "https://creativecommons.org/publicdomain/mark/1.0/"
    one = page([RECORD.format(id=1, title="Lang", extent="PT12M3S", lic=pd)])
    state = {}
    ob.harvest(state, lambda url, **kw: one, pause=0, max_pages=3)
    assert state["years"] == [2007, 2008, 2009] and "last" not in state
    ob.harvest(state, lambda url, **kw: one, pause=0, max_pages=100)
    assert "last" in state


def test_seconds():
    assert ob.seconds("PT1H2M3S") == 3723 and ob.seconds("PT46S") == 46 and ob.seconds("") is None


def test_failed_harvest_keeps_partial_records():
    pd = "https://creativecommons.org/publicdomain/mark/1.0/"
    first = page([RECORD.format(id=1, title="Lang", extent="PT12M3S", lic=pd)], token="!t")

    def fetch(url, **kw):
        if "resumptionToken" in url:
            raise TimeoutError("timed out")
        return first

    state = {}
    ob.harvest(state, fetch, pause=0)
    assert list(state["records"]) == ["oai:openimages.eu:1"] and "last" not in state
