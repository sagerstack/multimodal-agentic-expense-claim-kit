"""Tests for VLM receipt extraction tool."""

import base64
import json
from unittest.mock import AsyncMock, patch

import cv2
import numpy as np
import pytest

from agentic_claims.agents.intake.tools.extractReceiptFields import extractReceiptFields
from agentic_claims.core.imageStore import clearImage, storeImage

TEST_CLAIM_ID = "test-claim-001"


@pytest.fixture
def sharpImageB64() -> str:
    """Generate a sharp image and encode as base64."""
    sharpImage = np.random.randint(0, 255, (800, 1000, 3), dtype=np.uint8)
    _, imageBytes = cv2.imencode(".jpg", sharpImage)
    return base64.b64encode(imageBytes.tobytes()).decode("utf-8")


@pytest.fixture
def blurryImageB64() -> str:
    """Generate a blurry image and encode as base64."""
    blurryImage = np.full((800, 1000, 3), 128, dtype=np.uint8)
    _, imageBytes = cv2.imencode(".jpg", blurryImage)
    return base64.b64encode(imageBytes.tobytes()).decode("utf-8")


@pytest.fixture
def mockVlmResponse() -> dict:
    """Mock VLM extraction response with structured fields and confidence."""
    return {
        "fields": {
            "merchant": "Acme Corp",
            "date": "2024-03-15",
            "totalAmount": 125.50,
            "currency": "USD",
            "lineItems": [
                {"description": "Office Supplies", "amount": 100.00},
                {"description": "Shipping", "amount": 25.50},
            ],
            "tax": 12.50,
            "paymentMethod": "Credit Card",
        },
        "confidence": {
            "merchant": 0.95,
            "date": 0.92,
            "totalAmount": 0.98,
            "currency": 0.99,
            "lineItems": 0.88,
            "tax": 0.85,
            "paymentMethod": 0.90,
        },
    }


@pytest.fixture(autouse=True)
def cleanupImageStore():
    """Clean up image store after each test."""
    yield
    clearImage(TEST_CLAIM_ID)


@pytest.mark.asyncio
async def testBlurryImageReturnsError(blurryImageB64):
    """Verify blurry image returns error dict without calling VLM."""
    storeImage(TEST_CLAIM_ID, blurryImageB64)
    result = await extractReceiptFields.ainvoke({"claimId": TEST_CLAIM_ID})

    assert "error" in result, "Should return error dict for blurry image"
    assert "blurry" in result["error"].lower() or "quality" in result["error"].lower()


@pytest.mark.asyncio
async def testNoImageReturnsError():
    """Verify missing image returns error dict."""
    result = await extractReceiptFields.ainvoke({"claimId": "nonexistent-claim"})

    assert "error" in result, "Should return error dict when no image stored"
    assert "no receipt image" in result["error"].lower()


@pytest.mark.asyncio
async def testVlmCalledWithCorrectPrompt(sharpImageB64, mockVlmResponse):
    """Verify VLM receives multimodal message with base64 image and extraction prompt."""
    storeImage(TEST_CLAIM_ID, sharpImageB64)
    mockVlm = AsyncMock()
    mockVlm.ainvoke.return_value.content = json.dumps(mockVlmResponse)

    with patch("agentic_claims.agents.intake.tools.extractReceiptFields.ChatOpenRouter") as MockChatOpenRouter:
        MockChatOpenRouter.return_value = mockVlm

        result = await extractReceiptFields.ainvoke({"claimId": TEST_CLAIM_ID})

        # Verify VLM was called
        assert mockVlm.ainvoke.called, "VLM should be called for sharp image"

        # Get the messages passed to VLM
        callArgs = mockVlm.ainvoke.call_args[0][0]
        assert len(callArgs) > 0, "Should pass messages to VLM"

        # Verify message contains image and prompt
        message = callArgs[0]
        messageContent = str(message.content)

        # Should contain image reference and extraction instructions
        assert "base64" in messageContent.lower() or "image_url" in messageContent.lower()


@pytest.mark.asyncio
async def testExtractedFieldsStructure(sharpImageB64, mockVlmResponse):
    """Verify returned dict has correct structure with fields and confidence."""
    storeImage(TEST_CLAIM_ID, sharpImageB64)
    mockVlm = AsyncMock()
    mockVlm.ainvoke.return_value.content = json.dumps(mockVlmResponse)

    with patch("agentic_claims.agents.intake.tools.extractReceiptFields.ChatOpenRouter") as MockChatOpenRouter:
        MockChatOpenRouter.return_value = mockVlm

        result = await extractReceiptFields.ainvoke({"claimId": TEST_CLAIM_ID})

        # Verify top-level structure
        assert "fields" in result, "Result should contain 'fields'"
        assert "confidence" in result, "Result should contain 'confidence'"

        # Verify all expected fields present
        expectedFields = [
            "merchant",
            "date",
            "totalAmount",
            "currency",
            "lineItems",
            "tax",
            "paymentMethod",
        ]
        for field in expectedFields:
            assert field in result["fields"], f"Fields should contain '{field}'"
            assert field in result["confidence"], f"Confidence should contain '{field}'"


@pytest.mark.asyncio
async def testInvalidVlmResponseHandled(sharpImageB64):
    """Verify non-JSON VLM response returns error dict without raising exception."""
    storeImage(TEST_CLAIM_ID, sharpImageB64)
    mockVlm = AsyncMock()
    mockVlm.ainvoke.return_value.content = "Invalid JSON response"

    with patch("agentic_claims.agents.intake.tools.extractReceiptFields.ChatOpenRouter") as MockChatOpenRouter:
        MockChatOpenRouter.return_value = mockVlm

        result = await extractReceiptFields.ainvoke({"claimId": TEST_CLAIM_ID})

        assert "error" in result, "Should return error dict for invalid JSON"
        assert "parse" in result["error"].lower() or "json" in result["error"].lower()
