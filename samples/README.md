# Pre-generated pipeline output

Everything here was produced by running the full 5-stage pipeline end-to-end once (2026-04-19) against the BBC News CSV in `data/raw/`. You can inspect what the system produces without running anything — useful if you don't want to set up API keys just to read the output.

## What to look at first

If you're here to evaluate the system, the highest-signal files are:

1. **[style_guide/](style_guide/)** — the final output of stages 1–4. A shared [`_preamble.md`](style_guide/_preamble.md) (global voice and structure ranges) plus one `<category>.md` per category with 4–6 directive bullets. This is what the writer agent is actually grounded on.
2. **[generated/2026-04-19_161305_politics/article.md](generated/2026-04-19_161305_politics/article.md)** — a generated article about UK housing policy. Input facts live in [`../inputs/politics_example.txt`](../inputs/politics_example.txt).
3. **[generated/2026-04-19_161305_politics/reviews.json](generated/2026-04-19_161305_politics/reviews.json)** — the editor's structured review of that draft, with grounding / style / attribution issue lists.
4. **[traces/2026-04-19_161305_05_run_agent.jsonl](traces/2026-04-19_161305_05_run_agent.jsonl)** — OpenTelemetry spans (one JSON object per line) covering every LLM call and agent entrypoint in that run. See [`../docs/OBSERVABILITY.md`](../docs/OBSERVABILITY.md) for the attribute schema.

## Intermediate artefacts

- **[data/clustered/sample.json](data/clustered/sample.json)** — the 20-URLs-per-category manifest that stage 2 scrapes (12 headered + 8 headerless).
- **[data/clustered/assignments.csv](data/clustered/assignments.csv)** — full URL→category map with a `source ∈ {regex, llm, fallback}` column showing which classification path hit each URL.
- **[data/scraped/\<category\>/](data/scraped/)** — per-article JSON as produced by the scraper (`ScrapedArticle` shape).
- **[data/examples/\<category\>/](data/examples/)** — 3 representative articles per category, staged by stage 2 as few-shot style references for the writer agent at generation time.
- **[analysis/static/stats.json](analysis/static/stats.json)** — per-category percentile distributions (word count, paragraph length, sentence length, quote density, headline and lede lengths).
- **[analysis/semantic/\<category\>.md](analysis/semantic/)** — per-category qualitative observations from the semantic analyzer (voice, sourcing patterns, signature rhetorical moves).

## Regenerating this directory

These samples are a snapshot. To regenerate from scratch, delete or rename `samples/` and run the full pipeline (see the main [README.md](../README.md#how-to-use)). Each stage writes to `data/` / `analysis/` / `output/` — move the fresh artefacts back into `samples/` if you want to replace the snapshot.
