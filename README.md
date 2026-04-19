# BBC News Article Style Analyzer & Generator

A multi-stage pipeline that extracts a working style guide from a corpus of BBC News articles, then uses it to generate new articles in the same voice.

Given a CSV of BBC article URLs, the system:

1. Classifies each article into one of 10 topical categories (business, politics, sports, etc.)
2. Scrapes a sampled subset for full body content
3. Analyzes the corpus both statistically (word counts, paragraph lengths, quote density) and semantically (LLM-driven voice/style observations per category)
4. Merges the two analyses into a per-category style guide
5. Runs a planner → writer → editor agent loop to generate a new article from user-supplied facts, grounded in the style guide

Pre-generated output from one full end-to-end run lives in [samples/](samples/) — you can inspect the final style guide and a generated article without running anything.

---

## Problem framing & core assumptions

The take-home prompt was deliberately open:

> Using the BBC News dataset from Kaggle, design a backend AI agentic workflow that generates news articles resembling BBC-style content based on user inputs such as topics. Your workflow should include: content analysis, content generation, and a review/QA step.

I narrowed the scope to a concrete, evaluable specification:

**Usage model**

1. The user picks a **category** from a predefined taxonomy (politics, business, sports, technology, world, uk_news, health, science, entertainment).
2. The user supplies **raw material** — facts, figures, direct quotes, interview snippets — in a plaintext `--facts` file.
3. The pipeline produces a BBC-style article grounded strictly in that material. It invents nothing.

**Core assumptions**

These shape every downstream design decision:

- **Grounding is strict, not best-effort.** Every fact, entity, figure, date, and quote in the final article must trace to the user's raw material. World-knowledge injection is treated as a violation even when factually correct. This is the single load-bearing constraint of the system — the planner, writer, and editor all enforce it.
- **Category is a style selector, not a content generator.** Facts come from the user; voice comes from the category's style guide. A "politics" article about housing is shaped like a BBC politics piece, but its content is entirely the user's.
- **Thin material should be rejected, not padded.** If the user supplies a one-line tip, the correct output is a ~200-word brief or an explicit rejection — never a padded 700-word article filled with invented context. The planner gates sufficiency up-front.
- **Style is reverse-engineered from the corpus, not hand-written.** No human writes "BBC politics articles use a 'claim vs reality' framework." The semantic analyzer reads real articles and discovers per-category directive bullets, which the style generator then merges with statistical structure ranges from the static analyzer.
- **Quality control is LLM-as-judge against the style guide, not a rubric.** A stronger editor model grades a smaller writer model on three structured checks: grounding, style, attribution. Approved-only-if-issues-trivial.
- **Observability is first-class, not an afterthought.** Every LLM call emits a `gen_ai.*` span and every agent entrypoint nests under a role-tagged parent. Debugging a bad generation means reading the span tree, not sprinkling print statements.
- **The 10-category taxonomy is known a priori**, so "clustering" is actually classification via URL-path regex + LLM fallback for the headerless tail — not TF-IDF/KMeans reverse-discovery.
- **MVP over production hardening.** Regex sentence splitting, `html.parser`, no retry logic, rate-limited sequential scraping, single-round revision loop. The take-home is a design exercise; production-grade choices are called out explicitly in the **Key decisions & tradeoffs** table below.

Where these assumptions map into the code is called out throughout the **Design** section.

---

## Reviewing without running — start here

If you want to skim what the system produces:

- **[samples/README.md](samples/README.md)** — index of all pre-generated artefacts with pointers to the highest-signal files
- **[samples/style_guide/](samples/style_guide/)** — the final style guide: shared preamble + 9 category-specific rulesets
- **[samples/generated/2026-04-19_161305_politics/article.md](samples/generated/2026-04-19_161305_politics/article.md)** — one generated article (UK housing policy)
- **[samples/generated/2026-04-19_161305_politics/reviews.json](samples/generated/2026-04-19_161305_politics/reviews.json)** — structured editor review of that draft
- **[samples/traces/2026-04-19_161305_05_run_agent.jsonl](samples/traces/2026-04-19_161305_05_run_agent.jsonl)** — OpenTelemetry spans for the full agent run

The design section below explains *why* these files are shaped the way they are.

---

## How to use

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- At least one LLM API key (OpenRouter or Anthropic)

### Setup

```bash
uv sync
cp .env.example .env
```

