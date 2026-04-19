"""Writer agent — drafts a BBC-style article from a planner outline.

Takes the :class:`ArticleOutline` from the planner, composes a system prompt
from the focused style guide (:func:`src.style.generator.load_for_category`),
and loads the 2 shortest staged example articles from ``data/examples/<category>/``
as style references (explicit guardrail: imitate shape, never reuse facts).

Runs on the default provider model (the writer is the "smaller generator" in
the LLM-as-judge pair — see :mod:`src.agents.editor`).
"""

from __future__ import annotations

from src import config
from src.agents.editor import EditorReview
from src.agents.planner import ArticleOutline
from src.llm import LLMProvider, get_provider
from src.llm.tracing import traced
from src.scraping.scraper import ScrapedArticle
from src.style.generator import load_for_category

WRITER_SYSTEM_PROMPT_TEMPLATE = """You are a BBC News staff writer. Write articles in the style specified below.

---

{style_guide}

---

Rules:
• You will receive a structured outline: headline options, lede angle, sections, an extracted_facts list, and quote_anchors that must be preserved verbatim.
• You will also see 1–2 example articles as STYLE REFERENCES ONLY.
• Imitate the examples' structure, sentence rhythm, sourcing pattern, and tone.
• Do NOT reuse any named entities, quotes, figures, dates, locations, or facts from the examples. All factual content in your article comes exclusively from the provided extracted_facts and quote_anchors. Entity reuse from examples is a grounding violation and will be rejected by the editor.
• Target length is advisory (±15%). Do not pad with invented context to hit the count.
• Output plain markdown: headline as H1, then body paragraphs. No preamble, no trailing commentary, no meta explanation."""


def build_system_prompt(style_guide: str) -> str:
    return WRITER_SYSTEM_PROMPT_TEMPLATE.format(style_guide=style_guide.strip())


def _load_shortest_examples(category: str, n: int = 2) -> list[ScrapedArticle]:
    """Return up to ``n`` staged examples for ``category``, sorted shortest first."""
    cat_dir = config.EXAMPLES_DIR / category
    if not cat_dir.exists():
        return []
    articles: list[ScrapedArticle] = []
    for p in sorted(cat_dir.glob("*.json")):
        try:
            articles.append(ScrapedArticle.model_validate_json(p.read_text()))
        except Exception as e:
            print(f"[writer] skipping malformed example {p.name}: {e!r}")
    articles.sort(key=lambda a: sum(len(p.split()) for p in a.paragraphs))
    return articles[:n]


def _render_example(a: ScrapedArticle, idx: int) -> str:
    body = "\n\n".join(a.paragraphs)
    return f"=== Style reference {idx} ===\n{a.title}\n\n{body}"


def _render_outline_for_writer(outline: ArticleOutline) -> str:
    lines = [
        f"Category: {outline.category}",
        f"Target word count: ~{outline.target_word_count} (±15%)",
        "",
        "Headline options (pick one or adapt):",
    ]
    lines += [f"  • {h}" for h in outline.headline_options]
    lines += [
        "",
        f"Lede angle: {outline.lede_angle}",
        "",
        "Sections (in order):",
    ]
    lines += [f"  {i+1}. {s.angle}" for i, s in enumerate(outline.sections)]
    lines += [
        "",
        "Extracted facts (ALL factual content must come from this list):",
    ]
    lines += [f"  • {f}" for f in outline.extracted_facts]
    lines += [
        "",
        "Quote anchors (preserve verbatim; place in a natural spot):",
    ]
    lines += [f'  • "{q}"' for q in outline.quote_anchors]
    return "\n".join(lines)


def _build_writer_prompt(
    outline: ArticleOutline, examples: list[ScrapedArticle]
) -> str:
    parts = [_render_outline_for_writer(outline)]
    if examples:
        parts += [
            "",
            "---",
            "",
            "STYLE REFERENCES BELOW — imitate voice/structure/rhythm; "
            "do NOT reuse any factual content from them.",
            "",
        ]
        for i, ex in enumerate(examples, 1):
            parts.append(_render_example(ex, i))
            parts.append("")
    return "\n".join(parts)


def _format_issues(label: str, items: list[str]) -> list[str]:
    if not items:
        return [f"{label}:", "  • (none)"]
    return [f"{label}:"] + [f"  • {i}" for i in items]


@traced("writer")
def write_article(
    outline: ArticleOutline,
    provider: LLMProvider | None = None,
) -> str:
    """Draft a markdown article from the outline."""
    provider = provider or get_provider()
    style_guide = load_for_category(outline.category)
    examples = _load_shortest_examples(outline.category, n=2)
    return provider.complete(
        system=build_system_prompt(style_guide),
        user=_build_writer_prompt(outline, examples),
        temperature=0.4,
    )


@traced("writer_revision")
def revise_article(
    draft: str,
    outline: ArticleOutline,
    review: EditorReview,
    provider: LLMProvider | None = None,
) -> str:
    """Apply editor feedback to a draft; return the revised markdown.

    Examples are dropped on the revision pass — the writer has already
    internalised style from the initial draft, and the revision is about
    fixing specific issues. Reduces tokens and keeps focus on the feedback.
    """
    provider = provider or get_provider()
    style_guide = load_for_category(outline.category)
    parts = [
        _render_outline_for_writer(outline),
        "",
        "---",
        "",
        "Your previous draft:",
        "",
        draft.strip(),
        "",
        "---",
        "",
        "Editor feedback — address every issue; keep everything the editor did not criticise:",
        "",
    ]
    parts += _format_issues("Grounding issues", review.grounding_issues)
    parts.append("")
    parts += _format_issues("Style issues", review.style_issues)
    parts.append("")
    parts += _format_issues("Attribution issues", review.attribution_issues)
    parts.append("")
    parts += _format_issues("Suggested revisions", review.suggested_revisions)
    parts += [
        "",
        "Output: the revised markdown article only. No preamble, no trailing commentary.",
    ]
    return provider.complete(
        system=build_system_prompt(style_guide),
        user="\n".join(parts),
        temperature=0.4,
    )
