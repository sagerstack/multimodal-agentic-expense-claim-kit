"""Chat router: POST /chat/message, GET /chat/stream, POST /chat/reset."""

import asyncio
import base64
import logging
import time
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
from agentic_claims.web.interruptDetection import isPausedAtInterrupt
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.sessionQueues import (
    QueueRotationSignal,
    getOrCreateQueue,
    popQueue,
    removeQueue,
)
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

    # Single-snapshot read: one graph.aget_state() per /chat/message request.
    # Both the auto-reset check and the resume detection below consume this
    # same StateSnapshot (ROADMAP Criterion 8; Bug 7). If an auto-reset
    # fires, the thread_id changes — the resume check then short-circuits to
    # False (a brand-new thread has no pending interrupts by construction).
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": threadId}}
    priorState = None
    priorStateFetchFailed = False
    try:
        t0 = time.time()
        priorState = await graph.aget_state(config)
        logEvent(
            logger,
            "sse.aget_state_timing",
            logCategory="chat",
            claimId=claimId,
            threadId=threadId,
            elapsedSeconds=round(time.time() - t0, 2),
            message="aget_state timing (chat/message single snapshot)",
        )
    except Exception as e:
        priorStateFetchFailed = True
        logEvent(
            logger,
            "chat.resume_check_failed",
            level=logging.WARNING,
            logCategory="chat",
            claimId=claimId,
            threadId=threadId,
            errorType=type(e).__name__,
            payload={"error": str(e)},
            message="Checkpointer read failed; treating as fresh turn (no auto-reset, no resume)",
        )

    # Auto-reset session when user sends any message after claim submission.
    # Consumes the single priorState snapshot fetched above.
    autoResetFired = False
    try:
        if priorState and priorState.values and priorState.values.get("claimSubmitted"):
            # Reset session: new thread_id, new claim_id, clear old resources
            oldClaimId = claimId
            oldThreadId = threadId
            oldDraftClaimId = request.session.get("draft_claim_id")
            if oldClaimId:
                clearImage(oldClaimId)
            # Preserve the just-closed conversation pointers for export. The
            # orphaned thread still exists in the checkpointer; exportChat
            # reads these to reconstruct the conversation post-rotation.
            request.session["last_closed_thread_id"] = oldThreadId
            request.session["last_closed_claim_id"] = oldClaimId
            request.session["last_closed_draft_claim_id"] = oldDraftClaimId
            # Generate new IDs FIRST so the rotation signal carries the new
            # threadId in-band. The SSE consumer cannot rely on
            # request.session for the rotated thread_id — its session dict
            # is frozen from the cookie snapshot at SSE connection time.
            newThreadId = str(uuid.uuid4())
            request.session["thread_id"] = newThreadId
            request.session["claim_id"] = str(uuid.uuid4())
            request.session.pop("draft_created", None)
            request.session.pop("draft_claim_id", None)
            # Pop the OLD queue and post a QueueRotationSignal carrying the
            # newThreadId. The SSE streamChat generator will consume it,
            # rebind to the new queue, and continue — without ever reading
            # request.session.
            # Source: 13-DEBUG-sse-session-stale.md (superseding 13-DEBUG-post-reset-stuck.md).
            if oldThreadId:
                oldQueue = popQueue(oldThreadId)
                if oldQueue is not None:
                    try:
                        oldQueue.put_nowait(QueueRotationSignal(newThreadId=newThreadId))
                    except asyncio.QueueFull:
                        # Queue is at maxsize; consumer will wake on its own
                        # when it drains. Log and continue — do not block the
                        # POST path.
                        logEvent(
                            logger,
                            "sse.auto_reset_sentinel_queue_full",
                            logCategory="sse",
                            threadId=oldThreadId,
                            message="Old queue full on auto_reset; rotation signal skipped",
                        )
            # Update local vars for rest of handler
            threadId = newThreadId
            claimId = request.session["claim_id"]
            draftClaimNumber = f"DRAFT-{claimId[:8]}"
            autoResetFired = True
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
        pass  # If auto-reset decision fails, continue normally

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

    # Resume detection: reuse the single priorState snapshot fetched above
    # (ROADMAP Criterion 8; Bug 7). If auto-reset fired, the thread_id is a
    # brand-new UUID whose checkpoint does not exist yet — no pending
    # interrupts by construction, so short-circuit to False without an extra
    # DB round-trip. If the earlier aget_state() call failed, priorState is
    # None and awaitingClarification stays False (the earlier except already
    # emitted chat.resume_check_failed).
    awaitingClarification = False
    if not autoResetFired and not priorStateFetchFailed:
        try:
            awaitingClarification = isPausedAtInterrupt(priorState)
        except Exception as e:
            logEvent(
                logger,
                "chat.resume_check_failed",
                level=logging.WARNING,
                logCategory="chat",
                claimId=claimId,
                threadId=threadId,
                errorType=type(e).__name__,
                payload={"error": str(e)},
                message="isPausedAtInterrupt raised on single snapshot; treating as fresh turn",
            )

    graphInput = {
        "threadId": threadId,
        "claimId": claimId,
        "message": message,
        "hasImage": hasImage,
        "isResume": awaitingClarification,
    }

    if awaitingClarification:
        intakeAgentMode = getSettings().intake_agent_mode.lower()
        if intakeAgentMode == "gpt":
            graphInput["resumeData"] = message
        else:
            graphInput["resumeData"] = {"response": message, "action": "confirm"}

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

        # Rotation signal from POST auto_reset. The signal carries the new
        # threadId in-band so the stream can rebind without reading
        # request.session (which is frozen at SSE connection time). Do NOT
        # yield an SSE event. Source: 13-DEBUG-sse-session-stale.md.
        if isinstance(graphInput, QueueRotationSignal):
            oldThreadId = threadId
            threadId = graphInput.newThreadId
            queue = getOrCreateQueue(threadId)
            logEvent(
                logger,
                "sse.stream_rebind_in_band",
                logCategory="sse",
                oldThreadId=oldThreadId,
                newThreadId=threadId,
                message="streamChat rebound via in-band rotation signal",
            )
            continue

        # Use graphInput as the authoritative source of the turn's identity.
        # sessionIds was captured at stream start and is stale after any
        # auto_reset rotation. The POST handler always writes the current
        # threadId/claimId into graphInput.
        turnClaimId = graphInput.get("claimId")
        activeIntakeAgent = (
            "intake-gpt" if getSettings().intake_agent_mode.lower() == "gpt" else "intake"
        )
        logEvent(
            logger,
            "agent.turn_queued",
            logCategory="agent",
            actorType="app",
            employeeId=request.session.get("employee_id"),
            username=request.session.get("username"),
            agent=activeIntakeAgent,
            claimId=turnClaimId,
            draftClaimNumber=f"DRAFT-{turnClaimId[:8]}" if turnClaimId else None,
            threadId=graphInput.get("threadId"),
            status="queued",
            payload={"graphInput": graphInput},
            message="Agent turn queued",
        )

        try:
            employeeIdVar.set(request.session.get("employee_id"))
            imagePathVar.set(getImagePath(turnClaimId))

            async for sseEvent in runGraph(graph, graphInput, request, templates):
                yield sseEvent

            logEvent(
                logger,
                "agent.turn_stream_completed",
                logCategory="agent",
                actorType="app",
                employeeId=request.session.get("employee_id"),
                username=request.session.get("username"),
                agent=activeIntakeAgent,
                claimId=turnClaimId,
                draftClaimNumber=f"DRAFT-{turnClaimId[:8]}" if turnClaimId else None,
                threadId=graphInput.get("threadId"),
                status="completed",
                message="Agent turn stream completed",
            )
        except Exception as e:
            logEvent(
                logger,
                "sse.stream_error",
                level=logging.ERROR,
                logCategory="sse",
                claimId=turnClaimId,
                error=str(e),
                message="SSE stream error",
            )
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
            logEvent(
                logger,
                "sse.background_task_launched",
                logCategory="sse",
                actorType="app",
                claimId=backgroundTask["claimId"],
                threadId=backgroundTask["threadId"],
                message="Background post-submission task launched",
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
    oldDraftClaimId = request.session.get("draft_claim_id")

    if oldClaimId:
        clearImage(oldClaimId)
    if oldThreadId:
        removeQueue(oldThreadId)

    # Preserve the just-closed conversation pointers so the user can still
    # export it after a manual reset (e.g. after escalation + "New Claim").
    request.session["last_closed_thread_id"] = oldThreadId
    request.session["last_closed_claim_id"] = oldClaimId
    request.session["last_closed_draft_claim_id"] = oldDraftClaimId

    request.session["thread_id"] = str(uuid.uuid4())
    request.session["claim_id"] = str(uuid.uuid4())
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


@router.get("/chat/export")
async def exportChat(request: Request, scope: str = "auto"):
    """Export a conversation as a markdown file download.

    Scope selection:
      - scope="current" (explicit): always read the current session thread
      - scope="last-closed" (explicit): read last_closed_thread_id from session
      - scope="auto" (default): prefer current if it has turns; otherwise
        fall back to last-closed. Matches the "just submitted/escalated,
        export this claim" UX after session auto-reset.

    The LangGraph checkpointer persists by thread_id, so prior threads
    remain readable even after session rotation (chat.auto_reset).
    """
    from datetime import datetime, timezone

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    sessionIds = getSessionIds(request)
    currentThreadId = sessionIds["threadId"]
    currentClaimId = sessionIds["claimId"]
    lastClosedThreadId = request.session.get("last_closed_thread_id")
    lastClosedClaimId = request.session.get("last_closed_claim_id")

    graph = request.app.state.graph

    async def _readMessages(tid: str | None):
        if not tid:
            return None
        try:
            snap = await graph.aget_state({"configurable": {"thread_id": tid}})
        except Exception as e:  # noqa: BLE001
            logEvent(
                logger,
                "chat.export_failed",
                level=logging.WARNING,
                logCategory="chat_history",
                threadId=tid,
                error=str(e)[:200],
                message="Chat export failed: aget_state error",
            )
            return None
        return (snap.values or {}).get("messages", []) if snap else []

    if scope == "last-closed":
        threadId, claimId = lastClosedThreadId, lastClosedClaimId
        messages = await _readMessages(threadId)
    elif scope == "current":
        threadId, claimId = currentThreadId, currentClaimId
        messages = await _readMessages(threadId)
    else:
        # auto: try current first; fall back to last-closed if current is empty
        threadId, claimId = currentThreadId, currentClaimId
        messages = await _readMessages(threadId)
        currentIsEmpty = not any(
            isinstance(m, (HumanMessage, AIMessage)) and (getattr(m, "content", "") or getattr(m, "tool_calls", None))
            for m in (messages or [])
        )
        if currentIsEmpty and lastClosedThreadId:
            threadId, claimId = lastClosedThreadId, lastClosedClaimId
            messages = await _readMessages(threadId)

    if messages is None:
        return Response(status_code=500, content="Failed to read conversation state")

    exportedAt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Expense Claim Conversation",
        "",
        f"- **Exported:** {exportedAt}",
        f"- **Claim ID:** `{claimId}`",
        f"- **Thread ID:** `{threadId}`",
        "",
        "---",
        "",
    ]

    turnCount = 0
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(msg, HumanMessage):
            turnCount += 1
            text = content if isinstance(content, str) else str(content or "")
            lines.append("## User")
            lines.append("")
            lines.append(text.strip() or "_(empty)_")
            lines.append("")
        elif isinstance(msg, AIMessage):
            text = content if isinstance(content, str) else ""
            toolCalls = getattr(msg, "tool_calls", None) or []
            # Surface askHuman questions as assistant prose (the user sees them
            # as chat messages, not as tool-call metadata). Other tool calls
            # render in a compact "Tool calls:" block for auditability.
            askHumanQuestions: list[str] = []
            otherCalls: list[dict] = []
            for call in toolCalls:
                if isinstance(call, dict) and call.get("name") == "askHuman":
                    question = (call.get("args") or {}).get("question", "")
                    if question:
                        askHumanQuestions.append(str(question).strip())
                elif isinstance(call, dict):
                    otherCalls.append(call)
            if not text.strip() and not toolCalls:
                continue
            turnCount += 1
            lines.append("## Assistant")
            lines.append("")
            if text.strip():
                lines.append(text.strip())
                lines.append("")
            for q in askHumanQuestions:
                lines.append(q)
                lines.append("")
            if otherCalls:
                lines.append("**Tool calls:**")
                lines.append("")
                for call in otherCalls:
                    name = call.get("name", "?")
                    args = call.get("args", {})
                    lines.append(f"- `{name}` — `{args}`")
                lines.append("")
        elif isinstance(msg, ToolMessage):
            # Surface askHuman answers as user turns — they carry the user's
            # reply to an interrupt-triggered question. Dropping them loses the
            # majority of user content in the typical flow (only 1-2 messages
            # arrive as HumanMessage; everything else is an askHuman resume).
            # Source: CLAIM-022 export showed only the initial greeting + upload.
            if getattr(msg, "name", None) != "askHuman":
                continue
            text = content if isinstance(content, str) else str(content or "")
            if not text.strip():
                continue
            turnCount += 1
            lines.append("## User")
            lines.append("")
            lines.append(text.strip())
            lines.append("")

    if turnCount == 0:
        lines.append("_(No conversation yet.)_")
        lines.append("")

    markdown = "\n".join(lines)
    filename = f"claim-{claimId[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"

    logEvent(
        logger,
        "chat.exported",
        logCategory="chat_history",
        actorType="user",
        claimId=claimId,
        threadId=threadId,
        turnCount=turnCount,
        bytes=len(markdown.encode("utf-8")),
        message="Chat exported to markdown",
    )

    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        query += "WHERE LOWER(COALESCE(c.status, '')) != 'draft' "
        if employeeId:
            query += f"AND c.employee_id = $${employeeId}$$ "
        query += "ORDER BY c.created_at DESC LIMIT 50"

        result = await mcpCallTool(
            serverUrl=settings.db_mcp_url,
            toolName="executeQuery",
            arguments={"query": query},
        )
        if isinstance(result, list):
            filteredRows = [
                row
                for row in result
                if str(row.get("status", "") or "").strip().lower() != "draft"
            ]

            for row in filteredRows:
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

            return filteredRows
        if isinstance(result, dict) and "error" in result:
            logEvent(
                logger,
                "chat.fetch_claims_db_error",
                level=logging.WARNING,
                logCategory="chat",
                error=result["error"],
                message="fetchClaimsForTable DB error",
            )
            return []
        return []
    except Exception as e:
        logEvent(
            logger,
            "chat.fetch_claims_error",
            level=logging.WARNING,
            logCategory="chat",
            error=str(e),
            message="fetchClaimsForTable failed",
        )
        return []
