"""Unit tests for intake audit logging (buffer + flush pattern)."""

from unittest.mock import AsyncMock, patch

import pytest


# Reset the module-level buffer before each test to ensure isolation
@pytest.fixture(autouse=True)
def clearAuditBuffer():
    """Clear the audit buffer before each test."""
    from agentic_claims.agents.intake import auditLogger

    auditLogger._auditBuffer.clear()
    yield
    auditLogger._auditBuffer.clear()


# ---------------------------------------------------------------------------
# bufferStep tests
# ---------------------------------------------------------------------------


def testBufferStepAccumulatesEntries():
    """bufferStep appends entries to the buffer for the given session."""
    from agentic_claims.agents.intake.auditLogger import _auditBuffer, bufferStep

    sessionId = "session-abc-123"

    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "/tmp/receipt.jpg"})
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.9, "merchant": "Starbucks"})
    bufferStep(sessionId, "policy_check", {"violations": [], "compliant": True})

    assert len(_auditBuffer[sessionId]) == 3
    assert _auditBuffer[sessionId][0]["action"] == "receipt_uploaded"
    assert _auditBuffer[sessionId][1]["action"] == "ai_extraction"
    assert _auditBuffer[sessionId][2]["action"] == "policy_check"


def testAuditBufferIsolatedBySession():
    """Buffer entries for different session IDs do not interfere."""
    from agentic_claims.agents.intake.auditLogger import _auditBuffer, bufferStep

    bufferStep("session-A", "receipt_uploaded", {"imagePath": "a.jpg"})
    bufferStep("session-B", "receipt_uploaded", {"imagePath": "b.jpg"})
    bufferStep("session-A", "ai_extraction", {"confidence": 0.8})

    assert len(_auditBuffer["session-A"]) == 2
    assert len(_auditBuffer["session-B"]) == 1
    assert _auditBuffer["session-A"][0]["details"]["imagePath"] == "a.jpg"
    assert _auditBuffer["session-B"][0]["details"]["imagePath"] == "b.jpg"


# ---------------------------------------------------------------------------
# flushSteps tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testFlushStepsCallsMcpForEachEntry():
    """flushSteps makes one MCP insertAuditLog call per buffered entry."""
    from agentic_claims.agents.intake.auditLogger import bufferStep, flushSteps

    sessionId = "session-flush-1"
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "x.jpg"})
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.85})
    bufferStep(sessionId, "policy_check", {"violations": [], "compliant": True})

    mockMcp = AsyncMock(return_value={"id": 1, "timestamp": "2026-04-05T10:00:00"})

    with patch("agentic_claims.agents.intake.auditLogger.mcpCallTool", mockMcp):
        await flushSteps(sessionClaimId=sessionId, dbClaimId=42)

    assert mockMcp.call_count == 3

    # Verify each call passes the correct claimId and action
    calls = mockMcp.call_args_list
    actions = [c.kwargs["arguments"]["action"] for c in calls]
    assert "receipt_uploaded" in actions
    assert "ai_extraction" in actions
    assert "policy_check" in actions

    for call in calls:
        assert call.kwargs["arguments"]["claimId"] == 42
        assert call.kwargs["arguments"]["actor"] == "intake_agent"


@pytest.mark.asyncio
async def testFlushStepsClearsBuffer():
    """Buffer for the session is empty after flushSteps completes."""
    from agentic_claims.agents.intake.auditLogger import _auditBuffer, bufferStep, flushSteps

    sessionId = "session-flush-2"
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "y.jpg"})

    with patch("agentic_claims.agents.intake.auditLogger.mcpCallTool", AsyncMock()):
        await flushSteps(sessionClaimId=sessionId, dbClaimId=99)

    assert sessionId not in _auditBuffer


@pytest.mark.asyncio
async def testFlushStepsHandlesMcpFailureGracefully():
    """flushSteps continues and clears buffer even if an MCP call raises."""
    from agentic_claims.agents.intake.auditLogger import _auditBuffer, bufferStep, flushSteps

    sessionId = "session-flush-error"
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "z.jpg"})
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.7})

    mockMcp = AsyncMock(side_effect=RuntimeError("MCP unavailable"))

    # Must not raise
    with patch("agentic_claims.agents.intake.auditLogger.mcpCallTool", mockMcp):
        await flushSteps(sessionClaimId=sessionId, dbClaimId=77)

    # Buffer cleared despite errors
    assert sessionId not in _auditBuffer


