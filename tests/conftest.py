import pytest

from freeplaylist.models import Entry


@pytest.fixture
def entry():
    def make(**kw) -> Entry:
        base = dict(id="x.1", title="Example", url="https://example.org/a.m3u8", group="DE | News", kind="live",
                    source="iptv-org")
        base.update(kw)
        return Entry(**base)

    return make
