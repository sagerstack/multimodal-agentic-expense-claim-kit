"""Shared LLM factory for agent nodes."""

import httpx
from langchain_openrouter import ChatOpenRouter


def buildAgentLlm(
    settings,
    temperature: float = 0.1,
    useFallback: bool = False,
    reasoning: dict | None = None,
) -> ChatOpenRouter:
    """Instantiate ChatOpenRouter for an agent node.

    Applies SSL bypass for Zscaler corporate proxy and selects primary or
    fallback model based on useFallback flag.

    Args:
        settings: Application Settings instance
        temperature: LLM temperature (default 0.1 for deterministic agent output)
        useFallback: If True, use fallback model instead of primary
        reasoning: Optional OpenRouter reasoning config

    Returns:
        Configured ChatOpenRouter instance
    """
    modelName = (
        settings.openrouter_fallback_model_llm if useFallback
        else settings.openrouter_model_llm
    )

    llm = ChatOpenRouter(
        model=modelName,
        openrouter_api_key=settings.openrouter_api_key,
        temperature=temperature,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
        reasoning=reasoning,
    )

    # Bypass SSL verification (Zscaler corporate proxy workaround)
    llm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
    llm.client.sdk_configuration.async_client = httpx.AsyncClient(verify=False, follow_redirects=True)

    return llm
