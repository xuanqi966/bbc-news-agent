"""Stage 1: cluster raw BBC articles by topic.

Reads CSVs from ``data/raw/`` and writes cluster assignments + top terms
into ``data/clustered/``.
"""

from __future__ import annotations

from src import config
from src.clustering.cluster import run_clustering


def main() -> None:
    config.ensure_dirs()
    path = run_clustering()
    print(f"[cluster] manifest written to {path}")


if __name__ == "__main__":
    main()
