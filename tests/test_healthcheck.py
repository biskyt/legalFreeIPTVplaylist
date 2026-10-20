from freeplaylist import healthcheck, net

MASTER = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow/index.m3u8\n"
MEDIA = b"#EXTM3U\n#EXTINF:6,\nseg1.ts\n"


def fake(responses):
    def probe(url, **kw):
        status, body = responses.get(url, (None, b""))
        return net.Probe(status, url, body, None if status == 200 else f"HTTP {status}")
    return probe


def run(entries, responses, state=None, **kw):
    state = {} if state is None else state
    checker = healthcheck.Checker(probe=fake(responses), workers=4)
    kept, decisions = healthcheck.run(entries, state, checker, today="2026-10-20", **kw)
    return kept, {d.item: d.reason for d in decisions}, state


def test_master_and_variant_must_load(entry):
    ok = entry(id="ok", url="https://a/master.m3u8")
    bad_variant = entry(id="bad", url="https://b/master.m3u8")
    responses = {"https://a/master.m3u8": (200, MASTER), "https://a/low/index.m3u8": (200, MEDIA),
                 "https://b/master.m3u8": (200, MASTER), "https://b/low/index.m3u8": (404, b"")}
    kept, reasons, state = run([ok, bad_variant], responses)
    assert [e.id for e in kept] == ["ok"]
    assert reasons["bad"].startswith("dead")
    assert state["https://a/master.m3u8"] == {"ok": "2026-10-20", "fails": 0}


def test_falls_back_to_next_candidate(entry):
    e = entry(url="https://dead/x.m3u8", extra={"candidates": [
        {"url": "https://dead/x.m3u8"}, {"url": "https://alive/x.m3u8", "user_agent": "UA"}]})
    kept, reasons, _ = run([e], {"https://alive/x.m3u8": (200, MEDIA)})
    assert kept[0].url == "https://alive/x.m3u8" and kept[0].user_agent == "UA"


def test_geo_blocked_kept_only_when_labelled(entry):
    labelled = entry(id="geo", url="https://g/x.m3u8", extra={"labels": ["Geo-blocked"]})
    unlabelled = entry(id="forbidden", url="https://f/x.m3u8")
    kept, reasons, _ = run([labelled, unlabelled], {"https://g/x.m3u8": (403, b""), "https://f/x.m3u8": (403, b"")})
    assert [e.id for e in kept] == ["geo"] and reasons["geo"] == "geo-blocked"


def test_grace_run_for_previously_working_stream(entry):
    e = entry(url="https://flaky/x.m3u8")
    state = {"https://flaky/x.m3u8": {"ok": "2026-10-19", "fails": 0}}
    kept, reasons, state = run([e], {}, state)
    assert kept and reasons[e.id] == "grace" and state["https://flaky/x.m3u8"]["fails"] == 1
    kept, reasons, state = run([e], {}, state)
    assert not kept and state["https://flaky/x.m3u8"]["fails"] == 2


def test_never_working_stream_dropped_at_once(entry):
    kept, _, _ = run([entry(url="https://never/x.m3u8")], {})
    assert not kept


def test_mp4_and_sampling(entry):
    known = entry(id="known", kind="movie", url="https://ia/known.mp4")
    new = entry(id="new", kind="movie", url="https://ia/new.mp4")
    state = {"https://ia/known.mp4": {"ok": "2026-10-01", "fails": 0}}
    kept, reasons, _ = run([known, new], {"https://ia/new.mp4": (200, b"\x00\x00\x00 ftyp")}, state, sample=0.0)
    assert [e.id for e in kept] == ["known", "new"]
    assert set(reasons) == {"new"}  # the known entry wasn't sampled


def test_vod_kept_when_server_gives_no_answer(entry):
    busy = entry(id="busy", kind="movie", url="https://ia/busy.mp4")
    gone = entry(id="gone", kind="movie", url="https://ia/gone.mp4")
    kept, reasons, state = run([busy, gone], {"https://ia/busy.mp4": (503, b""), "https://ia/gone.mp4": (404, b"")},
                               keep_on_error=True)
    assert [e.id for e in kept] == ["busy"] and reasons["busy"].startswith("unconfirmed")
    assert "https://ia/busy.mp4" not in state  # no answer: nothing recorded


def test_live_server_errors_still_drop_new_streams(entry):
    kept, _, _ = run([entry(url="https://live/x.m3u8")], {"https://live/x.m3u8": (503, b"")})
    assert not kept
