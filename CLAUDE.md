# BBC News Style Analyzer — architecture notes for Claude

A multi-stage pipeline that extracts a working style guide from BBC News articles and will eventually use it to generate new articles. Built for a take-home assignment; scope is MVP-first, not production.

## Pipeline

```
raw CSV  →  cluster  →  scrape  →  static + semantic analyze  →  style guide  →  agent loop
data/raw    data/       data/         analysis/static + analysis/  output/       (stage 5,
(seed)      clustered/  scraped/      semantic/                     style_guide/ stubs)
```

Five stage scripts under [scripts/](scripts/), numbered `01` → `05`. Each is a thin entry point; logic lives in `src/`.

## Working-backwards principle

We implement consumers before their producers. Each module's output contract is shaped by what the downstream module needs, not by what's convenient to produce. This is the load-bearing design pattern — follow it when adding modules.

Order implemented: style generator → semantic analyzer → static analyzer → scraper → clustering → agent subsystem (planner/writer/editor). All five stages are wired end-to-end; stage-5 runs produce per-topic directories under [output/generated/](output/generated/) with `article.md`, `outline.json`, `reviews.json`, `trace.json`.

## Data contracts (the inter-module glue)

All contracts are pydantic v2 `BaseModel`s. Producers must emit shapes that deserialise cleanly via `model_validate_json`; consumers load them the same way.

| Contract | Defined in | Producer | Consumer |
|---|---|---|---|
| `ScrapedArticle` | [src/scraping/scraper.py](src/scraping/scraper.py) | scraper | both analyzers |
| `StaticStats` (+ `CategoryStats`, `NumericDistribution`) | [src/analyzers/static.py](src/analyzers/static.py) | static analyzer | style generator |
| `SemanticProfile` (rendered to markdown) | [src/analyzers/semantic.py](src/analyzers/semantic.py) | semantic analyzer | style generator |
| Cluster manifest `{category: [urls]}`, 20 URLs/cat (12 headered + 8 headerless) | convention, file at `data/clustered/sample.json` | clustering | scraper |
| `TAXONOMY` (list of 10 labels) | [src/clustering/cluster.py](src/clustering/cluster.py) | clustering | style generator (imports it) |

**Locked-in convention: split LLM-filled fields from deterministic metadata.** E.g. `SemanticObservations` (LLM output) vs `SemanticProfile` (observations + deterministic `category` + `sample_urls`). Don't let the LLM fill anything the code already knows — it drifts.

## LLM provider abstraction

[src/llm/](src/llm/) — a `typing.Protocol` `LLMProvider` with two methods: `complete()` (plain text) and `complete_structured(schema=…)` (pydantic-validated output).

- `OpenRouterProvider` uses the OpenAI SDK pointed at `openrouter.ai/api/v1` with `response_format={"type": "json_schema", ...}`.
- `AnthropicProvider` uses a forced single tool call for structured output (`tool_choice={"type": "tool", "name": ...}`).
- `get_provider()` factory: OpenRouter if `OPENROUTER_API_KEY` set, else Anthropic, else raises.
- Every LLM call site takes an optional `provider: LLMProvider | None = None` so tests can inject a fake.

## Observability

[src/llm/tracing.py](src/llm/tracing.py) wires OpenTelemetry spans to a JSONL file under `output/traces/<timestamp>_<stage>.jsonl`. LLM calls are auto-instrumented via `OpenAIInstrumentor` / `AnthropicInstrumentor` (OTel GenAI `gen_ai.*` conventions). Agent entrypoints are explicitly wrapped with `@traced(name=...)` so LLM spans nest under role-tagged parents. Each stage script calls `setup_tracing("<stage_name>")` at entry (the scraper skips it — no LLM calls). Full details and upgrade path live in [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md).

## Agent subsystem (stage 5)

[scripts/05_run_agent.py](scripts/05_run_agent.py) drives a planner → writer → editor loop against a user-supplied topic + source text from `inputs/`:

