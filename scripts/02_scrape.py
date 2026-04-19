"""Stage 2: scrape full article content for a sample of clustered URLs.

Reads cluster assignments from ``data/clustered/`` and writes one JSON
per article into ``data/scraped/<category>/``.
"""

from __future__ import annotations

from src import config
from src.scraping.scraper import run_scrape


def main() -> None:
    config.ensure_dirs()
    counts = run_scrape()
    total = sum(counts.values())
    print(f"[scrape] wrote {total} articles across {len(counts)} categories")


if __name__ == "__main__":
    main()
