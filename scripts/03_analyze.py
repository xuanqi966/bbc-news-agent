"""Stage 3: run static + semantic analysis over scraped articles.

Produces ``analysis/static/stats.json`` and one ``analysis/semantic/<category>.md``
per category.
"""

from __future__ import annotations

from src import config
from src.analyzers.semantic import run_semantic_analysis
from src.analyzers.static import run_static_analysis
from src.llm.tracing import setup_tracing, traced


@traced("stage_03_analyze")
def main() -> None:
    config.ensure_dirs()
    run_static_analysis()
    written = run_semantic_analysis()
    print(f"[analyze] wrote {len(written)} semantic profile(s)")


if __name__ == "__main__":
    setup_tracing("03_analyze")
    main()
