"""Shared LLM factory for agent nodes."""

import httpx
from langchain_openrouter import ChatOpenRouter

from agentic_claims.agents.shared.governedChatOpenRouter import GovernedChatOpenRouter


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


def buildGovernedAgentLlm(
    settings,
    agent_identity: str,
    temperature: float = 0.1,
    useFallback: bool = False,
    reasoning: dict | None = None,
) -> GovernedChatOpenRouter:
    """Build ChatOpenRouter with B1/B2 content governance for background agents.
    
    Wraps the base buildAgentLlm() so compliance/fraud/advisor get automatic
    B1 (injection) + B2 (PII) checks on both input prompts and output responses.
    
    Background agents (compliance/fraud/advisor):
    - Run governance via contentHookRuntime_background (NO chat notices)
    - Capture structured fired_controls for embedding in *Findings JSONB
    - Audit automatically via shared sink (unified correlation)
    
    Args:
        settings: Application Settings
        agent_identity: Agent name for governance correlation ("compliance"|"fraud"|"advisor")
        temperature: LLM temperature
        useFallback: Use fallback model
        reasoning: Optional reasoning config
    
    Returns:
        GovernedChatOpenRouter wrapper with pre/post content hooks
    """
    from agentic_claims.core.graph import contentHookRuntime_background
    
    base_llm = buildAgentLlm(settings, temperature, useFallback, reasoning)
    
    # Return wrapped LLM with background governance (no chat notices)
    return GovernedChatOpenRouter(
        base_llm=base_llm,
        agent_identity=agent_identity,
        content_hook_runtime=contentHookRuntime_background,
    )
