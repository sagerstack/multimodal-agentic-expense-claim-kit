"""Chat router: POST /chat/message, GET /chat/stream, POST /chat/reset."""

import asyncio
import base64
import logging
import uuid

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.sse import EventSourceResponse, ServerSentEvent
from starlette.requests import Request
from starlette.responses import Response

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.imageStore import clearImage, getImage, getImagePath, storeImage
from agentic_claims.core.logging import logEvent
from agentic_claims.web.employeeIdContext import employeeIdVar
from agentic_claims.web.imagePathContext import imagePathVar
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.sessionQueues import getOrCreateQueue, removeQueue
from agentic_claims.web.sseHelpers import runGraph, runPostSubmissionAgents
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat/message")
async def postMessage(
    request: Request,
    message: str = Form(default=""),
    receipt: UploadFile | None = File(default=None),
):
    """Accept a chat message, enqueue graph input, return 204."""
    sessionIds = getSessionIds(request)
    threadId = sessionIds["threadId"]
    claimId = sessionIds["claimId"]

    hasImage = False
    imageB64 = None
    if receipt and receipt.filename:
        imageBytes = await receipt.read()
        imageB64 = base64.b64encode(imageBytes).decode("utf-8")
        hasImage = True

    employeeId = request.session.get("employee_id")
    username = request.session.get("username")
    draftClaimNumber = f"DRAFT-{claimId[:8]}"

    # Auto-reset session when user sends any message after claim submission
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": threadId}}
    try:
        priorState = await graph.aget_state(config)
        if priorState and priorState.values and priorState.values.get("claimSubmitted"):
            # Reset session: new thread_id, new claim_id, clear old resources
            oldClaimId = claimId
            oldThreadId = threadId
            if oldClaimId:
                clearImage(oldClaimId)
            if oldThreadId:
                removeQueue(oldThreadId)
            # Generate new IDs
            request.session["thread_id"] = str(uuid.uuid4())
            request.session["claim_id"] = str(uuid.uuid4())
            request.session.pop("awaiting_clarification", None)
            request.session.pop("draft_created", None)
            request.session.pop("draft_claim_id", None)
            # Update local vars for rest of handler
            threadId = request.session["thread_id"]
            claimId = request.session["claim_id"]
            draftClaimNumber = f"DRAFT-{claimId[:8]}"
            logEvent(
                logger,
                "chat.auto_reset",
                logCategory="chat_history",
                actorType="app",
                userId=username,
                username=username,
                employeeId=employeeId,
                claimId=claimId,
                threadId=threadId,
                status="completed",
                payload={"oldClaimId": oldClaimId, "oldThreadId": oldThreadId, "trigger": "claimSubmitted"},
                message="Session auto-reset after claim submission",
            )
    except Exception:
        pass  # If state check fails, continue normally

    # Store image under the (possibly new) claimId
    if hasImage and imageB64:
        storeImage(claimId, imageB64)

    logEvent(
        logger,
        "user.chat_message_submitted",
        logCategory="chat_history",
        actorType="user",
        userId=username,
        username=username,
        employeeId=employeeId,
        claimId=claimId,
        draftClaimNumber=draftClaimNumber,
        threadId=threadId,
        status="received",
        payload={
            "message": message,
            "receiptFilename": receipt.filename if receipt else None,
            "hasImage": hasImage,
        },
        message="User chat message submitted",
    )

    # Create draft claim on first message in session
    if not request.session.get("draft_created"):
        try:
            settings = getSettings()
            draftResult = await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertClaim",
                arguments={
                    "claimNumber": draftClaimNumber,
                    "employeeId": employeeId,
                    "status": "draft",
                    "totalAmount": 0,
                    "currency": "SGD",
                    "idempotencyKey": f"draft_{claimId}",
                },
            )
            if isinstance(draftResult, dict) and "id" in draftResult:
                request.session["draft_claim_id"] = draftResult["id"]
            elif isinstance(draftResult, dict):
                claimData = draftResult.get("claim", {})
                if isinstance(claimData, dict) and "id" in claimData:
                    request.session["draft_claim_id"] = claimData["id"]
            request.session["draft_created"] = True
            logEvent(
                logger,
                "claim.draft_created",
                logCategory="chat_history",
                actorType="app",
                userId=username,
                username=username,
                employeeId=employeeId,
                claimId=claimId,
                dbClaimId=request.session.get("draft_claim_id"),
                draftClaimNumber=draftClaimNumber,
                threadId=threadId,
                status="completed",
                payload={"result": draftResult},
                message="Draft claim created",
            )
        except Exception as e:
            logEvent(
                logger,
                "claim.draft_failed",
                level=logging.WARNING,
                logCategory="chat_history",
                actorType="app",
                userId=username,
                username=username,
                employeeId=employeeId,
                claimId=claimId,
                draftClaimNumber=draftClaimNumber,
                threadId=threadId,
                status="failed",
                errorType=type(e).__name__,
                payload={"error": str(e)},
                message="Draft claim creation failed",
            )

    awaitingClarification = request.session.get("awaiting_clarification", False)

    graphInput = {
        "threadId": threadId,
        "claimId": claimId,
        "message": message,
        "hasImage": hasImage,
        "isResume": awaitingClarification,
    }

    if awaitingClarification:
        graphInput["resumeData"] = {"response": message, "action": "confirm"}
        request.session["awaiting_clarification"] = False

    queue = getOrCreateQueue(threadId)
    await queue.put(graphInput)

    return Response(status_code=204)


