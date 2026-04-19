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

Order implemented so far: style generator → semantic analyzer → static analyzer → scraper. Still stubs: clustering, agent subsystem (planner/writer/editor).

## Data contracts (the inter-module glue)

All contracts are pydantic v2 `BaseModel`s. Producers must emit shapes that deserialise cleanly via `model_validate_json`; consumers load them the same way.

| Contract | Defined in | Producer | Consumer |
|---|---|---|---|
| `ScrapedArticle` | [src/scraping/scraper.py](src/scraping/scraper.py) | scraper | both analyzers |
| `StaticStats` (+ `CategoryStats`, `NumericDistribution`) | [src/analyzers/static.py](src/analyzers/static.py) | static analyzer | style generator |
| `SemanticProfile` (rendered to markdown) | [src/analyzers/semantic.py](src/analyzers/semantic.py) | semantic analyzer | style generator |
| Cluster manifest `{category: [urls]}` | convention, file at `data/clustered/sample.json` | clustering (stub) | scraper |

**Locked-in convention: split LLM-filled fields from deterministic metadata.** E.g. `SemanticObservations` (LLM output) vs `SemanticProfile` (observations + deterministic `category` + `sample_urls`). Don't let the LLM fill anything the code already knows — it drifts.

## LLM provider abstraction

[src/llm/](src/llm/) — a `typing.Protocol` `LLMProvider` with two methods: `complete()` (plain text) and `complete_structured(schema=…)` (pydantic-validated output).

- `OpenRouterProvider` uses the OpenAI SDK pointed at `openrouter.ai/api/v1` with `response_format={"type": "json_schema", ...}`.
- `AnthropicProvider` uses a forced single tool call for structured output (`tool_choice={"type": "tool", "name": ...}`).
- `get_provider()` factory: OpenRouter if `OPENROUTER_API_KEY` set, else Anthropic, else raises.
- Every LLM call site takes an optional `provider: LLMProvider | None = None` so tests can inject a fake.

## Conventions you'll see repeated

- **Prose-render numeric stats before sending to an LLM.** See [`render_stats_brief`](src/analyzers/static.py). Don't hand the LLM `stats.json`. LLMs read prose ranges ("paragraphs 25–55 words") far better than JSON numbers.
- **Directive bullets in style guide per-category sections**, not observations. The writer agent will pick one category at generation time — give it rules, not notes about the corpus.
- **Deterministic seeded sampling** for anything stochastic in the analysis pipeline (`random.Random(42).sample(...)` with `sorted()` input).
- **Per-item try/except + log + skip** at batch boundaries (per-category for semantic, per-URL for scraper). Never let one bad input kill the whole run.
- **File-per-article / file-per-category** over monolithic blobs — keeps diffs small and stages independently rerunnable.

## Scraper specifics

BBC News articles are parsed via **JSON-LD first, HTML fallback**:
- JSON-LD `<script type="application/ld+json">` supplies `headline`, `datePublished`, `author` (most stable across BBC redesigns).
- `<div data-component="text-block">` contains the body `<p>` tags.
- Fallbacks: `<h1 id="main-heading">`, `<time datetime=...>`, `<article>` body.

BBC 403s the default `python-requests` UA; a realistic Chrome UA string is required. Rate limit 1.0s between requests. Idempotent resume via `<slug>.json` existence check.

## Style guide output shape

Split into a directory [output/style_guide/](output/style_guide/): a shared `_preamble.md` (global voice + structure ranges) plus one `<category>.md` per emitted category (4–6 directive bullets). `other` is intentionally not emitted. At generation time, writer agents call `src.style.generator.load_for_category(category)` to compose preamble + the single relevant category file — keeps the writer's system prompt focused (~350 words) instead of bloated with 10 categories of rules.

## Env + run

- `uv sync` to install; `uv run python -m scripts.XX_<stage>` to run a stage.
- `.env` keys: `OPENROUTER_API_KEY` and/or `ANTHROPIC_API_KEY`, optional `OPENROUTER_MODEL` / `ANTHROPIC_MODEL`.
- Paths all come from [src/config.py](src/config.py) — don't hardcode.
