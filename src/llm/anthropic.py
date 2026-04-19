"""Anthropic-backed :class:`LLMProvider` implementation.

Structured output is implemented via a forced single tool call — the
model can only respond by invoking a tool whose input schema matches the
requested pydantic schema.
"""

from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from src import config

T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or config.ANTHROPIC_API_KEY)
        self.default_model = default_model or config.ANTHROPIC_MODEL

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        resp = self.client.messages.create(
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

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
        tool_name = schema.__name__
        resp = self.client.messages.create(
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": tool_name,
                    "description": f"Emit a {tool_name} object.",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == tool_name:
                return schema.model_validate(block.input)
        raise RuntimeError(f"Anthropic did not return a {tool_name} tool call")
