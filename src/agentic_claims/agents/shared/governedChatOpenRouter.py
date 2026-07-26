"""Governed ChatOpenRouter wrapper — intercepts ainvoke for B1/B2 content checks.

Used by background agents (compliance/fraud/advisor) to run content governance
on model I/O without emitting live chat notices. Governance results are:
1. Automatically audited (via shared ContentHookRuntime audit sink)
2. Captured as structured fired_controls for embedding in *Findings JSONB

Intake-gpt uses a separate ContentHookRuntime with live chat notices (no regression).
"""

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openrouter import ChatOpenRouter

from agentic_claims.web.governanceNoticeContext import append_background_governance


class GovernedChatOpenRouter:
    """Wrapper around ChatOpenRouter that runs content governance on input/output.
    
    For background agents (compliance/fraud/advisor):
    - Runs B1/B2 (and B3/B4 if applicable) via ContentHookRuntime
    - Captures structured fired_controls for embedding in agent's *Findings
    - NO live chat notices (uses contentHookRuntime_background with notice_callback=None)
    - Auditing still happens (unified JSONL via shared sink)
    
    Delegates all LangChain BaseChatModel interface methods to the base LLM.
    """
    
    def __init__(
        self,
        *,
        base_llm: ChatOpenRouter,
        agent_identity: str,
        content_hook_runtime: Any,  # ContentHookRuntime instance (background, no chat notices)
    ):
        self._base_llm = base_llm
        self._agent_identity = agent_identity
        self._content_hook_runtime = content_hook_runtime
    
    async def ainvoke(
        self,
        input: list[BaseMessage] | str,
        config: Any = None,
        **kwargs: Any,
    ) -> AIMessage:
        """Async invoke with pre/post content checks.
        
        Captures structured fired_controls from governance results and appends
        to backgroundGovernanceVar for the agent node to drain and embed in findings.
        """
        from agentic_governance.core.content_envelope import ContentType
        
        # Extract correlation_id from config if available
        correlation_id = "unknown"
        if config and hasattr(config, "get"):
            configurable = config.get("configurable", {})
            correlation_id = configurable.get("thread_id", "unknown")
        
        # Extract latest content for pre-check
        latest_content = ""
        if isinstance(input, list):
            for msg in reversed(input):
                if hasattr(msg, "type") and msg.type in ("human", "system"):
                    latest_content = str(msg.content)
                    break
        else:
            latest_content = str(input)
        
        # Pre-check: run B1/B2 on input
        if self._content_hook_runtime and latest_content:
            pre_result = await self._content_hook_runtime.pre_model_check(
                content=latest_content,
                content_type=ContentType.CHAT_INPUT,
                correlation_id=correlation_id,
                agent_identity=self._agent_identity,
                context={"agent": self._agent_identity, "background": True},
            )
            
            # Capture structured fired_controls for findings embed
            if pre_result.fired_controls:
                for control in pre_result.fired_controls:
                    # Only capture actionable results (filter clean passes)
                    result = control.get("result", "")
                    if result in ("redacted", "escalated", "blocked", "flagged", "grounding-failed", "concerns-found"):
                        # PII-safe: controlId, name, result, entityTypes only (no raw content)
                        append_background_governance({
                            "control": control.get("controlId"),
                            "name": control.get("name"),
                            "result": result,
                            "entityTypes": control.get("entityTypes"),
                            "signalValue": control.get("signalValue"),
                        })
            
            # If governance blocked, return early with explanation
            if not pre_result.should_proceed:
                return AIMessage(
                    content=pre_result.explanation_employee or
                    "This request requires review. Please contact your manager."
                )
        
        # Call base LLM
        response = await self._base_llm.ainvoke(input, config, **kwargs)
        
        # Post-check: run B2 (PII) + B4 (judge if wired) on response
        if self._content_hook_runtime and response.content:
            post_result = await self._content_hook_runtime.post_model_check(
                content=str(response.content),
                content_type=ContentType.MODEL_OUTPUT,
                correlation_id=correlation_id,
                agent_identity=self._agent_identity,
                context={"agent": self._agent_identity, "background": True},
                trusted_state={},  # B3 runs separately on structured findings
                rag_clauses=None,
                required_evidence_fields=None,
            )
            
            # Capture structured fired_controls for findings embed
            if post_result.fired_controls:
                for control in post_result.fired_controls:
                    result = control.get("result", "")
                    if result in ("redacted", "escalated", "blocked", "flagged", "grounding-failed", "concerns-found"):
                        append_background_governance({
                            "control": control.get("controlId"),
                            "name": control.get("name"),
                            "result": result,
                            "entityTypes": control.get("entityTypes"),
                            "signalValue": control.get("signalValue"),
                        })
            
            # If PII redacted on output, replace content
            if post_result.content != str(response.content):
                response = AIMessage(
                    content=post_result.content,
                    additional_kwargs=response.additional_kwargs,
                    response_metadata=response.response_metadata,
                    id=response.id,
                )
        
        return response
    
    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> AIMessage:
        """Sync invoke (delegates to ainvoke via asyncio)."""
        return asyncio.run(self.ainvoke(input, config, **kwargs))
    
    # Delegate all other BaseChatModel methods to base_llm
    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_llm, name)
