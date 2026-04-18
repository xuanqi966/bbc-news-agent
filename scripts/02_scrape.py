"""Stage 2: scrape full article content for a sample of clustered URLs.

Reads cluster assignments from ``data/clustered/`` and writes one JSON
per article into ``data/scraped/<category>/``.
"""

from __future__ import annotations

from src import config


def main() -> None:
    config.ensure_dirs()
    raise NotImplementedError


if __name__ == "__main__":
    main()
