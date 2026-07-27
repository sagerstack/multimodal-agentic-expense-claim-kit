"""B4 LLM-judge integration tests (Group B4, observe-only).

Covers:
- Runtimes receive an injected judge via install_content_hooks(llm_judge=...)
- Intake path calls runtime.judge after assembling assistant reply; notice path fires
- Intake judge failure is graceful (no exception, reply preserved)
- Background agents call judge and embed PII-safe B4 result in findings.governance
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


class _FakeJudgeCritique:
    def __init__(self, concerns=(), confidence=0.9):
        self.concerns = tuple(concerns)
        self.confidence = confidence
        self.flags = ()
        self.contributed_to_escalation = False
        self.latency_ms = 1.0


class _FakeRuntime:
    def __init__(self, *, raise_on_judge=False, emit_notice=False):
        self._raise = raise_on_judge
        self._emit_notice = emit_notice

    async def judge(self, content: str, *, correlation_id: str, agent_identity: str, context=None):
        if self._raise:
            raise RuntimeError("judge-failure")
        # Optionally emit a small-red governance notice (intake path only)
        if self._emit_notice:
            from agentic_claims.web.governanceNoticeContext import append_notice
            append_notice(f"B4 concerns for {agent_identity}")
        return _FakeJudgeCritique(concerns=("risk",), confidence=0.85)


@pytest.mark.asyncio
async def test_install_injects_judge_into_both_runtimes(monkeypatch):
    # Stub OpenRouter judge client to avoid network
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")

    # Build graph, which installs governed boundary and content runtimes
    from agentic_claims.core.graph import buildGraph, contentHookRuntime, contentHookRuntime_background
    g = buildGraph()  # uncompiled is fine; side-effect installs runtimes
    assert g is not None

    # Assert: both runtimes present and expose judge()
    from agentic_claims.core import graph as _graph
    assert _graph.contentHookRuntime is not None
    assert _graph.contentHookRuntime_background is not None
    assert hasattr(_graph.contentHookRuntime, "judge")
    assert hasattr(_graph.contentHookRuntime_background, "judge")


@pytest.mark.asyncio
async def test_intake_calls_judge_and_emits_notice(monkeypatch):
    # Patch intake runtime with fake that emits a notice when judge runs
    with patch("agentic_claims.core.graph.contentHookRuntime", new=_FakeRuntime(emit_notice=True)):
        from agentic_claims.agents.intake_gpt.graph import reasonNode
        from agentic_claims.web.governanceNoticeContext import init_notice_queue, drain_notices

        # Minimal state and a no-op LLM that returns an AIMessage content
        class _NoopLLM:
            async def ainvoke(self, messages, *args, **kwargs):
                return AIMessage(content="hello from intake")

            def bind_tools(self, tools):
                return self

        init_notice_queue()
        result = await reasonNode({"claimId": "C-judge-1", "messages": [HumanMessage(content="hi")], "intakeGpt": {"workflow": {"currentStep": "plain_chat", "status": "active", "readyForSubmission": False}, "slots": {}, "pendingInterrupt": None, "lastUserTurn": {"message": "hi", "hasImage": False}, "toolTrace": {} }}, llm=_NoopLLM())
        # Judge emits a notice into the queue; reply is preserved
        notices = drain_notices()
        assert any("B4" in n for n in notices), f"Expected B4 notice, got {notices}"
        assert result["messages"], "Assistant reply should be preserved"


@pytest.mark.asyncio
async def test_intake_judge_failure_is_graceful(monkeypatch):
    # Patch intake runtime to raise in judge(); ensure no exception leaks and reply preserved
    with patch("agentic_claims.core.graph.contentHookRuntime", new=_FakeRuntime(raise_on_judge=True)):
        from agentic_claims.agents.intake_gpt.graph import reasonNode
        from agentic_claims.web.governanceNoticeContext import init_notice_queue, drain_notices

        class _NoopLLM:
            async def ainvoke(self, messages, *args, **kwargs):
                return AIMessage(content="hello from intake")
            def bind_tools(self, tools):
                return self

        init_notice_queue()
        result = await reasonNode({"claimId": "C-judge-2", "messages": [HumanMessage(content="hi")], "intakeGpt": {"workflow": {"currentStep": "plain_chat", "status": "active", "readyForSubmission": False}, "slots": {}, "pendingInterrupt": None, "lastUserTurn": {"message": "hi", "hasImage": False}, "toolTrace": {} }}, llm=_NoopLLM())
        notices = drain_notices()
        assert notices == [], f"No notices expected on judge failure, got {notices}"
        assert result["messages"], "Assistant reply should be preserved on judge failure"


@pytest.mark.asyncio
async def test_background_agents_embed_b4_in_findings(monkeypatch):
    # Patch background runtime with a fake that returns concerns
    with patch("agentic_claims.core.graph.contentHookRuntime_background", new=_FakeRuntime()):
        # Patch LLM factory to avoid network; return a static JSON body for parse
        with patch("agentic_claims.agents.shared.llmFactory.buildGovernedAgentLlm") as mock_llm_factory, \
             patch("agentic_claims.agents.intake.utils.mcpClient.mcpCallTool", new_callable=AsyncMock, return_value={"ok": True}):
            fake_llm = MagicMock()
            fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps({
                "verdict": "pass",
                "violations": [],
                "citedClauses": ["S1"],
                "requiresReview": False,
                "summary": "OK",
            })))
            mock_llm_factory.return_value = fake_llm

            # Minimal state for compliance node
            from agentic_claims.agents.compliance.node import complianceNode
            from agentic_claims.web.governanceNoticeContext import init_notice_queue, drain_notices
            init_notice_queue()
            state = {
                "claimId": "C-judge-bg-1",
                "dbClaimId": 1,
                "extractedReceipt": {"fields": {"category": "meals", "merchant": "Cafe", "totalAmount": 10.0, "currency": "SGD", "date": "2025-01-01"}},
                "intakeFindings": {},
                "violations": [],
            }
            result = await complianceNode(state)
            # Background agents must not emit chat notices
            notices = drain_notices()
            assert notices == [], f"Background agents must NOT emit chat notices; got {notices}"
            findings = result.get("complianceFindings", {})
            governance = findings.get("governance", [])
            # Assert a B4 entry embedded (PII-safe control id and signal only)
            assert any(g.get("control") == "B4" for g in governance), f"Expected B4 in governance, got {governance}"
