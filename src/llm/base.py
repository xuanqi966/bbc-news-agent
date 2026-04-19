"""LLM provider abstraction.

Every LLM-calling module in the pipeline depends on this Protocol, not on
a concrete SDK. Implementations live in :mod:`src.llm.openrouter` and
:mod:`src.llm.anthropic`; :func:`src.llm.factory.get_provider` picks one
based on the configured API keys.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str: ...

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> T: ...
