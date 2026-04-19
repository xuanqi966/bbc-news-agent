"""Stage 5: interactive agent — user supplies a topic, agent generates an article.

Picks the category for the topic, resolves the focused style guide via
:func:`src.style.generator.load_for_category` (preamble + one category file
from ``output/style_guide/``), then runs planner → writer → editor with at
least one revision loop and prints the final article.
"""

from __future__ import annotations

from src import config


def main() -> None:
    config.ensure_dirs()
    raise NotImplementedError


if __name__ == "__main__":
    main()