# ---------------------------------------------------------------------------
# logIntakeStep tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testLogIntakeStepCallsMcp():
    """logIntakeStep calls insertAuditLog via MCP with correct arguments."""
    from agentic_claims.agents.intake.auditLogger import logIntakeStep

    mockMcp = AsyncMock(return_value={"id": 5, "timestamp": "2026-04-05T11:00:00"})

    with patch("agentic_claims.agents.intake.auditLogger.mcpCallTool", mockMcp):
        await logIntakeStep(
            claimId=10,
            action="final_decision",
            details={"decision": "ai_approved", "confidence": 0.95},
        )

    mockMcp.assert_called_once()
    call = mockMcp.call_args
    assert call.kwargs["toolName"] == "insertAuditLog"
    assert call.kwargs["arguments"]["claimId"] == 10
    assert call.kwargs["arguments"]["action"] == "final_decision"
    assert call.kwargs["arguments"]["actor"] == "intake_agent"
    assert '"decision": "ai_approved"' in call.kwargs["arguments"]["newValue"]


@pytest.mark.asyncio
async def testLogIntakeStepHandlesError():
    """logIntakeStep does not raise when MCP call fails."""
    from agentic_claims.agents.intake.auditLogger import logIntakeStep

    mockMcp = AsyncMock(side_effect=ConnectionError("unreachable"))

    # Must not raise
    with patch("agentic_claims.agents.intake.auditLogger.mcpCallTool", mockMcp):
        await logIntakeStep(claimId=99, action="test_step", details={"x": 1})


# ---------------------------------------------------------------------------
# BUG-018: deduplication tests
# ---------------------------------------------------------------------------


def testBufferStepDeduplicatesActionPerSession():
    """BUG-018: calling bufferStep twice for the same action in one session only stores one entry."""
    from agentic_claims.agents.intake.auditLogger import _auditBuffer, bufferStep

    sessionId = "session-dedup-001"

    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "first.jpg"})
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "second.jpg"})  # duplicate action

    entries = _auditBuffer[sessionId]
    actions = [e["action"] for e in entries]
    assert actions.count("receipt_uploaded") == 1


def testBufferStepDeduplicatesAcrossMultipleTurnActions():
    """BUG-018: a full multi-turn scenario — receipt_uploaded + ai_extraction buffered twice each."""
    from agentic_claims.agents.intake.auditLogger import _auditBuffer, bufferStep

    sessionId = "session-dedup-002"

    # Turn 1 buffers
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "r.jpg"})
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.9})
    bufferStep(sessionId, "policy_check", {"violations": []})

    # Turn 2: intakeNode re-scans all messages and buffers the same actions again
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "r.jpg"})
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.9})
    bufferStep(sessionId, "policy_check", {"violations": []})

    entries = _auditBuffer[sessionId]
    assert len(entries) == 3  # exactly one entry per unique action


@pytest.mark.asyncio
async def testFlushStepsOnlyFlushesUniqueActions():
    """BUG-018: after dedup, flush makes exactly one MCP call per unique action."""
    from agentic_claims.agents.intake.auditLogger import bufferStep, flushSteps

    sessionId = "session-dedup-flush"

    # Simulate two turns each buffering the same steps
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "x.jpg"})
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.88})
    bufferStep(sessionId, "receipt_uploaded", {"imagePath": "x.jpg"})  # duplicate
    bufferStep(sessionId, "ai_extraction", {"confidence": 0.88})  # duplicate

    mockMcp = AsyncMock(return_value={"id": 1})

    with patch("agentic_claims.agents.intake.auditLogger.mcpCallTool", mockMcp):
        await flushSteps(sessionClaimId=sessionId, dbClaimId=55)

    # Only 2 unique actions → 2 MCP calls
    assert mockMcp.call_count == 2
    actions = [c.kwargs["arguments"]["action"] for c in mockMcp.call_args_list]
    assert sorted(actions) == ["ai_extraction", "receipt_uploaded"]
