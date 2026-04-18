"""Deterministic, non-LLM text statistics for scraped articles.

Computes counts (words, paragraphs, quotes, sentences, etc.) per article
and aggregates them by category. Writes ``analysis/static/stats.json``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ArticleStats(BaseModel):
    """Per-article text stats — see :func:`compute_article_stats`."""

    url: str
    category: str
    word_count: int
    paragraph_count: int
    sentence_count: int
    quote_count: int
    avg_sentence_length: float
    avg_paragraph_length: float


class CategoryStats(BaseModel):
    """Category-level aggregates across all articles in a category."""

    category: str
    article_count: int
    mean_word_count: float
    mean_paragraph_count: float
    mean_sentence_count: float
    mean_quote_count: float


def compute_article_stats(article) -> ArticleStats:
    """Compute stats for a single scraped article."""
    raise NotImplementedError


def aggregate_by_category(stats: list[ArticleStats]) -> list[CategoryStats]:
    """Reduce per-article stats into per-category aggregates."""
    raise NotImplementedError


def run_static_analysis(scraped_dir: Path, out_path: Path) -> None:
    """Walk scraped articles, compute stats, write ``stats.json`` to ``out_path``."""
    raise NotImplementedError
