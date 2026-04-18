"""Writer agent — drafts a BBC-style article from an outline.

The style guide is injected into the system prompt so the model writes in
the correct register. Takes the :class:`ArticleOutline` from the planner
and returns a full Markdown draft.
"""

from __future__ import annotations

from src.agents.planner import ArticleOutline


def build_system_prompt(style_guide: str) -> str:
    """Return the writer system prompt, with the style guide embedded as context."""
    raise NotImplementedError


def write_article(outline: ArticleOutline, style_guide: str) -> str:
    """Draft a full Markdown article from the outline, in the style of the guide."""
    raise NotImplementedError


def revise_article(draft: str, editor_feedback: str, style_guide: str) -> str:
    """Apply editor feedback to an existing draft and return a revised Markdown article."""
    raise NotImplementedError
