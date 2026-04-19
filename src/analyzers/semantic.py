"""LLM-based qualitative style analysis, one Markdown file per category.

For each category, samples up to ``SAMPLE_SIZE`` scraped articles and asks
the LLM to characterise tone, structure, vocabulary, sourcing, and
distinctive markers, grounded in verbatim phrases from the source. The
structured :class:`SemanticProfile` is rendered to
``analysis/semantic/<category>.md`` for the style guide generator to consume.
"""

from __future__ import annotations

import random
from pathlib import Path

from pydantic import BaseModel, Field

from src import config
from src.llm import LLMProvider, get_provider
from src.llm.tracing import traced
from src.scraping.scraper import ScrapedArticle

SAMPLE_SIZE = 5
SAMPLE_SEED = 42

SEMANTIC_SYSTEM_PROMPT = (
    "You are a newsroom style analyst. Examine the supplied BBC articles from a single "
    "category and characterise recurring style patterns. Be specific and grounded: every "
    "claim must reflect something observable across the samples — do not offer generic "
    "journalism advice. For example_phrases, quote 3–6 short phrases verbatim from the "
    "articles that ground your observations."
)


class SemanticObservations(BaseModel):
    """Fields the LLM fills from sample articles.

    Wrapped into a :class:`SemanticProfile` with deterministic ``category`` and
    ``sample_urls``; those two are not asked of the LLM.
    """

    tone_and_voice: str
    structure_and_framing: str
    vocabulary_and_register: str
    sourcing_and_attribution: str
    distinctive_markers: str
    example_phrases: list[str]


class SemanticProfile(BaseModel):
    """Structured per-category style observations. Rendered to markdown on disk."""

    category: str
    tone_and_voice: str = Field(
        ..., description="1–2 short paragraphs characterising tone and voice."
    )
    structure_and_framing: str = Field(
        ...,
        description=(
            "Headline → lede → body → close patterns; whether pieces are "
            "hard-news, feature, or explainer, and how they orient the reader."
        ),
    )
    vocabulary_and_register: str = Field(
        ..., description="Register, formality, jargon density, contractions, etc."
    )
    sourcing_and_attribution: str = Field(
        ...,
        description="Attribution conventions — 'said' vs 'claimed', named vs anonymous sources, etc.",
    )
    distinctive_markers: str = Field(
        ..., description="Signature turns of phrase or recurring rhetorical moves."
    )
    example_phrases: list[str] = Field(
        ...,
        description="3–6 short phrases drawn verbatim from source articles that ground the above.",
    )
    sample_urls: list[str]


def render_markdown(profile: SemanticProfile) -> str:
    """Render a :class:`SemanticProfile` into the canonical <category>.md layout."""
    lines = [
        f"# Style notes: {profile.category}",
        "",
        "## Tone & voice",
        profile.tone_and_voice.strip(),
        "",
        "## Structure & framing",
        profile.structure_and_framing.strip(),
        "",
        "## Vocabulary & register",
        profile.vocabulary_and_register.strip(),
        "",
        "## Sourcing & attribution",
        profile.sourcing_and_attribution.strip(),
        "",
        "## Distinctive markers",
        profile.distinctive_markers.strip(),
        "",
        "## Example phrases",
    ]
    for phrase in profile.example_phrases:
        lines.append(f'- "{phrase}"')
    lines.append("")
    lines.append("## Sources")
    for url in profile.sample_urls:
        lines.append(f"- {url}")
    lines.append("")
    return "\n".join(lines)


def _sample_articles(articles: list[ScrapedArticle]) -> list[ScrapedArticle]:
    """Deterministic sample of up to ``SAMPLE_SIZE`` articles."""
    if len(articles) <= SAMPLE_SIZE:
        return articles
    rng = random.Random(SAMPLE_SEED)
    return rng.sample(articles, SAMPLE_SIZE)


def _render_article_for_prompt(article: ScrapedArticle, idx: int) -> str:
    body = "\n\n".join(article.paragraphs)
    return f"--- Article {idx} ---\nTitle: {article.title}\nURL: {article.url}\n\n{body}"


def build_semantic_prompt(category: str, articles: list[ScrapedArticle]) -> str:
    """Assemble the user prompt — category header + full-text article samples."""
    rendered = [_render_article_for_prompt(a, i + 1) for i, a in enumerate(articles)]
    return (
        f"Category: {category}\n"
        f"Samples ({len(articles)} articles):\n\n"
        + "\n\n".join(rendered)
    )


@traced("semantic_analyzer")
def analyze_category(
    category: str,
    articles: list[ScrapedArticle],
    provider: LLMProvider | None = None,
) -> SemanticProfile:
    """Run the semantic LLM call for one category and return a full profile."""
    if not articles:
        raise ValueError(f"No articles for category {category!r}")
    provider = provider or get_provider()
    sample = _sample_articles(articles)
    observations = provider.complete_structured(
        system=SEMANTIC_SYSTEM_PROMPT,
        user=build_semantic_prompt(category, sample),
        schema=SemanticObservations,
        temperature=0.2,
    )
    return SemanticProfile(
        category=category,
        sample_urls=[str(a.url) for a in sample],
        **observations.model_dump(),
    )


def _load_category_articles(category_dir: Path) -> list[ScrapedArticle]:
    return [
        ScrapedArticle.model_validate_json(p.read_text())
        for p in sorted(category_dir.glob("*.json"))
    ]


def run_semantic_analysis(
    scraped_dir: Path | None = None,
    out_dir: Path | None = None,
    provider: LLMProvider | None = None,
) -> list[Path]:
    """Walk each category under ``scraped_dir`` and write ``<category>.md`` into ``out_dir``.

    Categories with no articles are skipped. A failed LLM call for one
    category is logged and skipped; remaining categories still run.
    Returns the list of files successfully written.
    """
    scraped_dir = scraped_dir or config.SCRAPED_DIR
    out_dir = out_dir or config.SEMANTIC_ANALYSIS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for category_dir in sorted(p for p in scraped_dir.iterdir() if p.is_dir()):
        category = category_dir.name
        articles = _load_category_articles(category_dir)
        if not articles:
            print(f"[semantic] {category}: skipped (no articles)")
            continue
        try:
            profile = analyze_category(category, articles, provider=provider)
        except Exception as e:
            print(f"[semantic] {category}: failed ({e!r}) — skipped")
            continue
        out_path = out_dir / f"{category}.md"
        out_path.write_text(render_markdown(profile))
        written.append(out_path)
        print(
            f"[semantic] {category}: wrote {out_path.name} "
            f"({len(profile.sample_urls)} samples)"
        )
    return written
