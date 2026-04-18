"""Merge static stats + per-category semantic notes into the final style guide.

Consumes ``analysis/static/stats.json`` plus every ``analysis/semantic/*.md``
and produces a single, agent-usable style guide at ``output/style_guide.md``.
"""

from __future__ import annotations

from pathlib import Path


def load_static_stats(stats_path: Path) -> dict:
    """Load the static stats JSON emitted by :mod:`src.analyzers.static`."""
    raise NotImplementedError


def load_semantic_notes(semantic_dir: Path) -> dict[str, str]:
    """Load every ``<category>.md`` file in ``semantic_dir`` keyed by category."""
    raise NotImplementedError


def build_style_guide(stats: dict, semantic_notes: dict[str, str]) -> str:
    """Produce the final Markdown style guide string from static + semantic inputs."""
    raise NotImplementedError


def generate_style_guide(stats_path: Path, semantic_dir: Path, out_path: Path) -> None:
    """End-to-end: read inputs, build guide, write ``output/style_guide.md``."""
    raise NotImplementedError
