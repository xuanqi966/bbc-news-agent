"""Smoke tests — provider selection wiring and the core scraped-article contract.

Deliberately small: the project is research-scale and most modules need real
LLM calls to exercise fully. These check the bits that are cheap to verify
and expensive to get wrong.
"""

from __future__ import annotations

import pytest

from src import config
from src.llm.anthropic import AnthropicProvider
from src.llm.factory import get_provider
from src.llm.openrouter import OpenRouterProvider
from src.scraping.scraper import ScrapedArticle


def test_get_provider_prefers_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-test-or")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test-anthropic")
    assert isinstance(get_provider(), OpenRouterProvider)


def test_get_provider_falls_back_to_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test-anthropic")
    assert isinstance(get_provider(), AnthropicProvider)


def test_get_provider_raises_when_neither_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    with pytest.raises(RuntimeError, match="No LLM provider configured"):
        get_provider()


def test_scraped_article_roundtrip() -> None:
    article = ScrapedArticle(
        url="https://www.bbc.co.uk/news/articles/cxyz123",
        title="Example headline",
        category="politics",
        published_at="2026-04-19T10:00:00Z",
        author="Jane Doe",
        paragraphs=["First paragraph.", "Second paragraph."],
    )
    reloaded = ScrapedArticle.model_validate_json(article.model_dump_json())
    assert reloaded == article


def test_scraped_article_allows_null_metadata() -> None:
    """`published_at` and `author` are Optional — BBC JSON-LD sometimes omits them."""
    article = ScrapedArticle.model_validate(
        {
            "url": "https://www.bbc.co.uk/news/articles/cxyz123",
            "title": "Headline",
            "category": "world",
            "published_at": None,
            "author": None,
            "paragraphs": ["Body."],
        }
    )
    assert article.published_at is None
    assert article.author is None
