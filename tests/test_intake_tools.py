"""Tests for Intake Agent tools (policy search, currency conversion, claim submission, human clarification)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_claims.agents.intake.tools.askHuman import askHuman
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
    """Verify submitClaim calls insertClaim and insertReceipt with FK link."""
    mockClaimResult = {"claim_id": 123, "claim_number": "CLM-001"}
    mockReceiptResult = {"receipt_id": 456, "claim_id": 123}

    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        # First call returns claim, second call returns receipt
        mockMcpCall.side_effect = [mockClaimResult, mockReceiptResult]

        claimData = {
            "employeeId": "EMP-001",
            "totalAmount": 100.0,
            "currency": "SGD",
        }
        receiptData = {
            "merchant": "Test Merchant",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }

        await submitClaim.ainvoke({"claimData": claimData, "receiptData": receiptData})

        # Verify mcpCallTool called twice
        assert mockMcpCall.call_count == 2

        # First call: insertClaim
        firstCall = mockMcpCall.call_args_list[0]
        firstArgs = firstCall[0]
        toolName1 = firstArgs[1] if len(firstArgs) > 1 else firstCall[1].get("toolName")
        assert toolName1 == "insertClaim"

        # Second call: insertReceipt with claim_id
        secondCall = mockMcpCall.call_args_list[1]
        secondArgs = secondCall[0]
        toolName2 = secondArgs[1] if len(secondArgs) > 1 else secondCall[1].get("toolName")
        arguments2 = secondArgs[2] if len(secondArgs) > 2 else secondCall[1].get("arguments")
        assert toolName2 == "insertReceipt"
        assert arguments2["claimId"] == 123  # FK from first call


@pytest.mark.asyncio
async def testSubmitClaimReturnsClaimAndReceiptRecords():
    """Verify submitClaim returns both claim and receipt records."""
    mockClaimResult = {"claim_id": 123, "claim_number": "CLM-001"}
    mockReceiptResult = {"receipt_id": 456, "claim_id": 123}

    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.side_effect = [mockClaimResult, mockReceiptResult]

        claimData = {"employeeId": "EMP-001", "totalAmount": 100.0, "currency": "SGD"}
        receiptData = {
            "merchant": "Test Merchant",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }

        result = await submitClaim.ainvoke({"claimData": claimData, "receiptData": receiptData})

        assert "claim" in result
        assert "receipt" in result
        assert result["claim"]["claim_id"] == 123
        assert result["receipt"]["receipt_id"] == 456


@pytest.mark.asyncio
async def testSubmitClaimHandlesError():
    """Verify submitClaim surfaces errors without calling insertReceipt."""
    with patch("agentic_claims.agents.intake.tools.submitClaim.mcpCallTool") as mockMcpCall:
        mockMcpCall.return_value = {"error": "Database connection failed"}

        claimData = {"employeeId": "EMP-001", "totalAmount": 100.0, "currency": "SGD"}
        receiptData = {
            "merchant": "Test",
            "date": "2026-03-25",
            "totalAmount": 100.0,
            "currency": "SGD",
            "lineItems": [],
        }

        result = await submitClaim.ainvoke({"claimData": claimData, "receiptData": receiptData})

        # Should only be called once (insertClaim), not twice
        assert mockMcpCall.call_count == 1
        assert "error" in result


# ==================== askHuman Tests ====================


def testAskHumanCallsInterrupt():
    """Verify askHuman calls LangGraph interrupt."""
    with patch("agentic_claims.agents.intake.tools.askHuman.interrupt") as mockInterrupt:
        mockInterrupt.return_value = {"action": "confirm", "data": {}}

        askHuman.invoke({"question": "Is this correct?", "data": {"amount": 100}})

        # Verify interrupt was called once
        mockInterrupt.assert_called_once()

        # Verify payload contains question and data
        callArgs = mockInterrupt.call_args[0]
        payload = callArgs[0] if len(callArgs) > 0 else mockInterrupt.call_args[1].get("value")
        assert payload["question"] == "Is this correct?"
        assert payload["data"]["amount"] == 100


def testAskHumanReturnsInterruptResponse():
    """Verify askHuman returns interrupt response."""
    mockResponse = {"action": "confirm", "data": {"correctedAmount": 150}}

    with patch("agentic_claims.agents.intake.tools.askHuman.interrupt") as mockInterrupt:
        mockInterrupt.return_value = mockResponse

        result = askHuman.invoke({"question": "Confirm amount?", "data": {}})

        assert result["action"] == "confirm"
        assert result["data"]["correctedAmount"] == 150
