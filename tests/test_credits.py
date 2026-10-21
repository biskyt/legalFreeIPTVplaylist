from freeplaylist import config, credits


def test_every_configured_source_has_a_credit():
    sources = set(config.load("credits")["sources"])
    used = {"iptv-org", "internet-archive", "wikimedia-commons"}
    used |= {p["credit"] for p in config.load("live_hosts")["platforms"]}
    cur = config.load("curated")
    used.add(cur["ia_defaults"]["source"])
    used |= {i["source"] for i in cur.get("ia_movies", []) if "source" in i}
    used |= {i["source"] for i in cur.get("direct", [])}
    assert used <= sources, used - sources


def test_readme_credits_are_current():
    text = (config.ROOT / "README.md").read_text(encoding="utf-8")
    section = credits.readme_section(config.load("credits")["sources"])
    assert f"{credits.START}\n{section}\n{credits.END}" in text, "run: python -m freeplaylist credits"


def test_missing_credit_detected(entry):
    assert credits.missing([entry(source="nobody")], {"iptv-org": {}}) == {"nobody"}
