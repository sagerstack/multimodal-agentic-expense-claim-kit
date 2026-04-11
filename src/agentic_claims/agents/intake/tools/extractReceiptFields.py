"""VLM receipt extraction tool with image quality gate."""

import base64
import json
import logging
import time

import httpx
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openrouter import ChatOpenRouter

from agentic_claims.agents.intake.extractionContext import extractedReceiptVar
from agentic_claims.agents.intake.prompts.vlmExtractionPrompt import VLM_EXTRACTION_PROMPT
from agentic_claims.agents.intake.utils.imageQuality import checkImageQuality
from agentic_claims.core.config import getSettings
from agentic_claims.core.imageStore import getImage, getImagePath
from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)


@tool
async def extractReceiptFields(claimId: str) -> dict:
    """Extract structured receipt fields from the uploaded receipt image using VLM with quality gate.

    Args:
        claimId: The claim ID whose receipt image should be processed

    Returns:
        Dict with either:
        - Success: {"fields": {...}, "confidence": {...}}
        - Error: {"error": "reason"}
    """
    toolStart = time.time()
    logEvent(logger, "tool.extractReceiptFields.started", logCategory="tool", toolName="extractReceiptFields", claimId=claimId)

    settings = getSettings()

    imageB64 = getImage(claimId)
    if not imageB64:
        return {"error": "No receipt image found. Please upload an image first."}

    try:
        # Decode base64 to bytes
        imageBytes = base64.b64decode(imageB64)

        # Step 1: Check image quality
        # Disabled: always continue to VLM extraction even for low-resolution or blurry images.
        # qualityCheck = checkImageQuality(
        #     imageBytes=imageBytes,
        #     threshold=settings.image_quality_threshold,
        #     minWidth=settings.image_min_width,
        #     minHeight=settings.image_min_height,
        # )
        #
        # if not qualityCheck["acceptable"]:
        #     return {
        #         "error": f"Image quality check failed: {qualityCheck['reason']}. Please upload a clearer, higher-resolution image."
        #     }
        #
        # logger.info(
        #     "extractReceiptFields quality check passed",
        #     extra={
        #         "elapsed": f"{time.time() - toolStart:.2f}s",
        #         "qualityScore": qualityCheck.get("score"),
        #     },
        # )

        # Step 3: Instantiate VLM using ChatOpenRouter
        vlm = ChatOpenRouter(
            model=settings.openrouter_model_vlm,
            openrouter_api_key=settings.openrouter_api_key,
            temperature=0.0,
            max_tokens=settings.openrouter_vlm_max_tokens,
        )

        # Bypass SSL verification (Zscaler corporate proxy workaround)
        vlm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
        vlm.client.sdk_configuration.async_client = httpx.AsyncClient(
            verify=False, follow_redirects=True
        )

        # Step 4: Build multimodal message with prompt + image (sent directly to VLM, not through LLM)
        message = HumanMessage(
            content=[
                {"type": "text", "text": VLM_EXTRACTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{imageB64}"},
                },
            ]
        )

        # Step 5: Call VLM with 402 fallback retry
        try:
            response = await vlm.ainvoke([message])
        except Exception as e:
            errorStr = str(e)
            # Check for 402 payment/quota errors
            if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
                logEvent(
                    logger,
                    "tool.extractReceiptFields.vlm_fallback",
                    level=logging.WARNING,
                    logCategory="tool",
                    toolName="extractReceiptFields",
                    claimId=claimId,
                    primaryModel=settings.openrouter_model_vlm,
                    fallbackModel=settings.openrouter_fallback_model_vlm,
                    error=errorStr,
                )
                # Retry with fallback VLM model
                fallbackVlm = ChatOpenRouter(
                    model=settings.openrouter_fallback_model_vlm,
                    openrouter_api_key=settings.openrouter_api_key,
                    temperature=0.0,
                    max_tokens=settings.openrouter_vlm_max_tokens,
                )
                # Bypass SSL verification (Zscaler corporate proxy workaround)
                fallbackVlm.client.sdk_configuration.client = httpx.Client(
                    verify=False, follow_redirects=True
                )
                fallbackVlm.client.sdk_configuration.async_client = httpx.AsyncClient(
                    verify=False, follow_redirects=True
                )
                response = await fallbackVlm.ainvoke([message])
            else:
                raise

        logEvent(
            logger,
            "tool.extractReceiptFields.vlm_completed",
            logCategory="tool",
            toolName="extractReceiptFields",
            claimId=claimId,
            elapsed=f"{time.time() - toolStart:.2f}s",
        )

        rawContent = response.content.strip()
        if rawContent.startswith("```"):
            # Remove opening ```json or ``` and closing ```
            lines = rawContent.split("\n")
            lines = lines[1:]  # Remove opening ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove closing ```
            rawContent = "\n".join(lines)

        try:
            result = json.loads(rawContent)
            logEvent(
                logger,
                "tool.extractReceiptFields.completed",
                logCategory="tool",
                toolName="extractReceiptFields",
                claimId=claimId,
                elapsed=f"{time.time() - toolStart:.2f}s",
                hasFields="fields" in result,
            )

            # Include imagePath in result so LLM passes it in receiptData.imagePath
            # and so intakeNode can buffer it in the receipt_uploaded audit step
            if "fields" in result:
                imagePath = getImagePath(claimId)
                if imagePath:
                    result["imagePath"] = imagePath

            # BUG-028: set ContextVar so submitClaim can inject numeric
            # confidenceScores into intakeFindings before DB write.
            # Must be set HERE (inside the tool) not in intakeNode
            # post-processing, because submitClaim runs before intakeNode
            # post-processing and ContextVars don't propagate child→parent.
            extractedReceiptVar.set(result)

            return result
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse VLM response as JSON: {str(e)}"}

    except Exception as e:
        return {"error": f"Extraction failed: {str(e)}"}
