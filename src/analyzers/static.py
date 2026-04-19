"""Deterministic, non-LLM text statistics for scraped articles.

Computes per-article numeric stats, aggregates them by category into
percentile distributions, and renders a short prose brief that the style
guide generator consumes directly (the LLM never sees the raw JSON).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from src import config
from src.scraping.scraper import ScrapedArticle

_QUOTE_RE = re.compile(r'"[^"]{2,}?"|\u201c[^\u201d]{2,}?\u201d')
_SENT_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\u201c])')


class NumericDistribution(BaseModel):
    """Percentile distribution for a single numeric stat across a category."""

    p25: float
    p50: float
    p75: float


class CategoryStats(BaseModel):
    """Aggregated style-relevant stats for one category (or the overall corpus)."""

    category: str
    article_count: int
    word_count: NumericDistribution
    paragraph_length_words: NumericDistribution
    sentence_length_words: NumericDistribution
    quotes_per_article: NumericDistribution
    headline_word_count: NumericDistribution
    lede_word_count: NumericDistribution


class StaticStats(BaseModel):
    """Root of analysis/static/stats.json — per-category plus corpus-wide overall."""

    categories: list[CategoryStats]
    overall: CategoryStats


class _ArticleStats(BaseModel):
    """Per-article intermediate — flattened into category aggregates, never serialised."""

    category: str
    word_count: int
    headline_word_count: int
    lede_word_count: int
    quotes_per_article: int
    paragraph_lengths: list[int]
    sentence_lengths: list[int]


def _render_block(c: CategoryStats, label: str | None = None) -> str:
    name = label or c.category
    return (
        f"**{name}** ({c.article_count} articles). "
        f"Typical length {int(c.word_count.p25)}–{int(c.word_count.p75)} words "
        f"(median {int(c.word_count.p50)}). "
        f"Paragraphs {int(c.paragraph_length_words.p25)}–{int(c.paragraph_length_words.p75)} words. "
        f"Sentences {int(c.sentence_length_words.p25)}–{int(c.sentence_length_words.p75)} words. "
        f"Headlines {int(c.headline_word_count.p25)}–{int(c.headline_word_count.p75)} words. "
        f"Ledes {int(c.lede_word_count.p25)}–{int(c.lede_word_count.p75)} words. "
        f"Direct quotes {int(c.quotes_per_article.p25)}–{int(c.quotes_per_article.p75)} per article."
    )


def render_stats_brief(stats: StaticStats) -> str:
    """Render :class:`StaticStats` as prose suitable for direct LLM consumption."""
    blocks = [_render_block(stats.overall, label="Overall")]
    for c in stats.categories:
        blocks.append(_render_block(c))
    return "\n\n".join(blocks)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def compute_article_stats(article: ScrapedArticle) -> _ArticleStats:
    """Compute raw numeric stats for a single scraped article."""
    paragraphs = [p for p in article.paragraphs if p.strip()]
    body = "\n\n".join(paragraphs)
    sentences = _split_sentences(body)
    return _ArticleStats(
        category=article.category,
        word_count=sum(len(p.split()) for p in paragraphs),
        headline_word_count=len(article.title.split()),
        lede_word_count=len(paragraphs[0].split()) if paragraphs else 0,
        quotes_per_article=len(_QUOTE_RE.findall(body)),
        paragraph_lengths=[len(p.split()) for p in paragraphs],
        sentence_lengths=[len(s.split()) for s in sentences],
    )


def _dist(values: list[float]) -> NumericDistribution:
    arr = np.array(values) if values else np.array([0.0])
    return NumericDistribution(
        p25=float(np.percentile(arr, 25)),
        p50=float(np.percentile(arr, 50)),
        p75=float(np.percentile(arr, 75)),
    )


def _aggregate(stats: list[_ArticleStats], label: str) -> CategoryStats:
    return CategoryStats(
        category=label,
        article_count=len(stats),
        word_count=_dist([s.word_count for s in stats]),
        paragraph_length_words=_dist([n for s in stats for n in s.paragraph_lengths]),
        sentence_length_words=_dist([n for s in stats for n in s.sentence_lengths]),
        quotes_per_article=_dist([s.quotes_per_article for s in stats]),
        headline_word_count=_dist([s.headline_word_count for s in stats]),
        lede_word_count=_dist([s.lede_word_count for s in stats]),
    )


def aggregate_by_category(article_stats: list[_ArticleStats]) -> StaticStats:
    """Reduce per-article stats into per-category NumericDistributions + overall."""
    by_cat: dict[str, list[_ArticleStats]] = defaultdict(list)
    for s in article_stats:
        by_cat[s.category].append(s)
    categories = [_aggregate(v, k) for k, v in sorted(by_cat.items())]
    overall = _aggregate(article_stats, "overall")
    return StaticStats(categories=categories, overall=overall)


def run_static_analysis(
    scraped_dir: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """Walk scraped articles, compute stats, write ``stats.json``, return its path."""
    scraped_dir = scraped_dir or config.SCRAPED_DIR
    out_path = out_path or (config.STATIC_ANALYSIS_DIR / "stats.json")

    article_stats: list[_ArticleStats] = []
    for cat_dir in sorted(p for p in scraped_dir.iterdir() if p.is_dir()):
        for f in sorted(cat_dir.glob("*.json")):
            article = ScrapedArticle.model_validate_json(f.read_text())
            article_stats.append(compute_article_stats(article))

    stats = aggregate_by_category(article_stats)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stats.model_dump_json(indent=2))
    print(
        f"[static] wrote {out_path.name} "
        f"({len(article_stats)} articles across {len(stats.categories)} categories)"
    )
    return out_path
