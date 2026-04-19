# Observability

This project emits OpenTelemetry spans for every LLM call and every agent-level function, writing them as JSONL to `output/traces/<timestamp>_<stage>.jsonl`. No external service is required.

## Vocabulary

- **Trace.** One end-to-end invocation — e.g. one run of `scripts.05_run_agent`. Identified by a UUID `trace_id` assigned automatically by the OTel SDK at the root span.
- **Span.** One sub-operation within a trace — an LLM call, an agent function, an external request. Has a `span_id`, parent `trace_id`, start/end times, status, structured attributes, and events. Spans nest.
- **Attributes.** Structured key-values on a span: model, temperature, token counts, latency.
- **Events.** Timestamped points within a span. Large text (prompts, completions) is captured as events, not attributes, in OTel's LLM conventions.

## OpenTelemetry GenAI semantic conventions (`gen_ai.*`)

Industry-standard attribute names for LLM spans. Every community observability tool (Langfuse, OpenLLMetry, Phoenix, Datadog APM) records under these:

- `gen_ai.system` — `"openai"`, `"anthropic"`
- `gen_ai.request.model`, `gen_ai.response.model`
- `gen_ai.request.temperature`, `gen_ai.request.max_tokens`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.operation.name` — `"chat"`, `"text_completion"`
- Events: `gen_ai.content.prompt`, `gen_ai.content.completion` (content is captured as span events due to size)

Because we use these names, our spans are portable — swap the exporter and they land in any OTel-compatible backend.

## Implementation

Two layers of instrumentation (in [src/llm/tracing.py](../src/llm/tracing.py)):

1. **LLM-level, automatic.** `OpenAIInstrumentor().instrument()` and `AnthropicInstrumentor().instrument()` monkey-patch the SDKs. Every `chat.completions.create` / `messages.create` call emits a span tagged with `gen_ai.*` attributes.
2. **Agent-level, explicit.** A `@traced(name="...")` decorator wraps each agent entrypoint (`planner`, `writer`, `editor`, etc.) so LLM spans nest under a role-tagged parent. Makes span trees readable.

Each stage script calls `setup_tracing("<stage_name>")` at entry. The function is idempotent and returns the trace file path so scripts can surface it to users.

## Viewing traces

```bash
# Raw spans (JSONL, one span per line, standard OTel shape)
cat output/traces/<file>.jsonl

# Per-span overview
jq -c '{name, duration_ms: ((.end_time - .start_time) / 1000000 | floor), tokens: .attributes."gen_ai.usage.output_tokens"}' <file>.jsonl

# Just the LLM-auto-instrumented spans
jq 'select(.attributes."gen_ai.request.model")' <file>.jsonl

# Just the agent-level wrapper spans
jq 'select(.name == "planner" or .name == "writer" or .name == "editor")' <file>.jsonl
```

For stage-5 runs the trace path is also recorded in `output/generated/<run>/trace.json` for direct filesystem-to-JSONL navigation.

## Upgrade path to a hosted backend

Our setup is the foundation. Swap the exporter and the same spans ship anywhere:

```python
# src/llm/tracing.py — replace this line
BatchSpanProcessor(ConsoleSpanExporter(out=trace_file.open("a")))

# with this, pointing at Langfuse / Datadog / Grafana Tempo / etc.
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
BatchSpanProcessor(OTLPSpanExporter(endpoint="https://...", headers={...}))
```

No agent code changes. That's the point of using OTel conventions from the start.

## Production considerations deferred here

- **Sampling.** Prod doesn't trace 100%. Head-based (decide at request start) vs tail-based (decide after, based on errors/latency).
- **Capture policy.** Full prompt/response text is costly on disk and privacy-sensitive. Prod defaults: hash + full-on-error, or cap at N tokens. We capture full — dev corpus, no PII.
- **Cost attribution.** Track tokens by role × model for per-agent spend. Span names make this pivotable.
- **Retention.** JSONL files grow without bound. Prod: ship to a backend with retention policies, don't accumulate on disk.

## Related industrial tools

| Tool | Shape | When reached for |
|---|---|---|
| **OpenTelemetry SDK** (what we use) | Standard protocol, vendor-agnostic | Foundation; swap exporters to route anywhere |
| **Langfuse** | OSS LLM platform, SaaS or self-host | Prompt/eval/trace workflows, UI dashboard |
| **Arize Phoenix** | OSS, local-first web UI | Dev-box debugging, RAG eval |
| **LangSmith** | LangChain-native, SaaS | LangChain/LangGraph-heavy codebases |
| **OpenLLMetry (Traceloop)** | OTel auto-instrumentation for 40+ SDKs — we use their `opentelemetry-instrumentation-openai/anthropic` packages | Vendor-neutral one-liner instrumentation |
| **Helicone / Portkey** | Proxy-based logging | "Just change the URL" minimalism |
