"""Regression tests for Plan 001 bug fixes."""

from unittest.mock import AsyncMock, patch

import pytest


def testActiveIntakePromptDoesNotAskForEmployeeId():
    from agentic_claims.agents.intake.prompts.agentSystemPrompt_v2 import (
        INTAKE_AGENT_SYSTEM_PROMPT,
    )

    prompt = INTAKE_AGENT_SYSTEM_PROMPT
    assert "Please also provide your employee ID" not in prompt
    assert "Do not ask for or parse employee ID" in prompt
    assert "authenticated session employee ID" in prompt


@pytest.mark.asyncio
async def testSubmitClaimOmitsFinalIdempotencyKeyAndInjectsSessionEmployeeId():
    from agentic_claims.agents.intake.tools.submitClaim import submitClaim
    from agentic_claims.web.employeeIdContext import employeeIdVar

    with patch(
        "agentic_claims.agents.intake.tools.submitClaim.mcpCallTool", new_callable=AsyncMock
    ) as mockMcpCall:
        mockMcpCall.return_value = {
            "claim": {"id": 44, "claim_number": "CLAIM-044"},
            "receipt": {"id": 144, "claim_id": 44},
        }

        token = employeeIdVar.set("EMP-SESSION")
        try:
            await submitClaim.ainvoke(
                {
                    "claimData": {"claimantId": "EMP-LLM", "amountSgd": 25.5, "currency": "SGD"},
                    "receiptData": {
                        "merchant": "Cafe",
                        "date": "2026-04-10",
                        "totalAmount": 25.5,
                        "currency": "SGD",
                    },
                    "intakeFindings": {"policyViolation": None},
                }
            )
        finally:
            employeeIdVar.reset(token)

    arguments = mockMcpCall.call_args.kwargs["arguments"]
    assert "idempotencyKey" not in arguments
    assert arguments["employeeId"] == "EMP-SESSION"
    assert arguments["intakeFindings"]["employeeId"] == "EMP-SESSION"


@pytest.mark.asyncio
async def testFetchClaimsForTableUsesClaimCategoryAndEmployeeFilter():
    from agentic_claims.web.routers.chat import fetchClaimsForTable

    with patch(
        "agentic_claims.web.routers.chat.mcpCallTool", new_callable=AsyncMock
    ) as mockMcpCall:
        mockMcpCall.return_value = [
            {
                "id": 1,
                "claim_number": "CLAIM-001",
                "employee_id": "EMP001",
                "status": "pending",
                "total_amount": 12.0,
                "currency": "SGD",
                "category": "office_supplies",
                "created_at": "2026-04-10T08:00:00+00:00",
                "line_items": [{"category": "meals"}],
            }
        ]

        rows = await fetchClaimsForTable(employeeId="EMP001")

    query = mockMcpCall.call_args.kwargs["arguments"]["query"]
    assert "c.category" in query
    assert "WHERE c.employee_id = $$EMP001$$" in query
    assert rows[0]["category"] == "office_supplies"


def testBuildPathwayStepsMakesExtractionCompletedWhenPolicyCompleted():
    from agentic_claims.web.sseHelpers import _buildPathwaySteps

    steps = _buildPathwaySteps(
        completedTools={"searchPolicies"},
        activeTools=set(),
        hasImage=True,
        toolTimestamps={"receiptUploaded": "01:00:00 PM", "searchPolicies": "01:01:00 PM"},
    )

    assert steps[1]["name"] == "AI Extraction"
    assert steps[1]["status"] == "completed"
    assert steps[2]["name"] == "Policy Check"
    assert steps[2]["status"] == "completed"


@pytest.mark.asyncio
async def testFraudDuplicateQueryExcludesCurrentClaimId():
    from agentic_claims.agents.fraud.tools.queryClaimsHistory import exactDuplicateCheck

    with patch(
        "agentic_claims.agents.fraud.tools.queryClaimsHistory.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockMcpCall:
        mockMcpCall.return_value = []
        await exactDuplicateCheck("EMP001", "Cafe", "2026-04-10", 20.0, excludeClaimId=44)

    query = mockMcpCall.call_args.kwargs["arguments"]["query"]
    assert "c.id != 44" in query


@pytest.mark.asyncio
async def testChatPagePreservesExistingSessionIds():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.staticfiles import StaticFiles

    from agentic_claims.web.main import projectRoot
    from agentic_claims.web.routers.pages import router as pagesRouter

    fakeUser = {
        "userId": 1,
        "username": "testuser",
        "role": "user",
        "employeeId": "EMP001",
        "displayName": "Test User",
    }

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", session_cookie="test_session")
    app.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    app.include_router(pagesRouter)

    with (
        patch("agentic_claims.web.routers.pages.getCurrentUser", return_value=fakeUser),
        patch(
            "agentic_claims.web.routers.pages.fetchClaimsForTable", new_callable=AsyncMock
        ) as mockFetchClaims,
    ):
        mockFetchClaims.return_value = []
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response1 = await client.get("/")
            response2 = await client.get("/")

    assert response1.status_code == 200
    assert response2.status_code == 200
    thread1 = response1.text.split("threadId: '")[1].split("'")[0]
    thread2 = response2.text.split("threadId: '")[1].split("'")[0]
    assert thread1 == thread2


def testCurrencyToolErrorProducesCorrectionMessage():
    from agentic_claims.web.sseHelpers import _currencyCorrectionMessage

    message = _currencyCorrectionMessage(
        'Frankfurter API error: 422 {"message":"bad currency pair"}'
    )

    assert message is not None
    assert "3-letter code" in message
    assert "SGD" in message
