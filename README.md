# BBC News Article Style Analyzer & Generator

A multi-agent system that:

1. Clusters a dataset of BBC news articles by topic.
2. Scrapes full article content for a sampled subset.
3. Analyzes the scraped articles — both statically (word counts, paragraph counts, quote counts, etc.) and semantically (LLM-driven qualitative analysis per category).
4. Merges the analyses into a single style guide.
5. Uses a planner / writer / editor agent pipeline to generate new BBC-style articles on user-supplied topics, grounded in that style guide.

## Setup

```bash
# Python 3.11+ required
uv sync
cp .env.example .env   # then fill in OPENROUTER_API_KEY / ANTHROPIC_API_KEY
```

Drop the source BBC CSV dataset into `data/raw/`.

## Pipeline

Each stage is a standalone script under `scripts/` so it can be run and debugged independently.

| Stage | Script | Input | Output |
|---|---|---|---|
| 1. Cluster | `scripts/01_cluster.py` | `data/raw/*.csv` | `data/clustered/` (cluster assignments, top terms per cluster) |
| 2. Scrape | `scripts/02_scrape.py` | `data/clustered/` | `data/scraped/<category>/*.json` |
| 3. Analyze | `scripts/03_analyze.py` | `data/scraped/` | `analysis/static/stats.json`, `analysis/semantic/<category>.md` |
| 4. Style guide | `scripts/04_generate_style.py` | `analysis/` | `output/style_guide/_preamble.md` + `output/style_guide/<category>.md` |
| 5. Run agent | `scripts/05_run_agent.py` | `output/style_guide/` + user topic | generated article (stdout) |

## Layout

- `src/clustering/` — TF-IDF + KMeans over article titles/descriptions.
- `src/scraping/` — BBC article fetcher (requests + BeautifulSoup).
- `src/analyzers/static.py` — deterministic text stats.
- `src/analyzers/semantic.py` — LLM-based qualitative analysis, per category.
- `src/style/generator.py` — merges static stats + semantic notes into the final style guide.
- `src/agents/planner.py` — outlines the article.
- `src/agents/writer.py` — drafts the article using the style guide as system prompt.
- `src/agents/editor.py` — scores the draft against the style guide and requests revisions.
- `src/config.py` — env loading, model configs, path constants.

## Conventions

- LLM calls go through the config-selected provider (OpenRouter primary, Anthropic fallback).
- Data schemas (scraped article, analysis output, etc.) live as pydantic models near the module that produces them.
- Every module is importable and independently testable.
