"""Each source's last results, so a source that isn't due tonight can be reused instead of harvested again.

A snapshot holds the source's entries before health checks (state/snapshots/<source>.json). The playlists are
rebuilt every night from all snapshots, so refreshing one source replaces exactly that source's entries.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from . import config
from .models import Decision, Entry


def save(state_dir: Path, source: str, entries: list[Entry], decisions: list[Decision], day: str) -> None:
    config.save_state(state_dir / "snapshots" / f"{source}.json", {
        "day": day,
        "entries": [dataclasses.asdict(e) for e in entries],
        "decisions": [dataclasses.asdict(d) for d in decisions],
    })


def load(state_dir: Path, source: str) -> tuple[list[Entry], list[Decision], str] | None:
    """A source's snapshot, or None if there isn't a usable one (then the source is simply harvested again)."""
    data = config.load_state(state_dir / "snapshots" / f"{source}.json")
    try:
        return ([Entry(**e) for e in data["entries"]], [Decision(**d) for d in data.get("decisions", [])],
                data.get("day", "?"))
    except (KeyError, TypeError):  # none yet, or written by an older version with different fields
        return None
