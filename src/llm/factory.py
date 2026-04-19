"""Pick an :class:`LLMProvider` based on which API key is configured."""

from __future__ import annotations

from src import config
from src.llm.anthropic import AnthropicProvider
from src.llm.base import LLMProvider
from src.llm.openrouter import OpenRouterProvider


def get_provider() -> LLMProvider:
    """Return OpenRouter if its key is set, else Anthropic, else raise."""
    if config.OPENROUTER_API_KEY:
        return OpenRouterProvider()
    if config.ANTHROPIC_API_KEY:
        return AnthropicProvider()
    raise RuntimeError(
        "No LLM provider configured — set OPENROUTER_API_KEY or ANTHROPIC_API_KEY in .env."
    )
