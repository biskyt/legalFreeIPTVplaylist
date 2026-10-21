"""Progress lines for long steps. A build log shows nothing else while a step runs, so each long loop logs how
far it has got, once a minute (never per item, so logs stay short)."""

from __future__ import annotations

import logging
import threading
from collections import Counter

log = logging.getLogger("freeplaylist")
EVERY = 60.0  # seconds between progress lines


class Progress:
    """`with Progress("health", total) as p: ... p.done()`. With `left` (items to do per key, e.g. per host), the
    lines also name the keys with most left, which shows where a slow or throttling server is."""

    def __init__(self, label: str, total: int, left: Counter | None = None, every: float | None = None):
        self.label, self.total, self.left = label, total, left
        self.every = EVERY if every is None else every
        self.count = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def done(self, key: str | None = None, n: int = 1) -> None:
        with self._lock:
            self.count += n
            if self.left is not None and key is not None:
                self.left[key] -= n

    def _report(self) -> None:
        while not self._stop.wait(self.every):
            with self._lock:
                line = f"{self.label}: {self.count} of {self.total} done"
                if self.left is not None:
                    most = (+self.left).most_common(3)  # unary + drops keys with nothing left
                    line += "; most left: " + (", ".join(f"{k} {n}" for k, n in most) or "-")
            log.info(line)

    def __enter__(self) -> Progress:
        if self.total:
            log.info("%s: %d to do", self.label, self.total)
            threading.Thread(target=self._report, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
