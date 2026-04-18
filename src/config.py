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

ANALYSIS_DIR = PROJECT_ROOT / "analysis"
STATIC_ANALYSIS_DIR = ANALYSIS_DIR / "static"
SEMANTIC_ANALYSIS_DIR = ANALYSIS_DIR / "semantic"

OUTPUT_DIR = PROJECT_ROOT / "output"
STYLE_GUIDE_PATH = OUTPUT_DIR / "style_guide.md"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-6")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def ensure_dirs() -> None:
    """Create every output directory used by the pipeline if it doesn't exist."""
    for d in (
        RAW_DIR,
        CLUSTERED_DIR,
        SCRAPED_DIR,
        STATIC_ANALYSIS_DIR,
        SEMANTIC_ANALYSIS_DIR,
        OUTPUT_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
