"""Image quality detection using OpenCV Laplacian variance."""

import cv2
import numpy as np


def checkImageQuality(imageBytes: bytes, threshold: float, minWidth: int, minHeight: int) -> dict:
    """Check if image meets resolution requirements for VLM extraction.

    Resolution check is orientation-aware and uses two guards:
      - Long side must be at least `minWidth` pixels (rejects images too
        small in both dimensions regardless of orientation).
      - Total pixel count must be at least `minWidth * minHeight`
        (protects the VLM from tiny thumbnails while allowing narrow
        portrait-orientation receipts where the short side may be
        smaller than `minHeight` as long as the total pixel count is
        sufficient — e.g. a 428×2040 receipt has 873K pixels which is
        higher than the 480K required by 800×600 defaults).

    Readability (blur, text clarity) is delegated to the VLM via the
    isReadable field in its response — Laplacian variance cannot reliably
    distinguish a blurry image from a receipt with large uniform areas.

    Args:
        imageBytes: Raw image bytes (JPEG, PNG, etc.)
        threshold: Laplacian variance threshold (computed but not enforced).
        minWidth: Required long-side minimum in pixels.
        minHeight: Used with `minWidth` to derive the minimum pixel count
            threshold (minWidth * minHeight).

    Returns:
        Dict with keys:
        - acceptable (bool): Whether image passes resolution check
        - variance (float): Laplacian variance score (informational)
        - resolution (tuple): Image dimensions (width, height)
        - reason (str): Explanation if rejected, empty string if accepted
    """
    npArray = np.frombuffer(imageBytes, np.uint8)
    image = cv2.imdecode(npArray, cv2.IMREAD_COLOR)

    if image is None:
        return {
            "acceptable": False,
            "variance": 0.0,
            "resolution": (0, 0),
            "reason": "Failed to decode image",
        }

    height, width = image.shape[:2]
    resolution = (width, height)

    longSide = max(width, height)
    pixelCount = width * height
    minPixels = minWidth * minHeight

    if longSide < minWidth:
        return {
            "acceptable": False,
            "variance": 0.0,
            "resolution": resolution,
            "reason": (
                f"Resolution too low: {width}x{height} "
                f"(required long side>={minWidth}px)"
            ),
        }

    if pixelCount < minPixels:
        return {
            "acceptable": False,
            "variance": 0.0,
            "resolution": resolution,
            "reason": (
                f"Resolution too low: {width}x{height} = {pixelCount} pixels "
                f"(required >={minPixels} pixels total)"
            ),
        }

    # Compute Laplacian variance for informational purposes only.
    # Readability judgment is delegated to the VLM (isReadable field).
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()

    return {
        "acceptable": True,
        "variance": float(variance),
        "resolution": resolution,
        "reason": "",
    }