- **[src/agents/planner.py](src/agents/planner.py)** — extracts facts from source, gates on sufficiency, decides target word count, emits outline.
- **[src/agents/writer.py](src/agents/writer.py)** — drafts markdown from outline using `load_for_category(category)` (preamble + single category file) as the system prompt.
- **[src/agents/editor.py](src/agents/editor.py)** — structured `review_draft()` against the style guide; conditionally calls `revise_article()`. Loop: initial draft → review → revision (if requested) → final review.

Each run writes a timestamped directory under `output/generated/<ts>_<category>/` with `article.md`, `outline.json`, `reviews.json` (initial + final), `trace.json` (pointer to the OTel JSONL).

## Conventions you'll see repeated

- **Prose-render numeric stats before sending to an LLM.** See [`render_stats_brief`](src/analyzers/static.py). Don't hand the LLM `stats.json`. LLMs read prose ranges ("paragraphs 25–55 words") far better than JSON numbers.
- **Directive bullets in style guide per-category sections**, not observations. The writer agent will pick one category at generation time — give it rules, not notes about the corpus.
- **Deterministic seeded sampling** for anything stochastic in the analysis pipeline (`random.Random(42).sample(...)` with `sorted()` input).
- **Per-item try/except + log + skip** at batch boundaries (per-category for semantic, per-URL for scraper). Never let one bad input kill the whole run.
- **File-per-article / file-per-category** over monolithic blobs — keeps diffs small and stages independently rerunnable.

## Clustering specifics

Classification, not clustering. BBC's own URL paths encode the category for ~83% of the corpus, and the taxonomy is fixed (10 labels in [src/clustering/cluster.py::TAXONOMY](src/clustering/cluster.py)). So [`cluster.py`](src/clustering/cluster.py) runs a **two-path classifier**:

- **Path A — regex on URL path** (`/sport/*` → sports, `/news/business-*`, `/news/science-*`, `politics` anywhere in slug, etc.) for the deterministic majority.
- **Path B — batched LLM classification** on `(title, description)` pairs for the ~17% headerless tail (post-2024Q2 UUID slugs `/news/articles/cXXXX` and bare-numeric `/news/12345`). Oversample ~3× the needed candidates, then `provider.complete_structured(schema=ClassifyBatch)`.

Per category sample: 12 headered + 8 headerless, clamped to supply, seeded via `random.Random(42)`. `other` is a routing bin — classified URLs go there but the style guide skips emitting rules for it.

Debug artefact: `data/clustered/assignments.csv` with a `source ∈ {regex, llm, fallback}` column for post-run inspection.

## Scraper specifics

BBC News articles are parsed via **JSON-LD first, HTML fallback**:
- JSON-LD `<script type="application/ld+json">` supplies `headline`, `datePublished`, `author` (most stable across BBC redesigns).
- `<div data-component="text-block">` contains the body `<p>` tags.
- Fallbacks: `<h1 id="main-heading">`, `<time datetime=...>`, `<article>` body.

BBC 403s the default `python-requests` UA; a realistic Chrome UA string is required. Rate limit 1.0s between requests. Idempotent resume via `<slug>.json` existence check.

After scraping, `_stage_examples()` copies the first 3 successfully-scraped articles per category into `data/examples/<category>/` as portable few-shot context for the future QA agent. Idempotent (skip if destination exists).

## Style guide output shape

Split into a directory [output/style_guide/](output/style_guide/): a shared `_preamble.md` (global voice + structure ranges) plus one `<category>.md` per emitted category (4–6 directive bullets). `other` is intentionally not emitted. At generation time, writer agents call `src.style.generator.load_for_category(category)` to compose preamble + the single relevant category file — keeps the writer's system prompt focused (~350 words) instead of bloated with 10 categories of rules.

## Env + run

- `uv sync` to install; `uv run python -m scripts.XX_<stage>` to run a stage.
- `.env` keys: `OPENROUTER_API_KEY` and/or `ANTHROPIC_API_KEY`, optional `OPENROUTER_MODEL` / `ANTHROPIC_MODEL`.
- Paths all come from [src/config.py](src/config.py) — don't hardcode.
