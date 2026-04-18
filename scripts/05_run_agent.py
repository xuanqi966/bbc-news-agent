"""Stage 5: interactive agent — user supplies a topic, agent generates an article.

Loads ``output/style_guide.md`` once, then runs planner → writer → editor
(with at least one revision loop) and prints the final article.
"""

from __future__ import annotations

from src import config


def main() -> None:
    config.ensure_dirs()
    raise NotImplementedError


if __name__ == "__main__":
    main()
