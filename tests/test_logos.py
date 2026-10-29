from freeplaylist import logos, net

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 20
IMGUR = "https://i.imgur.com/a.png"
PLUTO = "https://images.pluto.tv/a.png"
OTHER = "https://cdn.example/a.png"


def test_split_keeps_alternatives_only_when_the_first_logo_is_on_imgur():
    assert logos.split([]) == (None, [])
    assert logos.split([PLUTO, IMGUR]) == (PLUTO, [])  # already fine: nothing to look for
    assert logos.split([IMGUR, "https://i.imgur.com/b.png", PLUTO, OTHER, PLUTO]) == (IMGUR, [PLUTO, OTHER])
    assert logos.split([IMGUR]) == (IMGUR, [])


def test_is_image_by_content_not_by_header():
    assert logos.is_image(PNG) and logos.is_image(b"\xff\xd8\xff\xe0jfif") and logos.is_image(b"GIF89a")
    assert logos.is_image(b"RIFF\0\0\0\0WEBPVP8 ") and logos.is_image(b'<?xml version="1.0"?><svg xmlns="x"/>')
    assert not logos.is_image(b"<!DOCTYPE html><html>") and not logos.is_image(b"")


def fake(answers, seen):
    def probe(url, **kw):
        seen.append(url)
        status, body = answers.get(url, (404, b""))
        return net.Probe(status, url, body)
    return probe


def test_switches_to_the_first_alternative_that_loads(entry):
    a = entry(id="a", logo=IMGUR, extra={"logo_alternatives": [OTHER, PLUTO]})
    b = entry(id="b", logo=IMGUR, extra={"logo_alternatives": [OTHER]})
    c = entry(id="c", logo=IMGUR)  # nothing else to use
    seen = []
    state = {}
    n = logos.prefer_open_hosts([a, b, c], state, fake({OTHER: (404, b""), PLUTO: (200, PNG)}, seen), now=1000)
    assert (n, a.logo, b.logo, c.logo) == (1, PLUTO, IMGUR, IMGUR)
    assert "logo_alternatives" not in a.extra and sorted(seen) == [OTHER, PLUTO]  # each checked once
    assert state[PLUTO] == {"t": 1000, "ok": True} and state[OTHER] == {"t": 1000, "ok": False}


def test_checks_are_remembered_and_unclear_answers_are_not(entry):
    seen = []
    answers = {PLUTO: (200, PNG), OTHER: (429, b"")}
    state = {}
    e = lambda: entry(id="a", logo=IMGUR, extra={"logo_alternatives": [OTHER, PLUTO]})  # noqa: E731
    first = e()
    logos.prefer_open_hosts([first], state, fake(answers, seen), now=1000)
    assert first.logo == PLUTO and OTHER not in state  # throttled: no verdict recorded
    seen.clear()
    second = e()
    logos.prefer_open_hosts([second], state, fake(answers, seen), now=1000 + 86400)
    assert second.logo == PLUTO and seen == [OTHER]  # only the unanswered one is asked again
    third = e()
    logos.prefer_open_hosts([third], state, fake(answers, seen), now=1000 + 40 * 86400)  # PLUTO's check expired
    assert PLUTO in seen[1:]


def test_an_html_page_is_not_a_logo(entry):
    e = entry(id="a", logo=IMGUR, extra={"logo_alternatives": [OTHER]})
    logos.prefer_open_hosts([e], {}, fake({OTHER: (200, b"<html>sign in</html>")}, []), now=1)
    assert e.logo == IMGUR
