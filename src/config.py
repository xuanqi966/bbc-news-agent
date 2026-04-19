"""Central configuration: paths, env loading, model selection.

All other modules should import paths and model configs from here rather
than hardcoding strings, so the layout stays consistent across the pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLUSTERED_DIR = DATA_DIR / "clustered"
SCRAPED_DIR = DATA_DIR / "scraped"
EXAMPLES_DIR = DATA_DIR / "examples"

ANALYSIS_DIR = PROJECT_ROOT / "analysis"
STATIC_ANALYSIS_DIR = ANALYSIS_DIR / "static"
SEMANTIC_ANALYSIS_DIR = ANALYSIS_DIR / "semantic"

OUTPUT_DIR = PROJECT_ROOT / "output"
STYLE_GUIDE_DIR = OUTPUT_DIR / "style_guide"
GENERATED_DIR = OUTPUT_DIR / "generated"
TRACES_DIR = OUTPUT_DIR / "traces"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-6")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

OPENROUTER_EDITOR_MODEL = os.getenv("OPENROUTER_EDITOR_MODEL", "google/gemini-3.1-pro-preview")
ANTHROPIC_EDITOR_MODEL = os.getenv("ANTHROPIC_EDITOR_MODEL", "claude-opus-4-7")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def editor_model() -> str:
    """Return the model string for the editor role, matched to the active provider.

    Mirrors :func:`src.llm.factory.get_provider` selection order: OpenRouter first
    if its key is set, else Anthropic. Used by :func:`src.agents.editor.review_draft`
    to route the LLM-as-judge call to a stronger model than the writer uses.
    """
    if OPENROUTER_API_KEY:
        return OPENROUTER_EDITOR_MODEL
    return ANTHROPIC_EDITOR_MODEL


def ensure_dirs() -> None:
    """Create every output directory used by the pipeline if it doesn't exist."""
    for d in (
        RAW_DIR,
        CLUSTERED_DIR,
        SCRAPED_DIR,
        EXAMPLES_DIR,
        STATIC_ANALYSIS_DIR,
        SEMANTIC_ANALYSIS_DIR,
        OUTPUT_DIR,
        STYLE_GUIDE_DIR,
        GENERATED_DIR,
        TRACES_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
