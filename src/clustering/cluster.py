"""TF-IDF + KMeans clustering over BBC article titles/descriptions.

Reads the raw CSV from ``data/raw/``, clusters rows by TF-IDF vectors of
``title`` + ``description``, and writes per-cluster assignments plus the
top terms per cluster into ``data/clustered/``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ClusterResult(BaseModel):
    """Summary of a single cluster: its id, size, and characteristic terms."""

    cluster_id: int
    size: int
    top_terms: list[str]


def load_raw_csv(csv_path: Path):
    """Load the raw BBC article CSV into a DataFrame (titles + descriptions)."""
    raise NotImplementedError


def cluster_articles(df, n_clusters: int) -> list[ClusterResult]:
    """Run TF-IDF + KMeans and return per-cluster summaries."""
    raise NotImplementedError


def write_cluster_output(df, results: list[ClusterResult], out_dir: Path) -> None:
    """Persist cluster assignments and top terms to ``data/clustered/``."""
    raise NotImplementedError
