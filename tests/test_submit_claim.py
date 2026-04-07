"""Tests for submitClaim tool: confidenceScores injection and sessionClaimIdVar fallback."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from agentic_claims.agents.intake.extractionContext import (
    extractedReceiptVar,
    sessionClaimIdVar,
)
from agentic_claims.agents.intake.tools.submitClaim import submitClaim


def _makeSuccessResult(claimId=42, claimNumber="CLM-042"):
    return {"claim": {"id": claimId, "claim_number": claimNumber}, "receipt": {}}


def _baseClaimData():
    return {"claimantId": "EMP-001", "amountSgd": "25.00"}


def _baseReceiptData():
    return {"merchant": "Test Cafe", "date": "2026-04-07", "totalAmount": "25.00"}


# ── confidenceScores injection (BUG-028) ──


@pytest.mark.asyncio
async def testSubmitClaimInjectsConfidenceScoresFromContextVar():
    """BUG-028: confidenceScores from VLM extraction must be injected into intakeFindings."""
    confidence = {"merchant": 0.95, "totalAmount": 0.88, "date": 0.92}
    extractedReceipt = {"fields": {}, "confidence": confidence}

    capturedArgs = {}

    async def mockMcp(serverUrl, toolName, arguments):
        capturedArgs.update(arguments)
        return _makeSuccessResult()

    token = extractedReceiptVar.set(extractedReceipt)
    try:
        with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool", side_effect=mockMcp):
            with patch("agentic_claims.agents.intake.tools.submitClaim.flushSteps", new=AsyncMock()):
                result = await submitClaim.ainvoke(
                    {
                        "claimData": _baseClaimData(),
                        "receiptData": _baseReceiptData(),
                        "intakeFindings": {},
                    }
                )
    finally:
        extractedReceiptVar.reset(token)

    findings = capturedArgs.get("intakeFindings", {})
    assert "confidenceScores" in findings, "confidenceScores must be injected into intakeFindings"
    assert findings["confidenceScores"] == confidence


@pytest.mark.asyncio
async def testSubmitClaimDoesNotOverwriteExistingConfidenceScores():
    """BUG-028: when LLM already provides confidenceScores, do not overwrite them."""
    llmConfidence = {"merchant": 0.50, "totalAmount": 0.50}
    contextConfidence = {"merchant": 0.99, "totalAmount": 0.99}

    extractedReceipt = {"fields": {}, "confidence": contextConfidence}
    capturedArgs = {}

    async def mockMcp(serverUrl, toolName, arguments):
        capturedArgs.update(arguments)
        return _makeSuccessResult()

    token = extractedReceiptVar.set(extractedReceipt)
    try:
        with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool", side_effect=mockMcp):
            with patch("agentic_claims.agents.intake.tools.submitClaim.flushSteps", new=AsyncMock()):
                result = await submitClaim.ainvoke(
                    {
                        "claimData": _baseClaimData(),
                        "receiptData": _baseReceiptData(),
                        "intakeFindings": {"confidenceScores": llmConfidence},
                    }
                )
    finally:
        extractedReceiptVar.reset(token)

    findings = capturedArgs.get("intakeFindings", {})
    # LLM-provided scores must be preserved (not overwritten by context var)
    assert findings["confidenceScores"] == llmConfidence


@pytest.mark.asyncio
async def testSubmitClaimSkipsInjectionWhenNoContextVar():
    """BUG-028: when extractedReceiptVar is not set, no injection occurs."""
    capturedArgs = {}

    async def mockMcp(serverUrl, toolName, arguments):
        capturedArgs.update(arguments)
        return _makeSuccessResult()

    # Ensure no extractedReceiptVar is set (default None)
    token = extractedReceiptVar.set(None)
    try:
        with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool", side_effect=mockMcp):
            with patch("agentic_claims.agents.intake.tools.submitClaim.flushSteps", new=AsyncMock()):
                result = await submitClaim.ainvoke(
                    {
                        "claimData": _baseClaimData(),
                        "receiptData": _baseReceiptData(),
                        "intakeFindings": {"notes": "some notes"},
                    }
                )
    finally:
        extractedReceiptVar.reset(token)

    findings = capturedArgs.get("intakeFindings", {})
    assert "confidenceScores" not in findings


# ── sessionClaimIdVar fallback for flushSteps (BUG-027) ──


@pytest.mark.asyncio
async def testSubmitClaimUsesSessionClaimIdVarWhenLlmOmitsIt():
    """BUG-027: flushSteps must use sessionClaimIdVar when LLM doesn't pass sessionClaimId."""
    flushMock = AsyncMock()
    sessionId = "session-uuid-123"

    async def mockMcp(serverUrl, toolName, arguments):
        return _makeSuccessResult(claimId=99)

    claimIdToken = sessionClaimIdVar.set(sessionId)
    receiptToken = extractedReceiptVar.set(None)
    try:
        with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool", side_effect=mockMcp):
            with patch("agentic_claims.agents.intake.tools.submitClaim.flushSteps", flushMock):
                await submitClaim.ainvoke(
                    {
                        "claimData": _baseClaimData(),
                        "receiptData": _baseReceiptData(),
                        # sessionClaimId intentionally omitted
                    }
                )
    finally:
        sessionClaimIdVar.reset(claimIdToken)
        extractedReceiptVar.reset(receiptToken)

    flushMock.assert_called_once()
    callKwargs = flushMock.call_args
    assert callKwargs.kwargs.get("sessionClaimId") == sessionId or callKwargs.args[0] == sessionId


@pytest.mark.asyncio
async def testSubmitClaimExplicitSessionClaimIdTakesPrecedenceOverContextVar():
    """BUG-027: explicit sessionClaimId from LLM takes precedence over context var."""
    flushMock = AsyncMock()
    contextId = "context-uuid-111"
    llmId = "llm-uuid-222"

    async def mockMcp(serverUrl, toolName, arguments):
        return _makeSuccessResult(claimId=88)

    claimIdToken = sessionClaimIdVar.set(contextId)
    receiptToken = extractedReceiptVar.set(None)
    try:
        with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool", side_effect=mockMcp):
            with patch("agentic_claims.agents.intake.tools.submitClaim.flushSteps", flushMock):
                await submitClaim.ainvoke(
                    {
                        "claimData": _baseClaimData(),
                        "receiptData": _baseReceiptData(),
                        "sessionClaimId": llmId,
                    }
                )
    finally:
        sessionClaimIdVar.reset(claimIdToken)
        extractedReceiptVar.reset(receiptToken)

    flushMock.assert_called_once()
    callKwargs = flushMock.call_args
    # llmId must be used (it's the effective session claim id)
    effectiveId = callKwargs.kwargs.get("sessionClaimId") or (callKwargs.args[0] if callKwargs.args else None)
    assert effectiveId == llmId
