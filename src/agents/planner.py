"""Planner agent — turns raw user material into a structured article outline.

The planner is the shock absorber for input shape and size. It:

- Extracts a canonical fact list from whatever the user provided (one line,
  a dense brief, a jumble of quotes).
- Gates sufficiency: rejects material that lacks at least one actor, one
  action/event, and one verifiable detail.
- Decides a target word count based on material density — thin input yields
  a news brief, not a padded full article.

Follows the session convention of splitting LLM-filled observations
(:class:`PlannerObservations`) from deterministic fields
(:class:`ArticleOutline`, which adds ``category``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src import config
from src.llm import LLMProvider, get_provider
from src.llm.tracing import traced

PLANNER_SYSTEM_PROMPT = (
    "You are a news article outline planner. A user has provided raw material in any shape — "
    "a quote, a dense research brief, a handful of facts, or a one-liner. Your job is to "
    "produce a structured outline the downstream writer will follow verbatim.\n\n"
    "HARD CONSTRAINTS:\n"
    "• Do NOT invent, infer, or import outside knowledge. Every fact you emit must trace to "
    "the user's material.\n"
    "• PRESERVE NAMED ENTITIES. When extracting facts, keep every named person (with title/role), "
    "every organization, every place, every date, and every number exactly as they appear in the "
    "source. The writer may only use entities that appear in your extracted_facts list — "
    "paraphrasing a person out of the list effectively erases them from the article.\n"
    "• If the material lacks AT LEAST one actor + one action/event + one verifiable detail "
    "(date / figure / location / direct quote), set sufficient=false and give a one-sentence "
    "rejection_reason. Leave the other fields empty.\n"
    "• When sufficient, choose target_word_count based on material density, using the corpus "
    "baseline supplied in the style preamble as a reference (not a floor). A thin but workable "
    "story is a 200–300 word brief, not a padded 800-word piece.\n"
    "• Preserve verbatim quotes in quote_anchors exactly as written — the writer will place them.\n"
    "• Honor the user's override target_word_count if supplied; otherwise decide yourself."
)


class SectionPlan(BaseModel):
    """One section of the planned article."""

    angle: str = Field(..., description="One-sentence description of what this section covers.")


class PlannerObservations(BaseModel):
    """Fields the LLM fills. Assembled into an :class:`ArticleOutline` with deterministic ``category``."""

    sufficient: bool = Field(
        ...,
        description=(
            "False only if material is catastrophically thin (missing actor OR action OR "
            "any verifiable detail)."
        ),
    )
    rejection_reason: str | None = Field(
        None,
        description="Populated only when sufficient=False; one-sentence explanation of what's missing.",
    )
    extracted_facts: list[str] = Field(
        default_factory=list,
        description=(
            "Canonical fact list lifted verbatim or minimally rephrased from the user's material. "
            "No inference, no outside knowledge."
        ),
    )
    quote_anchors: list[str] = Field(
        default_factory=list,
        description="Verbatim quotes from the user material that should be preserved in the final article.",
    )
    target_word_count: int = Field(
        0,
        description=(
            "Planner-decided article length based on material density. 200–300 brief, "
            "500–700 standard, 800–1000 only with rich material. 0 if sufficient=False."
        ),
    )
    headline_options: list[str] = Field(
        default_factory=list,
        description="2–3 candidate headlines, ≤12 words each. Writer picks one.",
    )
    lede_angle: str = Field(
        "",
        description="One-sentence description of the lede's angle.",
    )
    sections: list[SectionPlan] = Field(
        default_factory=list,
        description="3–5 section plans in order.",
    )


class ArticleOutline(BaseModel):
    """Structured plan handed off to the writer agent.

    Deterministic ``category`` (from the user's CLI flag) plus everything the
    planner observed.
    """

    category: str
    sufficient: bool
    rejection_reason: str | None
    extracted_facts: list[str]
    quote_anchors: list[str]
    target_word_count: int
    headline_options: list[str]
    lede_angle: str
    sections: list[SectionPlan]


def _build_planner_prompt(
    preamble: str,
    category: str,
    raw_material: str,
    target_words_override: int | None,
) -> str:
    parts = [
        f"Category: {category}",
        "",
        "Style preamble (for target_word_count calibration only — voice is the writer's concern):",
        "",
        preamble.strip(),
        "",
        "---",
        "",
        "User-provided raw material:",
        "",
        raw_material.strip(),
    ]
    if target_words_override is not None:
        parts += [
            "",
            "---",
            "",
            f"User override: target_word_count = {target_words_override}. Honor this exactly.",
        ]
    return "\n".join(parts)


@traced("planner")
def plan_article(
    category: str,
    raw_material: str,
    target_words_override: int | None = None,
    provider: LLMProvider | None = None,
) -> ArticleOutline:
    """Build a structured :class:`ArticleOutline` from raw user material.

    Gates on sufficiency: if the material lacks an actor, action, or verifiable
    detail, the returned outline has ``sufficient=False`` and a ``rejection_reason``.
    """
    provider = provider or get_provider()
    preamble = (config.STYLE_GUIDE_DIR / "_preamble.md").read_text()
    user_prompt = _build_planner_prompt(preamble, category, raw_material, target_words_override)
    obs = provider.complete_structured(
        system=PLANNER_SYSTEM_PROMPT,
        user=user_prompt,
        schema=PlannerObservations,
        temperature=0.2,
    )
    if target_words_override is not None and obs.sufficient:
        obs = obs.model_copy(update={"target_word_count": target_words_override})
    return ArticleOutline(category=category, **obs.model_dump())
