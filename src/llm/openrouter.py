"""OpenRouter-backed :class:`LLMProvider` implementation.

Uses the ``openai`` SDK pointed at OpenRouter's OpenAI-compatible endpoint.
Structured output goes through the ``response_format=json_schema`` path.
"""

from __future__ import annotations

from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from src import config

T = TypeVar("T", bound=BaseModel)


class OpenRouterProvider:
    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        self.client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=api_key or config.OPENROUTER_API_KEY,
        )
        self.default_model = default_model or config.OPENROUTER_MODEL

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        resp = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> T:
        resp = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            },
        )
        content = resp.choices[0].message.content or "{}"
        return schema.model_validate_json(content)
