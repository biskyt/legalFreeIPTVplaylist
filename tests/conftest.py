import pytest

from freeplaylist import languages
from freeplaylist.models import Entry


@pytest.fixture(autouse=True)
def _isolated_language_lists(monkeypatch):
    """A build loads the full language and country lists into the module; tests start from the built-in ones."""
    for name in ("NAMES", "_BY_NAME", "_COUNTRIES"):
        monkeypatch.setattr(languages, name, dict(getattr(languages, name)))


@pytest.fixture
def entry():
    def make(**kw) -> Entry:
        base = dict(id="x.1", title="Example", url="https://example.org/a.m3u8", group="DE | News", kind="live",
                    source="example-source")
        base.update(kw)
        return Entry(**base)

    return make
