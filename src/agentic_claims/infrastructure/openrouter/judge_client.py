"""OpenRouter-backed client adapter for governance LlmJudge.

Provides a minimal async interface compatible with agentic_governance.adapters.llm_judge.LlmJudge:
- complete(model: str, messages: list[dict]) -> OpenAI ChatCompletion-like response

Implementation uses openai.AsyncOpenAI pointed at the OpenRouter base_url.
All failures are expected to be handled gracefully by the caller (judge is
observe-only and must never break user flow).
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from openai import AsyncOpenAI


class OpenRouterJudgeClient:
    """Thin async client for LlmJudge, backed by OpenRouter (AsyncOpenAI).

    Args:
        api_key: OpenRouter API key
        base_url: OpenRouter base URL (e.g. https://openrouter.ai/api/v1)
        timeout: request timeout in seconds
    """

    def __init__(self, *, api_key: str, base_url: str, timeout: int | float = 60) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    async def complete(self, *, model: str, messages: list[dict[str, Any]]) -> Any:
        """Call chat.completions.create with the provided model and messages.

        Returns the full response object with .choices[0].message.content.
        Exceptions are propagated to the caller (who must swallow per B5).
        """
        return await self._client.chat.completions.create(model=model, messages=messages)

    # Optional sync shim if ever needed
    def complete_sync(self, *, model: str, messages: list[dict[str, Any]]) -> Any:
        return asyncio.run(self.complete(model=model, messages=messages))