@router.get("/chat/stream", response_class=EventSourceResponse)
async def streamChat(request: Request):
    """SSE endpoint that reads from per-session queue and streams graph events."""
    sessionIds = getSessionIds(request)
    threadId = sessionIds["threadId"]
    queue = getOrCreateQueue(threadId)
    graph = request.app.state.graph

    while True:
        if await request.is_disconnected():
            break
        try:
            graphInput = await asyncio.wait_for(queue.get(), timeout=30.0)
        except asyncio.TimeoutError:
            yield ServerSentEvent(comment="ping")
            continue

        logEvent(
            logger,
            "agent.turn_queued",
            logCategory="agent",
            actorType="app",
            employeeId=request.session.get("employee_id"),
            username=request.session.get("username"),
            agent="intake",
            claimId=sessionIds["claimId"],
            draftClaimNumber=f"DRAFT-{sessionIds['claimId'][:8]}",
            threadId=graphInput.get("threadId"),
            status="queued",
            payload={"graphInput": graphInput},
            message="Agent turn queued",
        )

        try:
            employeeIdVar.set(request.session.get("employee_id"))
            imagePathVar.set(getImagePath(sessionIds["claimId"]))

            async for sseEvent in runGraph(graph, graphInput, request, templates):
                yield sseEvent

            logEvent(
                logger,
                "agent.turn_stream_completed",
                logCategory="agent",
                actorType="app",
                employeeId=request.session.get("employee_id"),
                username=request.session.get("username"),
                agent="intake",
                claimId=sessionIds["claimId"],
                draftClaimNumber=f"DRAFT-{sessionIds['claimId'][:8]}",
                threadId=graphInput.get("threadId"),
                status="completed",
                message="Agent turn stream completed",
            )
        except Exception as e:
            logger.exception("SSE stream error: %s", e)
            yield ServerSentEvent(raw_data=str(e), event="error")

        yield ServerSentEvent(raw_data="<!-- done -->", event="done")

        # BUG-026: launch background task for post-submission agents if flagged
        backgroundTask = getattr(request.state, "backgroundTask", None)
        if backgroundTask:
            asyncio.create_task(
                runPostSubmissionAgents(
                    backgroundTask["graph"],
                    backgroundTask["threadId"],
                    backgroundTask["claimId"],
                )
            )
            request.state.backgroundTask = None
            logger.info(
                "Background post-submission task launched for claim %s", backgroundTask["claimId"]
            )


