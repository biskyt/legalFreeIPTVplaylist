from freeplaylist.sources import wikimedia_commons as wc

CFG = {"queries": ["q"], "min_minutes": 5, "short_minutes": 40, "max_height": 720,
       "groups": {"feature": "Movies: World Classics", "short": "Movies: Shorts", "documentary": "Documentaries: C"}}


def page(title, duration, licence, cats, derivs):
    return {"pageid": hash(title), "title": title, "categories": [{"title": c} for c in cats],
            "videoinfo": [{"duration": duration, "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                           "derivatives": derivs,
                           "extmetadata": {"LicenseShortName": {"value": licence},
                                           "Artist": {"value": "<a>S. E.</a>"}}}]}


VP9 = [{"type": 'video/webm; codecs="vp9, opus"', "height": 480, "src": "https://u/480.webm?x=1"},
       {"type": 'video/webm; codecs="vp9, opus"', "height": 1080, "src": "https://u/1080.webm"},
       {"type": 'video/quicktime; codecs="mp4v"', "height": 360, "src": "https://u/360.mov"}]


def test_build(monkeypatch):
    pages = [
        page("File:Battleship Potemkin (1925).webm", 4244, "Public domain",
             ["Category:Silent films", "Category:Films of the Soviet Union"], VP9),
        page("File:Short.ogv", 120, "Public domain", [], VP9),
        page("File:Nonfree.webm", 4000, "CC BY-NC 4.0", [], VP9),
        page("File:Theora only.ogv", 4000, "CC0", [], [{"type": "video/ogg", "height": 480, "src": "https://u/o"}]),
        page("File:Le Film (1930).webm", 5000, "CC BY-SA 4.0",
             ["Category:French-language films", "Category:1930 films of France", "Category:Documentary films"], VP9),
    ]
    monkeypatch.setattr(wc, "fetch", lambda q, limit: pages)
    entries, decisions = wc.build(CFG)
    reasons = {d.item: d.reason for d in decisions}
    assert reasons["File:Short.ogv"] == "too-short"
    assert reasons["File:Nonfree.webm"].startswith("license:")
    assert reasons["File:Theora only.ogv"] == "no-webm"
    by = {e.title: e for e in entries}
    potemkin = by["Battleship Potemkin (1925)"]
    assert potemkin.url == "https://u/480.webm" and potemkin.languages == ["zxx"]
    assert potemkin.group == "Movies: World Classics" and "S. E." in potemkin.attribution
    film = by["Le Film (1930)"]
    assert (film.languages, film.countries, film.group) == (["fra"], ["FR"], "Documentaries: C")


def test_clean_title():
    assert wc.clean_title("1936. Цирк") == "Цирк"
    assert wc.clean_title("The Cat and the Canary (1927) by Paul Leni") == "The Cat and the Canary"