Then edit `.env` — you must fill in at least one API key. The file's comments explain each variable; in brief:

| Variable | What it's for | Required? |
|---|---|---|
| `OPENROUTER_API_KEY` | Primary LLM provider (routes to most models via one key) | One of OR/Anthropic |
| `ANTHROPIC_API_KEY` | Fallback provider — used if OpenRouter isn't set | One of OR/Anthropic |
| `OPENROUTER_MODEL` / `ANTHROPIC_MODEL` | The "general" model — used by the planner, writer, semantic analyzer, and LLM classification path in clustering | Optional (has a default) |
| `OPENROUTER_EDITOR_MODEL` / `ANTHROPIC_EDITOR_MODEL` | The model used by the editor (LLM-as-judge); typically a stronger model than the general one | Optional (has a default) |

If both providers' keys are set, OpenRouter wins (see [src/llm/factory.py](src/llm/factory.py)). The source CSV is already at `data/raw/bbc_news.csv`.

### Run the pipeline

Each stage is a standalone script — independently rerunnable and idempotent at the file level.

| Stage | Command | Reads from | Writes to |
|---|---|---|---|
| 1. Cluster | `uv run python -m scripts.01_cluster` | `data/raw/*.csv` | `data/clustered/` |
| 2. Scrape | `uv run python -m scripts.02_scrape` | `data/clustered/sample.json` | `data/scraped/<category>/*.json` |
| 3. Analyze | `uv run python -m scripts.03_analyze` | `data/scraped/` | `analysis/static/stats.json`, `analysis/semantic/<category>.md` |
| 4. Style guide | `uv run python -m scripts.04_generate_style` | `analysis/` | `output/style_guide/_preamble.md` + `output/style_guide/<category>.md` |
| 5. Run agent | `uv run python -m scripts.05_run_agent --category <cat> --facts <path>` | `output/style_guide/` + `--facts` file | `output/generated/<timestamp>_<category>/` |

Full first run end-to-end: ~5–8 minutes, dominated by stage 2 (rate-limited at 1 req/s to BBC) and the LLM-heavy stages 3 and 5. Stage 5 on its own runs in 30–60s.

Example stage-5 invocation using one of the sample `--facts` files in [inputs/](inputs/):

```bash
uv run python -m scripts.05_run_agent \
    --category politics \
    --facts inputs/politics_example.txt
```

The generated article lands at `output/generated/<timestamp>_politics/article.md`; progress and editor feedback go to stderr.

### Running stage 5 only (against the pre-generated snapshot)

If you just want to see the agent loop work without running the ~5-minute stages 1–4, bootstrap the runtime dirs from [samples/](samples/):

```bash
mkdir -p output/style_guide data/examples
cp -r samples/style_guide/. output/style_guide/
cp -r samples/data/examples/. data/examples/
uv run python -m scripts.05_run_agent --category politics --facts inputs/politics_example.txt
```

The writer reads the category-specific style guide from `output/style_guide/` and the few-shot style-reference articles from `data/examples/<category>/`. Both live canonically in [samples/](samples/) so the snapshot is stable; a fresh full pipeline run would overwrite the runtime copies without touching `samples/`.

### Tests

```bash
uv run --extra dev pytest tests/ -v
```

Smoke tests only (provider factory + pydantic contract round-trip). The pipeline itself needs real LLM calls to exercise fully, so it isn't covered by automated tests.

---

## Design

### Pipeline architecture

```
data/raw/*.csv  →  classify  →  scrape  →  static + semantic analyze  →  style guide  →  agent loop
                   clustering    scraping   analyzers                    style/         agents/
```

Five numbered stage scripts under [scripts/](scripts/) — each a thin entry point delegating to `src/`. The separation makes every stage independently rerunnable and debuggable.

### Working-backwards design

The load-bearing architectural decision: **each module's output shape is determined by what the next module needs, not by what's convenient to produce.** The pipeline was built in reverse order — style generator first, then the semantic analyzer to feed it, then the static analyzer, then the scraper, finally the clustering. The agent subsystem came last, consuming the style guide.

This gives every producer a concrete target to aim at. The pydantic models ([`ScrapedArticle`](src/scraping/scraper.py), [`StaticStats`](src/analyzers/static.py), [`SemanticProfile`](src/analyzers/semantic.py), [`ArticleOutline`](src/agents/planner.py), [`EditorReview`](src/agents/editor.py)) double as the inter-module contracts *and* the on-disk JSON format via `model_validate_json` / `model_dump_json`.

