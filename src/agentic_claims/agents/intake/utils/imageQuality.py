"""Image quality detection using OpenCV Laplacian variance."""

import cv2
import numpy as np


def checkImageQuality(imageBytes: bytes, threshold: float, minWidth: int, minHeight: int) -> dict:
    """Check if image meets quality requirements for VLM extraction.

    Args:
        imageBytes: Raw image bytes (JPEG, PNG, etc.)
        threshold: Laplacian variance threshold for blur detection
        minWidth: Minimum acceptable image width in pixels
        minHeight: Minimum acceptable image height in pixels

    Returns:
        Dict with keys:
        - acceptable (bool): Whether image passes quality checks
        - variance (float): Laplacian variance score
        - resolution (tuple): Image dimensions (width, height)
        - reason (str): Explanation if rejected, empty string if accepted
    """
    # Decode image bytes to numpy array
    npArray = np.frombuffer(imageBytes, np.uint8)
    image = cv2.imdecode(npArray, cv2.IMREAD_COLOR)

    if image is None:
        return {
            "acceptable": False,
            "variance": 0.0,
            "resolution": (0, 0),
            "reason": "Failed to decode image",
        }

    # Get image dimensions
    height, width = image.shape[:2]
    resolution = (width, height)

    # Check resolution first
    if width < minWidth or height < minHeight:
        return {
            "acceptable": False,
            "variance": 0.0,
            "resolution": resolution,
            "reason": f"Resolution too low: {width}x{height} (minimum: {minWidth}x{minHeight})",
        }

    # Convert to grayscale for blur detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Compute Laplacian variance
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()

    # Check if image is blurry
    if variance < threshold:
        return {
            "acceptable": False,
            "variance": float(variance),
            "resolution": resolution,
            "reason": f"Image is blurry (variance: {variance:.2f}, threshold: {threshold})",
        }

    # All checks passed
    return {
        "acceptable": True,
        "variance": float(variance),
        "resolution": resolution,
        "reason": "",
    }
