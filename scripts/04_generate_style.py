"""Stage 4: merge static stats + semantic notes into ``output/style_guide/``.

Writes a shared ``_preamble.md`` plus one ``<category>.md`` per emitted
category. Writer agents compose preamble + one category file at generation time
via :func:`src.style.generator.load_for_category`.
"""

from __future__ import annotations

from src import config
from src.llm.tracing import setup_tracing, traced
from src.style.generator import generate_style_guide


@traced("stage_04_generate_style")
def main() -> None:
    config.ensure_dirs()
    out_dir = generate_style_guide()
    print(f"Wrote style guide to {out_dir}/")


if __name__ == "__main__":
    setup_tracing("04_generate_style")
    main()