@router.get("/chat/receipt-image")
async def getReceiptImage(request: Request):
    """Serve the receipt image for the current session as image/jpeg."""
    sessionIds = getSessionIds(request)
    claimId = sessionIds["claimId"]
    imageB64 = getImage(claimId)
    if not imageB64:
        return Response(status_code=404, content="No receipt image")
    imageBytes = base64.b64decode(imageB64)
    return Response(content=imageBytes, media_type="image/jpeg")


@router.post("/chat/reset")
async def resetChat(request: Request):
    """Clear session state, remove queue, redirect to /."""
    oldClaimId = request.session.get("claim_id")
    oldThreadId = request.session.get("thread_id")

    if oldClaimId:
        clearImage(oldClaimId)
    if oldThreadId:
        removeQueue(oldThreadId)

    request.session["thread_id"] = str(uuid.uuid4())
    request.session["claim_id"] = str(uuid.uuid4())
    request.session.pop("awaiting_clarification", None)
    request.session.pop("draft_created", None)
    request.session.pop("draft_claim_id", None)

    logEvent(
        logger,
        "chat.reset",
        logCategory="chat_history",
        actorType="user",
        employeeId=request.session.get("employee_id"),
        username=request.session.get("username"),
        claimId=request.session["claim_id"],
        threadId=request.session["thread_id"],
        status="completed",
        payload={"oldClaimId": oldClaimId, "oldThreadId": oldThreadId},
        message="Chat reset",
    )

    return Response(status_code=204, headers={"HX-Redirect": "/"})


async def fetchClaimsForTable(employeeId: str | None = None) -> list[dict]:
    """Fetch recent claims with receipt data from DB via MCP for the submission table.

    When employeeId is provided, only returns claims belonging to that user.
    """
    try:
        settings = getSettings()
        query = (
            "SELECT c.id, c.claim_number, c.employee_id, c.status, "
            "c.total_amount, c.currency, c.category, c.created_at, "
            "r.merchant, r.date as receipt_date, "
            "r.original_amount, r.original_currency, r.converted_amount_sgd, "
            "r.line_items "
            "FROM claims c LEFT JOIN receipts r ON r.claim_id = c.id "
        )
        if employeeId:
            query += f"WHERE c.employee_id = $${employeeId}$$ "
        query += "ORDER BY c.created_at DESC LIMIT 50"

        result = await mcpCallTool(
            serverUrl=settings.db_mcp_url,
            toolName="executeQuery",
            arguments={"query": query},
        )
        if isinstance(result, list):
            for row in result:
                rawTs = row.get("created_at", "")
                if rawTs and isinstance(rawTs, str) and "T" in rawTs:
                    try:
                        from datetime import datetime

                        dt = datetime.fromisoformat(rawTs.replace("Z", "+00:00"))
                        from zoneinfo import ZoneInfo

                        sgt = dt.astimezone(ZoneInfo("Asia/Singapore"))
                        row["created_at"] = sgt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        row["created_at"] = rawTs[:16].replace("T", " ")

                if not row.get("category"):
                    lineItems = row.get("line_items")
                    if not lineItems:
                        row["category"] = "--"
                        continue
                    try:
                        import json as _json

                        items = _json.loads(lineItems) if isinstance(lineItems, str) else lineItems
                        if isinstance(items, list) and items:
                            row["category"] = items[0].get("category", "--")
                        else:
                            row["category"] = "--"
                    except Exception:
                        row["category"] = "--"

            return result
        if isinstance(result, dict) and "error" in result:
            logger.warning("fetchClaimsForTable DB error: %s", result["error"])
            return []
        return []
    except Exception as e:
        logger.warning("fetchClaimsForTable failed: %s", e)
        return []
