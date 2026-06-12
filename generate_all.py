#!/usr/bin/env python3
"""
generate_all.py — run all registered scrapers and write feeds/ directory.

Usage:
    python generate_all.py            # run everything
    python generate_all.py levin-lab  # run only scrapers whose slug matches
"""

import sys
import traceback
from pathlib import Path

FEEDS_DIR = Path(__file__).parent / "feeds"
FEEDS_DIR.mkdir(exist_ok=True)

# Import the registry
from scrapers import ALL_SCRAPERS


def main():
    filter_slugs = set(sys.argv[1:])

    results = {"ok": [], "failed": []}

    for scraper in ALL_SCRAPERS:
        slug = scraper.FEED_SLUG

        if filter_slugs and not any(f in slug for f in filter_slugs):
            print(f"[{slug}] skipped (not in filter)")
            continue

        try:
            scraper.write_feed(FEEDS_DIR)
            results["ok"].append(slug)
        except Exception:
            print(f"[{slug}] FAILED:")
            traceback.print_exc()
            results["failed"].append(slug)

    print()
    print(f"Done — {len(results['ok'])} succeeded, {len(results['failed'])} failed.")
    if results["failed"]:
        print("Failed:", ", ".join(results["failed"]))
        sys.exit(1)


if __name__ == "__main__":
    main()
