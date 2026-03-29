"""Tests for Intake Agent tools (policy search, currency conversion, claim submission)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_claims.agents.intake.tools.convertCurrency import convertCurrency
from agentic_claims.agents.intake.tools.searchPolicies import searchPolicies
from agentic_claims.agents.intake.tools.submitClaim import submitClaim


# ==================== searchPolicies Tests ====================


@pytest.mark.asyncio
async def testSearchPoliciesCallsMcpWithCorrectArgs():
    """Verify searchPolicies calls MCP with correct arguments."""
    with patch("agentic_claims.agents.intake.tools.searchPolicies.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = [{"type": "text", "text": "Policy result"}]

        await searchPolicies.ainvoke({"query": "meal limit"})

        # Verify mcpCallTool was called once
        mockMcpCall.assert_called_once()
        callArgs = mockMcpCall.call_args[0]
        callKwargs = mockMcpCall.call_args[1] if mockMcpCall.call_args[1] else {}

        # Verify arguments: serverUrl contains rag_mcp_url, toolName is "searchPolicies", arguments dict
        assert len(callArgs) == 3 or "serverUrl" in callKwargs
        # Verify tool name
        toolName = callArgs[1] if len(callArgs) > 1 else callKwargs.get("toolName")
        assert toolName == "searchPolicies"
        # Verify arguments include query and limit
        arguments = callArgs[2] if len(callArgs) > 2 else callKwargs.get("arguments")
        assert arguments["query"] == "meal limit"
        assert arguments["limit"] == 5


@pytest.mark.asyncio
async def testSearchPoliciesReturnsFormattedResults():
    """Verify searchPolicies returns formatted policy results."""
    mockResults = [
        {
            "text": "Meal expenses up to $50",
            "file": "policy.md",
            "category": "meals",
            "section": "Meal Limits",
            "score": 0.95,
        },
        {
            "text": "Receipt required for all meal claims",
            "file": "policy.md",
            "category": "meals",
            "section": "Documentation",
            "score": 0.88,
        },
    ]

    with patch("agentic_claims.agents.intake.tools.searchPolicies.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = mockResults

        result = await searchPolicies.ainvoke({"query": "meal policy"})

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["text"] == "Meal expenses up to $50"
        assert result[0]["score"] == 0.95


@pytest.mark.asyncio
async def testSearchPoliciesHandlesMcpError():
    """Verify searchPolicies handles MCP errors gracefully."""
    with patch("agentic_claims.agents.intake.tools.searchPolicies.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = {"error": "Connection failed"}

        result = await searchPolicies.ainvoke({"query": "test"})

        assert isinstance(result, dict)
        assert "error" in result


# ==================== convertCurrency Tests ====================


@pytest.mark.asyncio
async def testConvertCurrencyCallsMcpWithCorrectArgs():
    """Verify convertCurrency calls MCP with correct arguments."""
    with patch("agentic_claims.agents.intake.tools.convertCurrency.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = {
            "originalAmount": 50.0,
            "convertedAmount": 67.5,
            "rate": 1.35,
            "date": "2026-03-25",
        }

        await convertCurrency.ainvoke({"amount": 50.0, "fromCurrency": "USD", "toCurrency": "SGD"})

        # Verify mcpCallTool was called once
        mockMcpCall.assert_called_once()
        callArgs = mockMcpCall.call_args[0]
        callKwargs = mockMcpCall.call_args[1] if mockMcpCall.call_args[1] else {}

        # Verify tool name
        toolName = callArgs[1] if len(callArgs) > 1 else callKwargs.get("toolName")
        assert toolName == "convertCurrency"

        # Verify arguments
        arguments = callArgs[2] if len(callArgs) > 2 else callKwargs.get("arguments")
        assert arguments["amount"] == 50.0
        assert arguments["fromCurrency"] == "USD"
        assert arguments["toCurrency"] == "SGD"


@pytest.mark.asyncio
async def testConvertCurrencyReturnsConversionResult():
    """Verify convertCurrency returns conversion result."""
    mockResult = {
        "originalAmount": 100.0,
        "convertedAmount": 135.0,
        "rate": 1.35,
        "date": "2026-03-25",
    }

    with patch("agentic_claims.agents.intake.tools.convertCurrency.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = mockResult

        result = await convertCurrency.ainvoke({"amount": 100.0, "fromCurrency": "USD", "toCurrency": "SGD"})

        assert result["originalAmount"] == 100.0
        assert result["convertedAmount"] == 135.0
        assert result["rate"] == 1.35
        assert result["date"] == "2026-03-25"


# ==================== submitClaim Tests ====================


@pytest.mark.asyncio
async def testSubmitClaimCallsInsertClaimAndInsertReceipt():
    """Verify submitClaim makes single atomic MCP call with merged data."""
    mockResult = {
        "claim": {"id": 123, "claim_number": "CLM-001"},
        "receipt": {"id": 456, "claim_id": 123}
    }

    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = mockResult

        claimData = {
            "claimNumber": "CLM-001",
            "employeeId": "EMP-001",
            "status": "pending",
            "totalAmount": 100.0,
            "currency": "SGD",
        }
        receiptData = {
            "number": "REC-001",
            "merchant": "Test Merchant",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }
        intakeFindings = {"mismatches": [], "overrides": [], "redFlags": []}

        await submitClaim.ainvoke({
            "claimData": claimData,
            "receiptData": receiptData,
            "intakeFindings": intakeFindings
        })

        # Verify mcpCallTool called once (not twice)
        assert mockMcpCall.call_count == 1

        # Verify single call to insertClaim with merged arguments
        callArgs = mockMcpCall.call_args[0]
        callKwargs = mockMcpCall.call_args[1] if mockMcpCall.call_args[1] else {}
        toolName = callArgs[1] if len(callArgs) > 1 else callKwargs.get("toolName")
        assert toolName == "insertClaim"

        # Verify merged arguments include claim data, receipt data (prefixed), and intake findings
        arguments = callArgs[2] if len(callArgs) > 2 else callKwargs.get("arguments")
        assert arguments["claimNumber"] == "CLM-001"
        assert arguments["employeeId"] == "EMP-001"
        assert arguments["receiptNumber"] == "REC-001"
        assert arguments["receiptMerchant"] == "Test Merchant"
        assert arguments["intakeFindings"] == intakeFindings


@pytest.mark.asyncio
async def testSubmitClaimReturnsClaimAndReceiptRecords():
    """Verify submitClaim returns both claim and receipt records from single MCP call."""
    mockResult = {
        "claim": {"id": 123, "claim_number": "CLM-001"},
        "receipt": {"id": 456, "claim_id": 123}
    }

    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = mockResult

        claimData = {
            "claimNumber": "CLM-001",
            "employeeId": "EMP-001",
            "status": "pending",
            "totalAmount": 100.0,
            "currency": "SGD"
        }
        receiptData = {
            "number": "REC-001",
            "merchant": "Test Merchant",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }

        result = await submitClaim.ainvoke({"claimData": claimData, "receiptData": receiptData})

        assert "claim" in result
        assert "receipt" in result
        assert result["claim"]["id"] == 123
        assert result["receipt"]["id"] == 456


@pytest.mark.asyncio
async def testSubmitClaimHandlesError():
    """Verify submitClaim surfaces MCP errors."""
    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = {"error": "Database connection failed"}

        claimData = {
            "claimNumber": "CLM-001",
            "employeeId": "EMP-001",
            "status": "pending",
            "totalAmount": 100.0,
            "currency": "SGD"
        }
        receiptData = {
            "number": "REC-001",
            "merchant": "Test",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }

        result = await submitClaim.ainvoke({"claimData": claimData, "receiptData": receiptData})

        # Should only be called once
        assert mockMcpCall.call_count == 1
        assert "error" in result


@pytest.mark.asyncio
async def testSubmitClaimHandlesStringResponse():
    """Verify submitClaim parses string JSON response."""
    mockJsonString = '{"claim": {"id": 123}, "receipt": {"id": 456}}'

    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = mockJsonString

        claimData = {
            "claimNumber": "CLM-001",
            "employeeId": "EMP-001",
            "status": "pending",
            "totalAmount": 100.0,
            "currency": "SGD"
        }
        receiptData = {
            "number": "REC-001",
            "merchant": "Test",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }

        result = await submitClaim.ainvoke({"claimData": claimData, "receiptData": receiptData})

        # Should parse string to dict
        assert isinstance(result, dict)
        assert "claim" in result
        assert result["claim"]["id"] == 123


@pytest.mark.asyncio
async def testSubmitClaimPassesIntakeFindings():
    """Verify submitClaim includes intakeFindings in MCP call."""
    mockResult = {
        "claim": {"id": 123, "intake_findings": {"mismatches": ["test"]}},
        "receipt": {"id": 456}
    }

    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = mockResult

        claimData = {
            "claimNumber": "CLM-001",
            "employeeId": "EMP-001",
            "status": "pending",
            "totalAmount": 100.0,
            "currency": "SGD"
        }
        receiptData = {
            "number": "REC-001",
            "merchant": "Test",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }
        intakeFindings = {
            "mismatches": ["Receipt amount differs from extracted total"],
            "overrides": [],
            "redFlags": []
        }

        result = await submitClaim.ainvoke({
            "claimData": claimData,
            "receiptData": receiptData,
            "intakeFindings": intakeFindings
        })

        # Verify intakeFindings passed to MCP call
        callArgs = mockMcpCall.call_args[0]
        callKwargs = mockMcpCall.call_args[1] if mockMcpCall.call_args[1] else {}
        arguments = callArgs[2] if len(callArgs) > 2 else callKwargs.get("arguments")
        assert arguments["intakeFindings"] == intakeFindings
