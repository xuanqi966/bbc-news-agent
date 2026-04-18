"""LLM-based qualitative style analysis, one Markdown file per category.

For each category, samples a handful of scraped articles and asks the LLM
to characterise tone, structure, vocabulary, framing, sourcing conventions,
etc. Writes ``analysis/semantic/<category>.md``.
"""

from __future__ import annotations

from pathlib import Path


def build_semantic_prompt(category: str, articles: list) -> str:
    """Return the user prompt that asks the LLM to characterise this category's style."""
    raise NotImplementedError


def analyze_category(category: str, articles: list) -> str:
    """Run the semantic analysis LLM call for one category and return the Markdown report."""
    raise NotImplementedError


def run_semantic_analysis(scraped_dir: Path, out_dir: Path) -> None:
    """Walk each category under ``scraped_dir`` and write ``<category>.md`` into ``out_dir``."""
    raise NotImplementedError