### Stage-by-stage notes

**Clustering** — [src/clustering/cluster.py](src/clustering/cluster.py). This is classification, not clustering: BBC's URL paths encode the category for ~83% of the corpus, and the taxonomy is fixed (10 labels). Two-path classifier:

- **Path A** — regex on the URL path (`/sport/*` → sports, `/news/business-*`, `politics` anywhere in the slug, etc.) for the deterministic majority.
- **Path B** — batched LLM classification on `(title, description)` pairs for the ~17% headerless tail (post-2024Q2 UUID slugs like `/news/articles/cxxxx…`). The LLM returns a structured `ClassifyBatch`.

20 URLs per category (12 headered + 8 headerless), seeded with `random.Random(42)` for reproducibility. A debug `assignments.csv` records which path classified each URL.

**Scraping** — [src/scraping/scraper.py](src/scraping/scraper.py). BBC articles are parsed JSON-LD first (most stable across redesigns: `headline`, `datePublished`, `author`), with HTML-selector fallbacks (`<div data-component="text-block">` for body, `<h1 id="main-heading">`, `<time datetime=...>`). BBC 403s the default `python-requests` UA, so a realistic Chrome string is required. Rate-limited to 1.0s/req. Each article lands as a separate `<slug>.json` — idempotent resume via existence check, and per-URL failures don't poison the batch.

**Static analysis** — [src/analyzers/static.py](src/analyzers/static.py). Deterministic percentile distributions (p25 / p50 / p75) per category for word count, paragraph length, sentence length, quote density, headline and lede lengths. Regex sentence splitter — good enough for the MVP and avoids an nltk dependency.

**Semantic analysis** — [src/analyzers/semantic.py](src/analyzers/semantic.py). For each category, feeds the LLM a sample of N full articles and asks for structured observations about voice, sourcing patterns, recurring phrasings, and signature rhetorical moves. Returns a pydantic `SemanticObservations` (LLM-filled) that's combined with the deterministic `category` and `sample_urls` into a `SemanticProfile`. The pattern — never let the LLM fill fields the code already knows — is repeated across every structured output boundary.

**Style guide** — [src/style/generator.py](src/style/generator.py). Merges stats + per-category observations into a shared preamble (global voice + structure ranges, rendered as prose rather than JSON numbers) plus one `<category>.md` per category. The per-category files contain 4–6 *directive bullets* — rules the writer can follow, not observations about the corpus. Writer agents call `load_for_category(category)` to compose preamble + one category file, keeping the writer's system prompt focused (~350 words) instead of bloated with 10 categories of rules.

**Agent subsystem** — [src/agents/](src/agents/). The planner/writer/editor loop driven by [scripts/05_run_agent.py](scripts/05_run_agent.py):

- **Planner** ([planner.py](src/agents/planner.py)) — extracts grounded facts + verbatim quote anchors from user material. Gates on sufficiency (rejects material that lacks actor + action + verifiable detail). Chooses a target word count based on material density, using the style preamble's median range as reference.
- **Writer** ([writer.py](src/agents/writer.py)) — drafts markdown using the category-specific style guide as system prompt. Sees the extracted facts + quote anchors + 1–2 sample articles as *style references only*. Grounding firewall: cannot reuse entities from the sample articles.
- **Editor** ([editor.py](src/agents/editor.py)) — LLM-as-judge with a stronger model than the writer. Three strict checks — grounding (no invented entities/quotes), style (concrete rule violations), attribution (quotes must have clear sources) — emitted as separate issue lists on a structured `EditorReview`.
- **Revision loop** — if editor disapproves, the writer gets the structured issue list back and revises once. If still disapproved after one revision, the draft ships with a warning (logged + present in `reviews.json`).

### LLM provider abstraction

[src/llm/](src/llm/). `LLMProvider` is a `typing.Protocol` with two methods: `complete()` for plain text and `complete_structured(schema=...)` for pydantic-validated structured output. Two implementations:

- **OpenRouterProvider** — OpenAI SDK pointed at `openrouter.ai/api/v1` with `response_format={"type": "json_schema", …}` for structured output.
- **AnthropicProvider** — Anthropic SDK with a forced single tool call (`tool_choice={"type": "tool", "name": …}`) to coerce structured output.

