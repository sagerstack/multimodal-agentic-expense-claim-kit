"""OpenRouter model client for LLM and VLM calls with retry logic.

DEPRECATED: Replaced by langchain_openai.ChatOpenAI with OpenRouter base_url.
Kept for backward compatibility. Will be removed in a future phase.
"""

import asyncio
from typing import Optional

from openai import AsyncOpenAI

from agentic_claims.core.config import Settings


class OpenRouterClient:
    """OpenRouter client with retry logic for LLM and VLM calls."""

    def __init__(self, settings: Settings):
        """Initialize OpenRouter client with settings.

        Args:
            settings: Settings instance containing OpenRouter configuration
        """
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
        )

    async def callLlm(self, messages: list[dict], model: Optional[str] = None) -> str:
        """Call LLM model with retry logic.

        Args:
            messages: List of message dicts with role and content
            model: Model name (defaults to settings.openrouter_model_llm)

        Returns:
            Model response text

        Raises:
            Exception: If all retries fail
        """
        model_name = model or self.settings.openrouter_model_llm

        for attempt in range(self.settings.openrouter_max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model_name, messages=messages
                )
                return response.choices[0].message.content

            except Exception as e:
                if attempt == self.settings.openrouter_max_retries - 1:
                    # Last attempt failed, re-raise
                    raise
                # Sleep before retry
                await asyncio.sleep(self.settings.openrouter_retry_delay)

        # Should never reach here due to re-raise above
        raise RuntimeError(f"Failed after {self.settings.openrouter_max_retries} retries")

    async def callVlm(self, text: str, imageUrl: str, model: Optional[str] = None) -> str:
        """Call vision-language model with image.

        Args:
            text: Text prompt
            imageUrl: URL to image
            model: Model name (defaults to settings.openrouter_model_vlm)

        Returns:
            Model response text

        Raises:
            Exception: If all retries fail
        """
        model_name = model or self.settings.openrouter_model_vlm

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": imageUrl}},
                ],
            }
        ]

        return await self.callLlm(messages, model=model_name)
