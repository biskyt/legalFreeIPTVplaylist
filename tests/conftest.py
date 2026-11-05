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


@pytest.fixture
def permitted_config(tmp_path):
    """A copy of config/ whose permissions.yaml allows the fixture channels (the real file lists real owners)."""
    import shutil

    import yaml

    from freeplaylist import config

    folder = tmp_path / "config"
    shutil.copytree(config.CONFIG_DIR, folder)
    grants = [{"channel": c, "url": f"https://{c.split('.')[0].lower()}.example/terms",
               "quote": "Anyone may redistribute our live stream.", "checked": "2026-11-05"}
              for c in ("Example.uk", "Local1.us", "AlJazeera.qa", "DW.de")]
    (folder / "permissions.yaml").write_text(yaml.safe_dump({"permissions": grants}), encoding="utf-8")
    return folder
