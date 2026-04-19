"""OpenTelemetry tracing wired to a local JSONL file.

Auto-instruments openai + anthropic SDK calls via the OpenLLMetry community
packages (``opentelemetry-instrumentation-openai`` and
``opentelemetry-instrumentation-anthropic``); provides a :func:`traced`
decorator for wrapping agent entrypoints so LLM spans nest under a
role-named parent.

No external service required. Spans land in
``output/traces/<YYYY-MM-DD_HHMMSS>_<stage>.jsonl`` as standard-shape OTel
spans. Upgrade path: replace :class:`ConsoleSpanExporter` with
:class:`OTLPSpanExporter` pointing at Langfuse / Datadog / Grafana Tempo
to ship the same spans to a hosted backend — no other code changes.
"""

from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path

from opentelemetry import trace
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from src import config

_initialised = False
_trace_file: Path | None = None


def setup_tracing(stage_name: str) -> Path:
    """Initialise OTel once per process; return the JSONL file path for this run.

    Idempotent: subsequent calls return the same file path that spans are
    actually being written to. Call once at stage-script entry, then call
    again inside the stage ``main()`` to retrieve the path for artifacts.
    """
    global _initialised, _trace_file
    if _initialised:
        assert _trace_file is not None
        return _trace_file

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _trace_file = config.TRACES_DIR / f"{timestamp}_{stage_name}.jsonl"
    _trace_file.parent.mkdir(parents=True, exist_ok=True)

    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(
            ConsoleSpanExporter(
                out=_trace_file.open("a"),
                formatter=lambda span: span.to_json(indent=None) + "\n",
            )
        )
    )
    trace.set_tracer_provider(provider)

    OpenAIInstrumentor().instrument()
    AnthropicInstrumentor().instrument()

    _initialised = True
    return _trace_file


def traced(name: str):
    """Decorator: wrap a function's body in an OTel span named ``name``.

    Use at agent entrypoints (``planner``, ``writer``, ``editor``) and stage
    ``main()`` functions so the auto-instrumented LLM spans nest under a
    role-tagged parent.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            tracer = trace.get_tracer("bbc_news_agent")
            with tracer.start_as_current_span(name):
                return fn(*args, **kwargs)

        return wrapper

    return decorator
