"""Which sources and which host groups the build refreshes on a given night (config/schedule.yaml)."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import date


def group(key: str, groups: int) -> int:
    """A stable group number for a host or site, so its turn comes round on the same night each week."""
    return zlib.crc32(key.encode()) % groups


@dataclass(frozen=True)
class Tonight:
    """The schedule as it applies to one night of building."""

    cfg: dict
    day: date

    @property
    def groups(self) -> int:
        return self.cfg.get("live_groups", 7)

    @property
    def night(self) -> int:
        """Which host group is checked tonight."""
        return self.day.weekday() % self.groups

    def due(self, source: str) -> bool:
        """Whether a source is harvested tonight: one of its weekdays, in one of its weeks."""
        rule = (self.cfg.get("sources") or {}).get(source)
        if rule is None:
            return True  # unscheduled sources run every night
        every = rule.get("every_weeks", 1)
        return self.day.weekday() in rule.get("days", range(7)) and self.day.isocalendar().week % every == 0

    def is_turn(self, key: str) -> bool:
        """Whether a host or site is in tonight's group."""
        return group(key, self.groups) == self.night
