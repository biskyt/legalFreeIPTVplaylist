"""Command line: `python -m freeplaylist build` and `python -m freeplaylist credits`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import build, config, credits, epg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="freeplaylist")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build the playlists into a site directory")
    b.add_argument("--out", type=Path, default=Path("site"))
    b.add_argument("--state", type=Path, default=Path("state"), help="cache kept between runs")
    b.add_argument("--api-dir", type=Path, help="use a local copy of the iptv-org API")
    b.add_argument("--no-health", action="store_true", help="skip stream health checks")
    b.add_argument("--no-website-check", action="store_true", help="don't fetch broadcasters' websites")
    b.add_argument("--live-only", action="store_true")
    b.add_argument("--vod-only", action="store_true")
    b.add_argument("--all", action="store_true", help="harvest and check everything, ignoring config/schedule.yaml")
    b.add_argument("--only", help="staged run: harvest only these comma-separated sources; the rest come from "
                                  f"their snapshots ({', '.join(build.SOURCES)})")
    b.add_argument("--no-minimums", action="store_true", help="don't fail on small feeds (partial builds)")

    c = sub.add_parser("credits", help="regenerate the README credits section from config/credits.yaml")
    c.add_argument("--check", action="store_true", help="fail if the README is out of date instead of writing")
    c.add_argument("--readme", type=Path, default=config.ROOT / "README.md")

    g = sub.add_parser("epg", help="build the TV guide from the plan the last build wrote (after the grabber ran)")
    g.add_argument("--state", type=Path, default=Path("state"))
    g.add_argument("--out", type=Path, default=Path("site/epg.xml.gz"))
    g.add_argument("--grabbed", type=Path, help="tonight's iptv-org/epg grabber output (.xml.gz)")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if args.command == "epg":
        count = epg.merge(args.state, args.out, args.grabbed)
        print(f"guide: {count} channels")
        return 0 if count else 1

    if args.command == "credits":
        sources = config.load("credits").get("sources") or {}
        if args.check:
            text = args.readme.read_text(encoding="utf-8")
            if f"{credits.START}\n{credits.readme_section(sources)}\n{credits.END}" not in text:
                print("README credits are out of date: run `python -m freeplaylist credits`", file=sys.stderr)
                return 1
            return 0
        changed = credits.update_readme(args.readme, sources)
        print("README updated" if changed else "README already up to date")
        return 0

    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else None
    if only and only - set(build.SOURCES):
        parser.error(f"unknown sources: {', '.join(sorted(only - set(build.SOURCES)))}")
    opts = build.Options(
        out=args.out, state_dir=args.state, api_dir=args.api_dir, health=not args.no_health,
        website_check=not args.no_website_check,
        live=not args.vod_only, vod=not args.live_only, all=args.all, only=only,
        enforce_minimums=not (args.no_minimums or args.live_only or args.vod_only),
    )
    try:
        result = build.run(opts)
    except build.BuildError as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    for name, feed in result.feeds.items():
        print(f"{name}.m3u: {len(feed.entries)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
