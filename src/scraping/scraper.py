"""BBC article scraper.

Given a list of article URLs (sampled from each cluster), fetches the HTML
with ``requests``, parses the main body + metadata with BeautifulSoup, and
writes one JSON file per article into ``data/scraped/<category>/``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, HttpUrl


class ScrapedArticle(BaseModel):
    """Canonical shape of a scraped BBC article — produced by :func:`scrape_article`."""

    url: HttpUrl
    title: str
    category: str
    published_at: str | None
    author: str | None
    paragraphs: list[str]


def scrape_article(url: str, category: str) -> ScrapedArticle:
    """Fetch a single BBC article URL and return a :class:`ScrapedArticle`."""
    raise NotImplementedError


def scrape_batch(urls: list[str], category: str, out_dir: Path) -> list[ScrapedArticle]:
    """Scrape many URLs for one category and write each as JSON under ``out_dir/<category>/``."""
    raise NotImplementedError
