"""Stage 1: classify raw BBC articles into a fixed taxonomy.

Two paths:

1. **Regex on URL path** (deterministic, no LLM cost) — covers ~75% of the
   corpus, since pre-2024Q2 BBC URLs encode the section
   (``/news/business-…``, ``/sport/football/…``, ``/news/science-…``).
2. **Batched LLM classification** on ``(title, description)`` — handles the
   headerless ~25% (BBC's post-2024Q2 UUID-style URLs and bare-numeric slugs).

Produces the scraper's manifest ``data/clustered/sample.json`` with shape
``{category: [urls]}``, ≤20 URLs per category, mixing 12 headered + 8
headerless where available. Also writes a debug ``assignments.csv``.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from src import config
from src.llm import LLMProvider, get_provider
from src.llm.tracing import traced
from src.scraping.scraper import _normalise_url

SEED = 42
SAMPLE_PER_CATEGORY = 20
HEADERED_TARGET = 12
HEADERLESS_TARGET = 8
CANDIDATE_OVERSAMPLE = 3
LLM_BATCH_SIZE = 50

TAXONOMY = [
    "politics",
    "business",
    "technology",
    "science",
    "health",
    "sports",
    "world",
    "entertainment",
    "uk_news",
    "other",
]

HEADERLESS_PATTERNS = [
    re.compile(r"/news/articles/c[a-z0-9]+", re.IGNORECASE),
    re.compile(r"/news/\d+(?:/|$|\?)"),
]

MISC_PATH_TOKENS = (
    "/sounds/",
    "/weather/",
    "/in-pictures/",
    "/blogs-the-papers/",
    "/newsbeat/",
    "/news/videos/",
)


def classify_url(url: str) -> str | None:
    """Classify a BBC URL by path.

    Returns a taxonomy label, or ``None`` if the URL has no category signal
    (headerless — caller should fall back to title/description classification).
    """
    path = _normalise_url(url).lower()

    for pat in HEADERLESS_PATTERNS:
        if pat.search(path):
            return None

    if "/sport/" in path:
        return "sports"
    if "politics" in path:
        return "politics"
    if "/news/world-" in path:
        return "world"
    if "/news/business-" in path:
        return "business"
    if "/news/health-" in path:
        return "health"
    if "/news/science-" in path:
        return "science"
    if "/news/technology-" in path:
        return "technology"
    if "/news/entertainment-" in path:
        return "entertainment"
    if "/news/uk-" in path:
        return "uk_news"
    if any(tok in path for tok in MISC_PATH_TOKENS):
        return "other"
    return "other"


LLM_SYSTEM_PROMPT = (
    "You classify BBC News articles into a fixed taxonomy. "
    f"The allowed labels are: {', '.join(TAXONOMY)}. "
    "Given a numbered list of articles (title + short description), "
    "return exactly one label per article, in the same order. "
    "Use 'other' only when none of the substantive labels fit. "
    "Use 'uk_news' for UK domestic stories that are not specifically politics. "
    "Use 'world' for international stories outside the UK."
)


class ClassifyBatch(BaseModel):
    """LLM output: one taxonomy label per input item, parallel to input order."""

    labels: list[str] = Field(
        ...,
        description="One taxonomy label per input article, in the same order.",
    )


def _build_classification_prompt(items: list[tuple[str, str]]) -> str:
    parts = [f"Classify these {len(items)} articles. Return one label per article, in order.", ""]
    for i, (title, desc) in enumerate(items):
        parts.append(f"{i + 1}. Title: {title}")
        if desc:
            parts.append(f"   Description: {desc}")
    return "\n".join(parts)


@traced("cluster_classifier")
def _classify_batch_via_llm(
    items: list[tuple[str, str]], provider: LLMProvider
) -> list[str]:
    """Classify one batch. Never raises — failed batches return 'other'."""
    if not items:
        return []
    try:
        result = provider.complete_structured(
            system=LLM_SYSTEM_PROMPT,
            user=_build_classification_prompt(items),
            schema=ClassifyBatch,
            temperature=0.0,
        )
    except Exception as e:
        print(f"[cluster] LLM batch failed ({e!r}) — defaulting {len(items)} items to 'other'")
        return ["other"] * len(items)

    labels = result.labels
    if len(labels) != len(items):
        print(
            f"[cluster] LLM returned {len(labels)} labels (expected {len(items)}) "
            "— defaulting batch to 'other'"
        )
        return ["other"] * len(items)

    cleaned: list[str] = []
    for lab in labels:
        if lab in TAXONOMY:
            cleaned.append(lab)
        else:
            print(f"[cluster] out-of-taxonomy label {lab!r} — coerced to 'other'")
            cleaned.append("other")
    return cleaned


def _sample(urls: list[str], n: int, rng: random.Random) -> list[str]:
    if len(urls) <= n:
        return sorted(urls)
    return rng.sample(sorted(urls), n)


def run_clustering(
    raw_path: Path | None = None,
    out_dir: Path | None = None,
    provider: LLMProvider | None = None,
) -> Path:
    """Classify, sample, and write ``sample.json`` + ``assignments.csv``.

    Returns the path to ``sample.json`` (the scraper's input manifest).
    """
    raw_path = raw_path or (config.RAW_DIR / "bbc_news.csv")
    out_dir = out_dir or config.CLUSTERED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(raw_path)
    df = df.drop_duplicates(subset=["guid"]).reset_index(drop=True)
    print(f"[cluster] loaded {len(df)} unique articles from {raw_path.name}")

    df["regex_label"] = df["guid"].astype(str).map(classify_url)
    headered_mask = df["regex_label"].notna()
    headerless_df = df[~headered_mask].reset_index(drop=True)
    print(
        f"[cluster] Path A (regex): {headered_mask.sum()} headered, "
        f"{len(headerless_df)} headerless"
    )

    rng = random.Random(SEED)

    headered_by_cat: dict[str, list[str]] = defaultdict(list)
    for url, lab in zip(df.loc[headered_mask, "guid"], df.loc[headered_mask, "regex_label"]):
        headered_by_cat[lab].append(url)
    for cat in TAXONOMY:
        headered_by_cat.setdefault(cat, [])
    print("[cluster] Path A counts per label: " +
          ", ".join(f"{c}={len(headered_by_cat[c])}" for c in TAXONOMY))

    headerless_label_map: dict[str, str] = {}
    if len(headerless_df):
        target_candidates = SAMPLE_PER_CATEGORY * len(TAXONOMY) * CANDIDATE_OVERSAMPLE
        n = min(target_candidates, len(headerless_df))
        candidate_idx = rng.sample(range(len(headerless_df)), n)
        candidate_idx.sort()
        candidates = headerless_df.iloc[candidate_idx].reset_index(drop=True)
        items = [
            (
                str(row["title"] or ""),
                str(row["description"] or "") if pd.notna(row["description"]) else "",
            )
            for _, row in candidates.iterrows()
        ]
        provider = provider or get_provider()
        print(
            f"[cluster] Path B: classifying {len(items)} headerless candidates "
            f"in batches of {LLM_BATCH_SIZE}"
        )
        labels_out: list[str] = []
        for start in range(0, len(items), LLM_BATCH_SIZE):
            chunk = items[start : start + LLM_BATCH_SIZE]
            labels_out.extend(_classify_batch_via_llm(chunk, provider))
        for url, lab in zip(candidates["guid"].tolist(), labels_out):
            headerless_label_map[url] = lab
        counts = defaultdict(int)
        for lab in labels_out:
            counts[lab] += 1
        print("[cluster] Path B counts per label: " +
              ", ".join(f"{c}={counts[c]}" for c in TAXONOMY))

    headerless_by_cat: dict[str, list[str]] = defaultdict(list)
    for url, lab in headerless_label_map.items():
        headerless_by_cat[lab].append(url)

    sample: dict[str, list[str]] = {}
    for cat in TAXONOMY:
        headerless_picks = _sample(headerless_by_cat.get(cat, []), HEADERLESS_TARGET, rng)
        remaining = SAMPLE_PER_CATEGORY - len(headerless_picks)
        headered_picks = _sample(headered_by_cat.get(cat, []), remaining, rng)
        combined = headered_picks + headerless_picks
        sample[cat] = [_normalise_url(u) for u in combined]

    sample_path = out_dir / "sample.json"
    sample_path.write_text(json.dumps(sample, indent=2))
    total = sum(len(v) for v in sample.values())
    print(f"[cluster] wrote {sample_path.name} ({total} URLs across {len(sample)} categories)")
    for cat in TAXONOMY:
        print(f"[cluster]   {cat}: {len(sample[cat])}")

    def _final_label(row) -> tuple[str, str]:
        if pd.notna(row["regex_label"]):
            return row["regex_label"], "regex"
        lab = headerless_label_map.get(row["guid"])
        if lab is not None:
            return lab, "llm"
        return "unclassified", "fallback"

    labels_and_sources = df.apply(_final_label, axis=1)
    assignments = df[["guid", "title"]].copy()
    assignments["category"] = [x[0] for x in labels_and_sources]
    assignments["source"] = [x[1] for x in labels_and_sources]
    assignments.to_csv(out_dir / "assignments.csv", index=False)

    return sample_path
