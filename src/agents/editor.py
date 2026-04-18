"""Editor / QA agent — scores a draft against the style guide.

Produces a numeric score plus targeted feedback the writer can act on.
Used to drive at least one revision loop before the final article is
returned to the user.
"""

from __future__ import annotations

from pydantic import BaseModel


class EditorReview(BaseModel):
    """Editor's assessment of a draft; ``score`` ranges 0–10."""

    score: float
    strengths: list[str]
    issues: list[str]
    suggested_revisions: list[str]
    approved: bool


def review_draft(draft: str, style_guide: str) -> EditorReview:
    """Score ``draft`` against ``style_guide`` and return structured feedback."""
    raise NotImplementedError
