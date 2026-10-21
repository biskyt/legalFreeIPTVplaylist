from datetime import date

from freeplaylist import build, schedule, snapshots
from freeplaylist.models import Decision

CFG = {"sources": {"weekly": {"days": [3]}, "fortnightly": {"days": [4], "every_weeks": 2}}}


def test_due():
    thursday = date(2026, 10, 22)  # ISO week 43
    assert schedule.due(CFG, "weekly", thursday)
    assert not schedule.due(CFG, "weekly", date(2026, 10, 21))
    assert schedule.due(CFG, "unlisted", thursday)
    assert not schedule.due(CFG, "fortnightly", date(2026, 10, 23))  # Friday, odd week
    assert schedule.due(CFG, "fortnightly", date(2026, 10, 30))  # Friday, even week


def test_groups_are_stable_and_spread():
    hosts = [f"h{i}.example" for i in range(700)]
    groups = [schedule.group(h, 7) for h in hosts]
    assert groups == [schedule.group(h, 7) for h in hosts]
    assert all(60 < groups.count(g) < 140 for g in range(7))


def test_snapshot_round_trip(tmp_path, entry):
    e = entry(id="a", languages=["eng"], extra={"candidates": [{"url": "u"}]})
    snapshots.save(tmp_path, "src", [e], [Decision("src", "a", True, "ok")], "2026-10-21")
    entries, decisions, day = snapshots.load(tmp_path, "src")
    assert entries == [e] and decisions[0].reason == "ok" and day == "2026-10-21"
    assert snapshots.load(tmp_path, "missing") is None


def test_sources_not_due_come_from_their_snapshot(tmp_path, monkeypatch):
    from test_build import FIXTURES, fake_archive

    from freeplaylist.sources import internet_archive as ia
    fake_archive(monkeypatch)
    calls = []
    real_movies = ia.movies
    monkeypatch.setattr(ia, "movies", lambda *a: calls.append(1) or real_movies(*a))

    def options(day):
        return build.Options(out=tmp_path / "site", state_dir=tmp_path / "state", api_dir=FIXTURES, health=False,
                             website_check=False, extra_vod=False, enrich=False, enforce_minimums=False, day=day)

    build.run(options(date(2026, 10, 21)))  # Wednesday: no snapshot yet, so harvested anyway
    first = (tmp_path / "site" / "movies.m3u").read_text()
    build.run(options(date(2026, 10, 21)))  # not its day: from the snapshot
    assert len(calls) == 1 and (tmp_path / "site" / "movies.m3u").read_text() == first
    build.run(options(date(2026, 10, 22)))  # Thursday: harvested again
    assert len(calls) == 2
