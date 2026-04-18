"""Planner agent — turns a user topic into a structured article outline.

Consumes the style guide (as context) and the user's topic, emits a plan
covering headline, lede, section beats, and intended sourcing. The writer
agent consumes this plan downstream.
"""

from __future__ import annotations

from pydantic import BaseModel


class ArticleOutline(BaseModel):
    """Structured plan handed off to the writer agent."""

    headline: str
    lede: str
    sections: list[str]
    suggested_sources: list[str]


def plan_article(topic: str, style_guide: str) -> ArticleOutline:
    """Ask the LLM to produce a BBC-shaped outline for ``topic``, grounded in ``style_guide``."""
    raise NotImplementedError
