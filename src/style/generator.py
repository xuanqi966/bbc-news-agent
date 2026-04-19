"""Generate the per-category BBC style guide.

One LLM call receives the prose stats brief (rendered from ``stats.json``)
and every ``analysis/semantic/*.md`` file, and returns a structured
:class:`StyleGuide` artifact. The module then writes it deterministically as:

- ``output/style_guide/_preamble.md`` — global voice + structure ranges
- ``output/style_guide/<category>.md`` — per-category directive bullets

``other`` is intentionally excluded from the per-category output (catch-all bin,
no coherent voice to teach). At generation time, writer agents call
:func:`load_for_category` to assemble the focused prompt.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from src import config
from src.analyzers.static import StaticStats, render_stats_brief
from src.clustering.cluster import TAXONOMY
from src.llm import LLMProvider, get_provider

EMITTED_CATEGORIES = [c for c in TAXONOMY if c != "other"]

STYLE_GUIDE_SYSTEM_PROMPT = (
    "You are a newsroom style editor. Produce a compact, authored working style "
    "guide for a downstream writer agent. The guide lives inside another model's "
    "system prompt alongside the user's topic, facts, and the in-progress draft, "
    "so it must be short and prescriptive — not an essay. Write in second-person, "
    "directive voice ('Open with…', 'Prefer…', 'Keep sentences ≤ 20 words'). "
    "Treat the supplied corpus stats and per-category style notes as ground truth; "
    "do not invent facts about the corpus."
)


class CategoryGuide(BaseModel):
    """Per-category directive bullets — one entry in the structured output."""

    name: str = Field(
        ...,
        description=(
            "Category slug. Must be exactly one of: "
            f"{', '.join(EMITTED_CATEGORIES)}."
        ),
    )
    bullets: list[str] = Field(
        ...,
        description=(
            "4–6 directive bullets in second-person imperative voice "
            "('Open with…', 'Prefer…'). Rules a writer can follow, not observations."
        ),
    )


class StyleGuide(BaseModel):
    """Structured output: preamble + one CategoryGuide per emitted category."""

    preamble: str = Field(
        ...,
        description=(
            "Global rules section, ~250 words. Two subsections in markdown:\n"
            "## Voice & principles (150–200 words of authored prose)\n"
            "## Structure & length (bullets grounded in the supplied corpus stats: "
            "article length, headline length, lede, paragraphs, sentences, quotes)."
        ),
    )
    categories: list[CategoryGuide] = Field(
        ...,
        description=(
            f"One entry per category in this set: {', '.join(EMITTED_CATEGORIES)}. "
            "Do not emit 'other'."
        ),
    )


def _render_user_prompt(stats_brief: str, semantic: dict[str, str]) -> str:
    parts = [
        "Produce a structured style guide matching the StyleGuide schema.",
        "",
        "The preamble should contain two markdown subsections:",
        "  '## Voice & principles' — 150–200 words of authored prose, global rules.",
        "  '## Structure & length' — bullets grounded in the corpus stats below "
        "(article length, headline length, lede, paragraph rhythm, sentence length, quotes).",
        "",
        "For categories, emit one CategoryGuide per label in this exact set, in this order:",
        f"  {', '.join(EMITTED_CATEGORIES)}",
        "Do NOT emit an entry for 'other'.",
        "Each CategoryGuide has 4–6 directive bullets — rules the writer can follow, "
        "not observations about the corpus. Second-person imperative voice.",
        "",
        "---",
        "",
        "Corpus stats (use these as ground truth for ranges in the preamble):",
        "",
        stats_brief,
        "",
        "---",
        "",
        "Per-category style notes (derived from the corpus; informs each CategoryGuide):",
        "",
    ]
    for category, notes in semantic.items():
        parts.append(f"## {category}")
        parts.append(notes.strip())
        parts.append("")
    return "\n".join(parts)


def _write_category_file(out_dir: Path, guide: CategoryGuide) -> Path:
    title = guide.name.replace("_", " ").title()
    body = f"# {title} article rules\n\n" + "\n".join(f"- {b}" for b in guide.bullets) + "\n"
    path = out_dir / f"{guide.name}.md"
    path.write_text(body)
    return path


def generate_style_guide(
    stats_path: Path | None = None,
    semantic_dir: Path | None = None,
    out_dir: Path | None = None,
    provider: LLMProvider | None = None,
) -> Path:
    """Synthesise the style guide; write ``_preamble.md`` + per-category files.

    Returns the output directory.
    """
    stats_path = stats_path or (config.STATIC_ANALYSIS_DIR / "stats.json")
    semantic_dir = semantic_dir or config.SEMANTIC_ANALYSIS_DIR
    out_dir = out_dir or config.STYLE_GUIDE_DIR
    provider = provider or get_provider()
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = StaticStats.model_validate_json(stats_path.read_text())
    brief = render_stats_brief(stats)
    semantic = {p.stem: p.read_text() for p in sorted(semantic_dir.glob("*.md"))}

    result = provider.complete_structured(
        system=STYLE_GUIDE_SYSTEM_PROMPT,
        user=_render_user_prompt(brief, semantic),
        schema=StyleGuide,
        temperature=0.3,
    )

    preamble_path = out_dir / "_preamble.md"
    preamble_path.write_text(result.preamble.rstrip() + "\n")
    print(f"[style] wrote {preamble_path.name}")

    seen: set[str] = set()
    for guide in result.categories:
        if guide.name == "other":
            print("[style] skipping 'other' (emitted by LLM, not allowed)")
            continue
        if guide.name not in EMITTED_CATEGORIES:
            print(f"[style] warning — unknown category {guide.name!r}, skipping")
            continue
        if guide.name in seen:
            print(f"[style] warning — duplicate category {guide.name!r}, skipping")
            continue
        seen.add(guide.name)
        path = _write_category_file(out_dir, guide)
        print(f"[style] wrote {path.name} ({len(guide.bullets)} bullets)")

    missing = [c for c in EMITTED_CATEGORIES if c not in seen]
    if missing:
        print(f"[style] warning — missing category files: {missing}")

    return out_dir


def load_for_category(
    category: str,
    style_guide_dir: Path | None = None,
) -> str:
    """Return the writer-ready style guide for ``category``.

    Returns ``preamble + "\\n\\n---\\n\\n" + {category}.md`` when the category
    file exists, else the preamble alone (with a log warning). The writer agent
    calls this at generation time to build its system-prompt context.
    """
    style_guide_dir = style_guide_dir or config.STYLE_GUIDE_DIR
    preamble = (style_guide_dir / "_preamble.md").read_text()
    cat_path = style_guide_dir / f"{category}.md"
    if not cat_path.exists():
        print(f"[style] no category file for {category!r} — returning preamble only")
        return preamble
    return preamble.rstrip() + "\n\n---\n\n" + cat_path.read_text()
