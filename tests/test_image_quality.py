"""Tests for image quality detection."""

import cv2
import numpy as np
import pytest

from agentic_claims.agents.intake.utils.imageQuality import checkImageQuality


pytestmark = pytest.mark.skip(reason="Image quality gate disabled in extractReceiptFields.")


@pytest.fixture
def sharpImageBytes() -> bytes:
    """Generate a sharp image with high variance (random noise)."""
    sharpImage = np.random.randint(0, 255, (800, 1000, 3), dtype=np.uint8)
    _, imageBytes = cv2.imencode(".jpg", sharpImage)
    return imageBytes.tobytes()


@pytest.fixture
def blurryImageBytes() -> bytes:
    """Generate a blurry image with low variance (solid gray)."""
    blurryImage = np.full((800, 1000, 3), 128, dtype=np.uint8)
    _, imageBytes = cv2.imencode(".jpg", blurryImage)
    return imageBytes.tobytes()


@pytest.fixture
def lowResolutionImageBytes() -> bytes:
    """Generate a low-resolution sharp image."""
    lowResImage = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)
    _, imageBytes = cv2.imencode(".jpg", lowResImage)
    return imageBytes.tobytes()


def testSharpImageAccepted(sharpImageBytes):
    """Verify sharp image with high variance is accepted."""
    result = checkImageQuality(
        imageBytes=sharpImageBytes, threshold=150.0, minWidth=800, minHeight=600
    )

    assert result["acceptable"] is True, "Sharp image should be accepted"
    assert result["variance"] > 150.0, "Sharp image variance should exceed threshold"


def testBlurryImageRejected(blurryImageBytes):
    """Verify blurry image with low variance is rejected."""
    result = checkImageQuality(
        imageBytes=blurryImageBytes, threshold=150.0, minWidth=800, minHeight=600
    )

    assert result["acceptable"] is False, "Blurry image should be rejected"
    assert "blurry" in result["reason"].lower(), "Reason should mention blur"
    assert result["variance"] < 150.0, "Blurry image variance should be below threshold"


def testLowResolutionRejected(lowResolutionImageBytes):
    """Verify low-resolution image is rejected."""
    result = checkImageQuality(
        imageBytes=lowResolutionImageBytes, threshold=150.0, minWidth=800, minHeight=600
    )

    assert result["acceptable"] is False, "Low-resolution image should be rejected"
    assert "resolution" in result["reason"].lower(), "Reason should mention resolution"


def testReturnedFieldsPresent(sharpImageBytes):
    """Verify result dict contains all required fields."""
    result = checkImageQuality(
        imageBytes=sharpImageBytes, threshold=150.0, minWidth=800, minHeight=600
    )

    requiredFields = ["acceptable", "variance", "resolution", "reason"]
    for field in requiredFields:
        assert field in result, f"Result should contain '{field}' field"

    # Verify resolution is a tuple with width and height
    assert isinstance(result["resolution"], tuple), "Resolution should be a tuple"
    assert len(result["resolution"]) == 2, "Resolution should have width and height"
