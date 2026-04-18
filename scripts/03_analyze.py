"""Stage 3: run static + semantic analysis over scraped articles.

Produces ``analysis/static/stats.json`` and one ``analysis/semantic/<category>.md``
per category.
"""

from __future__ import annotations

from src import config


def main() -> None:
    config.ensure_dirs()
    raise NotImplementedError


if __name__ == "__main__":
    main()
