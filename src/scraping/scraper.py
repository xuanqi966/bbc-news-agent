"""BBC article scraper.

Given a list of article URLs (sampled from each cluster), fetches the HTML
with ``requests``, parses the main body + metadata with BeautifulSoup, and
writes one JSON file per article into ``data/scraped/<category>/``.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, HttpUrl
from tqdm import tqdm

from src import config

REQUEST_TIMEOUT_S = 15
RATE_LIMIT_SLEEP_S = 1.0
RETRY_BACKOFF_S = 2.0
EXAMPLES_PER_CATEGORY = 3
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class ScrapedArticle(BaseModel):
    """Canonical shape of a scraped BBC article — produced by :func:`scrape_article`."""

    url: HttpUrl
    title: str
    category: str
    published_at: str | None
    author: str | None
    paragraphs: list[str]


def _normalise_url(url: str) -> str:
    """Drop query string + fragment; keep scheme, host, and path."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def _slug_from_url(url: str) -> str:
    """Last path segment of the URL — stable, human-readable filename."""
    path = urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or "index"


def _fetch(url: str) -> str:
    """GET with a realistic UA, 1 retry on failure."""
    headers = {"User-Agent": USER_AGENT}
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_err = e
            if attempt == 0:
                time.sleep(RETRY_BACKOFF_S)
    assert last_err is not None
    raise last_err


def _parse_jsonld(soup: BeautifulSoup) -> dict | None:
    """Return the first NewsArticle-shaped JSON-LD block, or None."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if isinstance(c, dict) and c.get("@type") in {
                "ReportageNewsArticle",
                "NewsArticle",
                "Article",
            }:
                return c
    return None


def _extract_paragraphs(soup: BeautifulSoup) -> list[str]:
    """Body paragraphs from BBC's text-block components, with an <article> fallback."""
    paragraphs: list[str] = []
    for block in soup.find_all("div", attrs={"data-component": "text-block"}):
        for p in block.find_all("p"):
            text = p.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
    if paragraphs:
        return paragraphs
    article = soup.find("article")
    if not article:
        return []
    for bad in article.find_all(["figure", "aside"]):
        bad.decompose()
    return [
        p.get_text(" ", strip=True)
        for p in article.find_all("p")
        if p.get_text(strip=True)
    ]


def _extract_title(soup: BeautifulSoup, jsonld: dict | None) -> str | None:
    if jsonld and isinstance(jsonld.get("headline"), str):
        return jsonld["headline"].strip()
    h1 = soup.find("h1", id="main-heading") or soup.find("h1")
    return h1.get_text(strip=True) if h1 else None


def _extract_published_at(soup: BeautifulSoup, jsonld: dict | None) -> str | None:
    if jsonld and isinstance(jsonld.get("datePublished"), str):
        return jsonld["datePublished"]
    time_tag = soup.find("time")
    if isinstance(time_tag, Tag) and time_tag.get("datetime"):
        return str(time_tag["datetime"])
    return None


def _extract_author(jsonld: dict | None) -> str | None:
    if not jsonld:
        return None
    author = jsonld.get("author")
    if isinstance(author, dict) and isinstance(author.get("name"), str):
        return author["name"]
    if isinstance(author, list) and author and isinstance(author[0], dict):
        name = author[0].get("name")
        return name if isinstance(name, str) else None
    if isinstance(author, str):
        return author
    return None


def scrape_article(url: str, category: str) -> ScrapedArticle:
    """Fetch one BBC article URL and return a validated :class:`ScrapedArticle`."""
    normalised = _normalise_url(url)
    html = _fetch(normalised)
    soup = BeautifulSoup(html, "html.parser")
    jsonld = _parse_jsonld(soup)
    title = _extract_title(soup, jsonld)
    paragraphs = _extract_paragraphs(soup)
    if not title or not paragraphs:
        raise ValueError(f"empty title or paragraphs for {normalised!r}")
    return ScrapedArticle(
        url=normalised,
        title=title,
        category=category,
        published_at=_extract_published_at(soup, jsonld),
        author=_extract_author(jsonld),
        paragraphs=paragraphs,
    )


def scrape_batch(urls: list[str], category: str, out_dir: Path) -> list[ScrapedArticle]:
    """Scrape many URLs for one category; write each as JSON; return the successes.

    Idempotent: URLs whose ``<slug>.json`` already exists under ``out_dir/<category>/``
    are skipped without a network call. Per-URL failures are logged and skipped;
    remaining URLs still run.
    """
    cat_dir = out_dir / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    results: list[ScrapedArticle] = []
    for url in tqdm(urls, desc=f"[scrape] {category}", unit="article"):
        slug = _slug_from_url(_normalise_url(url))
        out_path = cat_dir / f"{slug}.json"
        if out_path.exists():
            continue
        try:
            article = scrape_article(url, category)
        except Exception as e:
            print(f"[scrape] {category}/{slug}: failed ({e!r}) — skipped")
            continue
        out_path.write_text(article.model_dump_json(indent=2))
        results.append(article)
        time.sleep(RATE_LIMIT_SLEEP_S)
    return results


def _stage_examples(
    manifest: dict[str, list[str]],
    scraped_dir: Path,
    examples_dir: Path,
    n: int = EXAMPLES_PER_CATEGORY,
) -> None:
    """Copy up to ``n`` scraped articles per category into ``examples_dir``.

    Selection is deterministic: the first ``n`` URLs per category in the
    manifest whose scraped JSON file exists. Idempotent — skips files that
    already exist at the destination.
    """
    for category, urls in manifest.items():
        dest_dir = examples_dir / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        staged = 0
        for url in urls:
            if staged >= n:
                break
            slug = _slug_from_url(_normalise_url(url))
            src = scraped_dir / category / f"{slug}.json"
            if not src.exists():
                continue
            dst = dest_dir / f"{slug}.json"
            if not dst.exists():
                shutil.copy(src, dst)
            staged += 1
        if staged < n:
            print(
                f"[scrape] {category}: staged only {staged} / {n} examples "
                f"(fewer scraped articles than target)"
            )
        else:
            print(f"[scrape] {category}: staged {staged} examples to {dest_dir}")


def run_scrape(
    manifest_path: Path | None = None,
    out_dir: Path | None = None,
    examples_dir: Path | None = None,
) -> dict[str, int]:
    """Read the cluster manifest and scrape every URL in every category.

    Manifest shape: ``{"<category>": ["<url>", ...], ...}`` at
    ``data/clustered/sample.json`` by default. Returns per-category success counts.
    After scraping, stages a small subset (3 per category) to
    ``data/examples/<category>/`` as few-shot context for the future QA agent.
    """
    manifest_path = manifest_path or (config.CLUSTERED_DIR / "sample.json")
    out_dir = out_dir or config.SCRAPED_DIR
    examples_dir = examples_dir or config.EXAMPLES_DIR
    manifest: dict[str, list[str]] = json.loads(manifest_path.read_text())
    counts: dict[str, int] = {}
    for category, urls in manifest.items():
        articles = scrape_batch(urls, category, out_dir)
        counts[category] = len(articles)
        print(f"[scrape] {category}: wrote {len(articles)} / {len(urls)} articles")
    _stage_examples(manifest, out_dir, examples_dir)
    return counts