`get_provider()` picks based on which key is set. Every LLM call site takes an optional `provider: LLMProvider | None = None` so tests can inject a fake without monkey-patching.

### Observability

[src/llm/tracing.py](src/llm/tracing.py), [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md). Two layers of OpenTelemetry instrumentation:

- **LLM-level, automatic** — `OpenAIInstrumentor().instrument()` and `AnthropicInstrumentor().instrument()` monkey-patch the SDKs so every `chat.completions.create` / `messages.create` call emits a span tagged with OTel's GenAI `gen_ai.*` attributes (model, tokens, latency; prompt + completion captured as span events).
- **Agent-level, explicit** — `@traced(name=...)` decorator wraps each agent entrypoint (`planner`, `writer`, `editor`) and each stage script's `main` so LLM spans nest under role-tagged parents.

Spans export to JSONL at `output/traces/<timestamp>_<stage>.jsonl`. Because the attributes follow OTel GenAI conventions, the same spans land unchanged in any OTel-compatible backend (Langfuse, Phoenix, Datadog) via a one-line exporter swap.

---

## Key decisions & tradeoffs

| Decision | Why | Tradeoff |
|---|---|---|
| URL-regex + LLM-fallback classifier over sklearn clustering | Taxonomy is fixed (10 known categories); ~83% of URLs encode the category. True clustering would reverse-discover categories we already know. | Regex rules are BBC-specific; a different corpus would need different path rules. |
| Pydantic contracts as both in-memory and on-disk format | `model_validate_json` / `model_dump_json` round-trip for free; contracts are enforced at every module boundary. | Serialization format is tied to pydantic. |
| Split LLM-filled vs deterministic fields in every structured response | LLMs drift on fields the code already knows (category names, URLs). Never trust the LLM to echo what it was told. | One extra pydantic class per schema boundary. |
| Prose-render numerics before sending to an LLM | LLMs read "paragraphs 25–55 words" far better than `{"p25": 25, "p75": 55}`. | Small amount of glue code per schema. |
| Per-article / per-category files over monolithic blobs | Small diffs; per-category iteration; individual failures don't poison the batch; stages are rerunnable from partial state. | More files on disk. |
| LLM-as-judge editor with a stronger model than the writer | The canonical separation-of-concerns pattern — cheaper generator, more trusted judge. Also makes it easy to swap either side independently. | Two model configs to maintain. |
| Single revision round, ship-with-warning on persistent disapproval | Bounds latency at ~2× writer cost worst-case; prevents pathological infinite-revision loops on impossible material. | Occasionally ships drafts with unresolved style issues (always logged + present in `reviews.json`). |
| Writer sees one category file, not the whole style guide | Keeps the writer's system prompt focused (~350 words) instead of 10 categories of rules. | The guide's cross-category observations are lost on the writer (they still shape the preamble). |
| OpenTelemetry from day one, even for a small project | Vendor-neutral; upgrade path to any hosted backend is a one-line exporter swap; span trees make the agent loop debuggable by default. | One extra dependency — worth it. |
| MVP over production hardening (regex sentence splitter, html.parser, no retries on transient LLM failures) | This is a take-home demonstrating system design, not a production deployment. Every MVP choice is marked in comments where it matters. | Would need revisiting for real use — see "Production considerations deferred" in [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md). |

---

## Layout

```
scripts/             stage entry points 01–05
src/
  clustering/        URL-regex + LLM-fallback classifier
  scraping/          BBC article fetcher (JSON-LD first, HTML fallback)
  analyzers/         static.py (deterministic stats), semantic.py (LLM observations)
  style/             merges stats + observations into directive-bullet style guide
  agents/            planner, writer, editor + revision loop
  llm/               LLMProvider protocol, OpenRouter + Anthropic impls, OTel tracing
  config.py          paths, env loading, model selection
inputs/              example --facts files for stage 5
samples/             pre-generated artefacts for reviewer inspection
docs/                OBSERVABILITY.md
tests/               smoke tests (provider factory + pydantic contracts)
```

## Further reading

- [CLAUDE.md](CLAUDE.md) — dense architecture notes written for LLM assistants
- [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) — span schema, query recipes, hosted-backend upgrade path
- [samples/README.md](samples/README.md) — index of the pre-generated artefacts
