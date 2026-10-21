"""Which sources and which host groups the build refreshes on a given night (config/schedule.yaml)."""

from __future__ import annotations

import zlib
from datetime import date


def due(cfg: dict, source: str, day: date) -> bool:
    """Whether a source is harvested on `day`: one of its weekdays, in one of its weeks."""
    rule = (cfg.get("sources") or {}).get(source)
    if rule is None:
        return True  # unscheduled sources run every night
    every = rule.get("every_weeks", 1)
    return day.weekday() in rule.get("days", range(7)) and day.isocalendar().week % every == 0


def group(key: str, groups: int) -> int:
    """A stable group number for a host or site, so its turn comes round on the same night each week."""
    return zlib.crc32(key.encode()) % groups


def tonight(day: date, groups: int) -> int:
    return day.weekday() % groups
