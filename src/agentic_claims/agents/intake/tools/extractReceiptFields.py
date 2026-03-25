"""VLM receipt extraction tool with image quality gate."""

import base64
import json

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agentic_claims.agents.intake.prompts.vlmExtractionPrompt import VLM_EXTRACTION_PROMPT
from agentic_claims.agents.intake.utils.imageQuality import checkImageQuality
from agentic_claims.core.config import getSettings


@tool
async def extractReceiptFields(imageB64: str) -> dict:
    """Extract structured receipt fields from image using VLM with quality gate.

    Args:
        imageB64: Base64-encoded image string

    Returns:
        Dict with either:
        - Success: {"fields": {...}, "confidence": {...}}
        - Error: {"error": "reason"}
    """
    # Get settings
    settings = getSettings()

    try:
        # Decode base64 to bytes
        imageBytes = base64.b64decode(imageB64)

        # Step 1: Check image quality
        qualityCheck = checkImageQuality(
            imageBytes=imageBytes,
            threshold=settings.image_quality_threshold,
            minWidth=settings.image_min_width,
            minHeight=settings.image_min_height,
        )

        # Step 2: Reject if quality is insufficient
        if not qualityCheck["acceptable"]:
            return {
                "error": f"Image quality check failed: {qualityCheck['reason']}. Please upload a clearer, higher-resolution image."
            }

        # Step 3: Instantiate VLM using existing Settings fields
        vlm = ChatOpenAI(
            model=settings.openrouter_model_vlm,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            temperature=0.0,
        )

        # Step 4: Build multimodal message with prompt + image
        message = HumanMessage(
            content=[
                {"type": "text", "text": VLM_EXTRACTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{imageB64}"},
                },
            ]
        )

        # Step 5: Call VLM
        response = await vlm.ainvoke([message])

        # Step 6: Parse JSON response
        try:
            result = json.loads(response.content)
            return result
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse VLM response as JSON: {str(e)}"}

    except Exception as e:
        return {"error": f"Extraction failed: {str(e)}"}
