"""Stage 1: cluster raw BBC articles by topic.

Reads CSVs from ``data/raw/`` and writes cluster assignments + top terms
into ``data/clustered/``.
"""

from __future__ import annotations

from src import config


def main() -> None:
    config.ensure_dirs()
    raise NotImplementedError


if __name__ == "__main__":
    main()
