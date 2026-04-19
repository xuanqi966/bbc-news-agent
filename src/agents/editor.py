"""Editor / QA agent — structured LLM-as-judge review of a writer's draft.

Runs a stronger model (see :func:`src.config.editor_model`) than the writer
uses, so a larger judge grades a smaller generator's output — the canonical
LLM-as-judge setup. Applies three strict checks:

- **Grounding** (strict): every named entity, figure, date, and quote in the
  draft must trace to :attr:`ArticleOutline.extracted_facts` or
  :attr:`ArticleOutline.quote_anchors`. Factually-correct-but-unsourced
  content is still a violation — the writer is not permitted to import
  world knowledge.
- **Style**: concrete violations of the style guide's directive bullets.
- **Attribution**: quotes without attribution, or attribution unsupported
  by the facts.

Separate issue lists make the judge's output legible; a holistic ``approved``
flag drives the revision loop in :mod:`scripts.05_run_agent`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src import config
from src.agents.planner import ArticleOutline
from src.llm import LLMProvider, get_provider
from src.llm.tracing import traced
from src.style.generator import load_for_category

EDITOR_SYSTEM_PROMPT = """You are a BBC News editor performing a structured quality review of a draft article. Apply three checks:

1. GROUNDING. The writer may only introduce factual content traceable to extracted_facts or quote_anchors. Distinguish two cases:

  (a) VIOLATION — invented or imported factual content:
      • definitions or characterisations not in the facts (e.g. "'grey belt' is poor-quality scrubland")
      • a new figure, date, or name not in the facts
      • an opposition argument, reaction, or reasoning the facts didn't mention
      • a quote not in quote_anchors, even if plausible

  (b) ACCEPTABLE — neutral connective tissue, paraphrase, or transitional prose that asserts no new factual claim:
      • "during the announcement", "the Prime Minister added", "the statement noted"
      • "framing the policy as…" (characterises, doesn't assert a fact)
      • "a sweeping overhaul" (qualitative framing of a factual change)
      • re-ordering or paraphrasing a fact already in the list

  Test: "does this assert a specific claim that, if false, would be wrong?" If yes and it's not in the facts → violation. If it's prose framing around a grounded claim → acceptable.

2. STYLE. Concrete violations of the style guide's directive bullets — not taste preferences. Flag only things the writer can act on.

3. ATTRIBUTION. Direct quotes used without clear source attribution, or attributions that don't match the supplied facts.

Output a structured EditorReview. Populate the three issue lists SEPARATELY. Set approved=true only if the issues are trivial or absent. Score 0–10 reflects overall quality holistically, not a simple issue count."""


class EditorReview(BaseModel):
    """Structured LLM-as-judge assessment of a draft.

    Three separate issue lists expose what kind of violation each one is —
    easier to read, easier to target in the revision loop.
    """

    approved: bool = Field(
        ...,
        description="Holistic go/no-go. True only if issues are trivial or absent.",
    )
    score: float = Field(
        ...,
        description="Overall quality 0–10. Holistic, not a simple issue count.",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="What the draft does well — at most 3 items.",
    )
    grounding_issues: list[str] = Field(
        default_factory=list,
        description=(
            "Draft content that does not trace to extracted_facts or quote_anchors. "
            "STRICT — world-knowledge injection is a violation even if factually correct."
        ),
    )
    style_issues: list[str] = Field(
        default_factory=list,
        description="Concrete violations of the style guide's directive bullets.",
    )
    attribution_issues: list[str] = Field(
        default_factory=list,
        description="Quotes or claims without proper attribution.",
    )
    suggested_revisions: list[str] = Field(
        default_factory=list,
        description="Concrete actionable fixes the writer can apply.",
    )


def _build_editor_prompt(draft: str, outline: ArticleOutline, style_guide: str) -> str:
    parts = [
        "STYLE GUIDE:",
        "",
        style_guide.strip(),
        "",
        "---",
        "",
        "EXTRACTED FACTS (everything factual in the draft must trace to these):",
    ]
    parts += [f"  • {f}" for f in outline.extracted_facts] or ["  (none)"]
    parts += [
        "",
        "QUOTE ANCHORS (direct quotes may only appear verbatim from this list):",
    ]
    parts += [f'  • "{q}"' for q in outline.quote_anchors] or ["  (none)"]
    parts += [
        "",
        "---",
        "",
        "DRAFT TO REVIEW:",
        "",
        draft.strip(),
    ]
    return "\n".join(parts)


@traced("editor")
def review_draft(
    draft: str,
    outline: ArticleOutline,
    provider: LLMProvider | None = None,
) -> EditorReview:
    """Run the editor on a draft; returns structured :class:`EditorReview`.

    Uses a stronger model (``config.editor_model()``) than the writer — the
    LLM-as-judge pattern. The provider itself is the same instance; only the
    per-call ``model`` string differs.
    """
    provider = provider or get_provider()
    style_guide = load_for_category(outline.category)
    user = _build_editor_prompt(draft, outline, style_guide)
    return provider.complete_structured(
        system=EDITOR_SYSTEM_PROMPT,
        user=user,
        schema=EditorReview,
        model=config.editor_model(),
        temperature=0.1,
    )
