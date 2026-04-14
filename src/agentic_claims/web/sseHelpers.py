"""Ported streaming helpers from app.py + runGraph SSE generator.

All helper functions (_stripToolCallJson, _stripThinkingTags, _formatElapsed,
_summarizeToolOutput, TOOL_LABELS) are ported verbatim from the Chainlit app.py.
runGraph translates LangGraph astream_events into SSE events.
"""

import json
import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.sse import ServerSentEvent
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from agentic_claims.agents.intake.auditLogger import flushSteps, logIntakeStep
from agentic_claims.agents.intake.extractionContext import sessionClaimIdVar
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
from agentic_claims.web.employeeIdContext import employeeIdVar
from agentic_claims.web.sseEvents import SseEvent

logger = logging.getLogger(__name__)


async def fetchClaimsForTable(employeeId: str | None = None) -> list[dict]:
    """Thin wrapper so tests can patch agentic_claims.web.sseHelpers.fetchClaimsForTable."""
    from agentic_claims.web.routers.chat import fetchClaimsForTable as _fetchClaimsForTable

    return await _fetchClaimsForTable(employeeId=employeeId)


TOOL_LABELS = {
    "getClaimSchema": "Loading claim schema...",
    "extractReceiptFields": "Extracting receipt fields...",
    "searchPolicies": "Checking policies...",
    "convertCurrency": "Converting currency...",
    "submitClaim": "Submitting claim...",
    "askHuman": "Waiting for your input...",
    "requestHumanInput": "Waiting for your input...",
}

# Plan 13-16 fix: completion-phase labels. Used as the fallback for
# _summarizeToolOutput so no raw internal tool name reaches the DOM, and as
# a defensive map for any future tool added without a dedicated branch.
# Convention: when a new tool is added to TOOL_LABELS, add a matching entry
# here. Source: 13-DEBUG-tool-name-leak.md sections 3 + 5.
TOOL_COMPLETION_LABELS = {
    "getClaimSchema": "Claim schema loaded",
    "extractReceiptFields": "Receipt read",
    "searchPolicies": "Policy check complete",
    "convertCurrency": "Currency converted",
    "submitClaim": "Claim submitted",
    # Kept for defensive fallback; runGraph filters askHuman from emission
    # entirely, so this string should never actually reach the DOM.
    "askHuman": "Asked for clarification",
    "requestHumanInput": "Asked for clarification",
}


# BUG-013 guard pattern. Matches actual success phrasing only, so a refusal
# that echoes a CLAIM-XXX number (e.g. "I can't retrieve CLAIM-010") does not
# falsely trip the hallucinated-submit guard. Source: user-reported 2026-04-13
# false positive on "can you load my previous claim CLAIM-010".
_SUBMISSION_SUCCESS_PATTERN = re.compile(
    r"(?:claim\s+CLAIM-\d+\s+(?:has been|is|was)\s+submitted"
    r"|CLAIM-\d+\s+submitted\s+successfully"
    r"|submitted\s+successfully"
    r"|submission\s+(?:complete|successful))",
    re.IGNORECASE,
)


_TOOL_NAMES_FOR_CALL_STRIP = (
    "askHuman",
    "submitClaim",
    "searchPolicies",
    "convertCurrency",
    "extractReceiptFields",
    "getClaimSchema",
    "requestHumanInput",
)


def _stripToolCallExpressions(text: str) -> str:
    """Remove python-style tool-call expressions (`askHuman("...")`) from prose.

    qwen3 frequently narrates its next tool call by also emitting the call
    syntax as plain text, e.g.:

        Analysis Complete
        | ...table... |

        askHuman("Do the details above look correct?")

    The structured tool_call goes through LangGraph correctly, but the prose
    copy leaks into the user bubble. This stripper finds each known tool
    name followed by `(` and removes up to the matching `)` with a simple
    depth counter (handles nested parens and quoted parens inside strings).

    Source: CLAIM-020 screenshot — "askHuman(...)" leak in two bubbles.
    """
    if not text:
        return text
    for toolName in _TOOL_NAMES_FOR_CALL_STRIP:
        while True:
            idx = text.find(toolName + "(")
            if idx == -1:
                break
            start = idx
            depth = 0
            inString = False
            stringChar = ""
            end = -1
            scan = idx + len(toolName)
            while scan < len(text):
                ch = text[scan]
                if inString:
                    if ch == "\\" and scan + 1 < len(text):
                        scan += 2
                        continue
                    if ch == stringChar:
                        inString = False
                elif ch in ("'", '"'):
                    inString = True
                    stringChar = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = scan
                        break
                scan += 1
            if end == -1:
                break
            text = (text[:start] + text[end + 1:]).replace("  ", " ")
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln or True).strip()


def _stripToolCallJson(text: str) -> str:
    """Strip raw tool call JSON / leading JSON-root dumps from text content.

    Three strip paths, evaluated in order:

    0. Leading fenced JSON block (````json ... ````) emitted by qwen-style
       models while a tool call is pending. Consume the fenced block and keep
       any trailing prose.
    1. Leading JSON object/array dump (qwen3 frequently leaks the raw tool
       result as the opening of its content, followed by the analysis prose
       — e.g. `{"fields": {...}, "confidence": {...}}\\n\\nAnalysis Complete...`).
       Uses `json.JSONDecoder.raw_decode` to consume exactly the JSON prefix
       and keep the trailing prose.
    2. Trailing `{"name": ...}` tool-call specifications (QwQ-32B style —
       kept for back-compat with older reasoning models).
    """
    stripped = text.lstrip()
    fencedMatch = re.match(r"^```(?:json)?\s*\n([\s\S]*?)\n```", stripped)
    if fencedMatch:
        remaining = stripped[fencedMatch.end() :].lstrip()
        if remaining:
            return remaining
        fencedBody = fencedMatch.group(1).strip()
        if _looksLikeStructuredPayloadLeak(fencedBody):
            return ""

    stripped = text.lstrip()
    if stripped and stripped[0] in "{[":
        try:
            decoder = json.JSONDecoder()
            _, endIdx = decoder.raw_decode(stripped)
            remaining = stripped[endIdx:].lstrip()
            if remaining:
                return remaining
            return ""
        except (ValueError, TypeError):
            pass

    idx = text.find('{"name":')
    if idx == -1:
        idx = text.find('{"name" :')
    if idx > 0:
        return text[:idx].strip()
    return text


def _stripThinkingTags(text: str) -> str:
    """Strip XML-style thinking/reasoning/tools wrappers from model output.

    Models like QwQ-32B sometimes emit <Thinking>...</Thinking>,
    <think>...</think>, or <tools>...</tools> tags in their text content.
    The UI handles reasoning display via the thinking panel, and tool calls
    are handled by LangGraph, so these leak through as unwanted visible text.
    """
    cleaned = re.sub(
        r"<(?:Thinking|thinking|think|Think|reasoning|Reasoning|tools|Tools)>.*?</(?:Thinking|thinking|think|Think|reasoning|Reasoning|tools|Tools)>",
        "",
        text,
        flags=re.DOTALL,
    )
    return cleaned.strip()


def _looksLikeJsonRoot(text: str) -> bool:
    """Return True if text appears to be a raw JSON object or array payload.

    Guards the mid-stream bubble emission against leaking tool-call payloads
    that were not wrapped in a ```json fence (qwen3 frequently emits bare
    JSON while `pendingToolCalls > 0`). We parse defensively — only reject
    when the body parses cleanly as JSON, so a sentence that happens to
    contain '{' or '[' mid-line is not suppressed.

    Source: 13-DEBUG-raw-json-bubble.md (screenshot #7, CLAIM-018).
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(stripped)
    except (ValueError, TypeError):
        return False
    return True


def _looksLikeStructuredPayloadLeak(text: str) -> bool:
    """Return True if text resembles a leaked structured payload.

    This covers two cases:
    - valid JSON roots (`_looksLikeJsonRoot`)
    - pretty-printed object-like dumps that start with `{`/`[` but are not
      strictly valid JSON after markdown rendering or model mutation
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    if _looksLikeJsonRoot(stripped):
        return True
    keyValueHits = len(re.findall(r'"\w[\w\s]*"\s*:', stripped))
    lineCount = stripped.count("\n") + 1
    return keyValueHits >= 2 and lineCount >= 3


def _isUserFacingProse(text: str) -> bool:
    """Decide whether cleaned content should render as a chat bubble vs thinking entry.

    Gate: length >= 40 chars OR contains markdown structure markers (table pipes,
    headings, bullets, multi-line content). Short acknowledgements ("Ok.", "Sure.")
    fall through to the reasoning panel (existing behaviour preserved).

    Bug 1 fix (2026-04-13): reject content that parses as a JSON root object
    or array. `_stripToolCallJson` only strips ```json fences; bare JSON from
    qwen3 passes through and historically rendered as a raw dict in the main
    chat. The JSON-root check kills that failure class before bubble emission.
    """
    if not text:
        return False
    stripped = text.strip()
    if _looksLikeStructuredPayloadLeak(stripped):
        return False
    if len(stripped) >= 40:
        return True
    # Markdown structure heuristics: table row, heading, bullet, multi-line
    if "|" in stripped or stripped.startswith(("# ", "## ", "### ", "- ", "* ")):
        return True
    if "\n" in stripped:
        return True
    return False


def _formatElapsed(elapsed: float) -> str:
    """Format elapsed seconds into a human-readable duration string."""
    if elapsed >= 60:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes}m {seconds}s"
    seconds = int(elapsed)
    if seconds < 1:
        return "<1s"
    return f"{seconds}s"


def _summarizeToolOutput(toolName: str, toolOutput) -> str:
    """Create a human-readable summary of a tool's output for the Thinking panel."""
    try:
        if isinstance(toolOutput, str):
            data = json.loads(toolOutput)
        elif hasattr(toolOutput, "content"):
            data = (
                json.loads(toolOutput.content)
                if isinstance(toolOutput.content, str)
                else toolOutput.content
            )
        else:
            data = toolOutput

        if not isinstance(data, dict):
            return TOOL_COMPLETION_LABELS.get(toolName, "Step complete")

        if "error" in data:
            return f"Error: {data['error']}"

        if toolName == "getClaimSchema":
            claims = data.get("claims", [])
            receipts = data.get("receipts", [])
            return f"Schema loaded: {len(claims)} claim fields, {len(receipts)} receipt fields"

        if toolName == "extractReceiptFields":
            fields = data.get("fields", {})
            merchant = fields.get("merchant", "unknown")
            total = fields.get("totalAmount", "unknown")
            currency = fields.get("currency", "")
            return f"Extracted receipt: {merchant}, {currency} {total}"

        if toolName == "searchPolicies":
            results = data.get("results", data.get("policies", []))
            if isinstance(results, list):
                return f"Found {len(results)} relevant policy clause(s)"
            return "Policy search completed"

        if toolName == "convertCurrency":
            fromAmount = data.get("fromAmount", data.get("originalAmount", "?"))
            fromCurrency = data.get("fromCurrency", data.get("originalCurrency", "?"))
            amountSgd = data.get("amountSgd", data.get("convertedAmount", "?"))
            rate = data.get("rate", data.get("exchangeRate", "?"))
            return f"Converted {fromCurrency} {fromAmount} → SGD {amountSgd} (rate: {rate})"

        if toolName == "submitClaim":
            if "error" in data:
                return f"Submission error: {data['error']}"
            claimId = data.get("claim", {}).get("id", "")
            return f"Claim submitted successfully (ID: {claimId})"

        return TOOL_COMPLETION_LABELS.get(toolName, "Step complete")

    except Exception:
        return TOOL_COMPLETION_LABELS.get(toolName, "Step complete")


def _isFieldConfirmationToolCall(toolCalls) -> bool:
    """Return True when a tool-call list contains requestHumanInput(field_confirmation)."""
    if not toolCalls:
        return False
    for toolCall in toolCalls:
        if not isinstance(toolCall, dict):
            continue
        if toolCall.get("name") != "requestHumanInput":
            continue
        args = toolCall.get("args") or {}
        if isinstance(args, dict) and str(args.get("kind") or "") == "field_confirmation":
            return True
    return False


TOOL_TO_STEP = {
    "extractReceiptFields": 1,
    "searchPolicies": 2,
    "submitClaim": 3,
}

POST_SUBMISSION_GRAPH_NODES = {
    "postSubmission",
    "compliance",
    "fraud",
    "advisor",
    "markAiReviewed",
}

GRAPH_NODE_AGENT_MAP = {
    "compliance": "compliance",
    "fraud": "fraud",
    "advisor": "advisor",
}

PATHWAY_WAITING_TEXT = {
    0: "",
    1: "Awaiting receipt upload...",
    2: "Awaiting extraction data...",
    3: "Awaiting policy check...",
}


def _nowTimestamp() -> str:
    sgt = ZoneInfo("Asia/Singapore")
    return datetime.now(sgt).strftime("%I:%M:%S %p")


def _agentFromGraphNode(nodeName: str | None, defaultAgent: str) -> str:
    """Map a graph node name to the owning agent for logging purposes."""
    if not nodeName:
        return defaultAgent
    return GRAPH_NODE_AGENT_MAP.get(str(nodeName), defaultAgent)


def _inferLlmLogAgent(metadata: dict | None, currentNodeName: str | None, defaultAgent: str) -> str:
    """Infer which agent owns an LLM event.

    `runGraph` observes a single outer LangGraph stream that includes intake,
    compliance, fraud, and advisor events. The intake-mode default is only
    correct for intake turns; post-submission LLM calls must be labeled with
    their actual node owner.
    """
    if isinstance(metadata, dict):
        for key in ("langgraph_node", "graph_node", "node_name"):
            agent = _agentFromGraphNode(metadata.get(key), defaultAgent)
            if agent != defaultAgent:
                return agent
    return _agentFromGraphNode(currentNodeName, defaultAgent)


def _buildPathwaySteps(
    completedTools: set,
    activeTools: set,
    hasImage: bool,
    toolTimestamps: dict,
    extractionDetails: dict | None = None,
) -> list:
    """Build the 4 Decision Pathway steps from current tool state."""
    completedTools = set(completedTools)
    activeTools = set(activeTools)
    if "submitClaim" in completedTools:
        completedTools.update({"extractReceiptFields", "searchPolicies"})
    elif "searchPolicies" in completedTools:
        completedTools.add("extractReceiptFields")

    downstreamEvidence = {"extractReceiptFields", "searchPolicies", "submitClaim"}
    hasReceiptEvidence = hasImage or bool(
        completedTools.intersection(downstreamEvidence)
        or activeTools.intersection(downstreamEvidence)
    )

    steps = [
        {
            "name": "Receipt Uploaded",
            "icon": "cloud_upload",
            "status": "pending",
            "timestamp": None,
            "details": None,
            "description": None,
            "waitingText": "",
        },
        {
            "name": "AI Extraction",
            "icon": "troubleshoot",
            "status": "pending",
            "timestamp": None,
            "details": None,
            "description": None,
            "waitingText": PATHWAY_WAITING_TEXT[1],
        },
        {
            "name": "Policy Check",
            "icon": "rule",
            "status": "pending",
            "timestamp": None,
            "details": None,
            "description": None,
            "waitingText": PATHWAY_WAITING_TEXT[2],
        },
        {
            "name": "Claim Submission",
            "icon": "send",
            "status": "pending",
            "timestamp": None,
            "details": None,
            "description": None,
            "waitingText": PATHWAY_WAITING_TEXT[3],
        },
    ]

    # Step 0: Receipt Uploaded
    if hasReceiptEvidence:
        steps[0]["status"] = "completed"
        steps[0]["timestamp"] = toolTimestamps.get("receiptUploaded", _nowTimestamp())

    # Steps 1-3: tool-driven
    for toolName, stepIdx in TOOL_TO_STEP.items():
        if toolName in completedTools:
            steps[stepIdx]["status"] = "completed"
            steps[stepIdx]["timestamp"] = toolTimestamps.get(toolName)
            if toolName == "extractReceiptFields" and extractionDetails:
                steps[stepIdx]["details"] = extractionDetails
            if toolName == "submitClaim":
                steps[stepIdx]["description"] = "Claim submitted successfully"
        elif toolName in activeTools:
            steps[stepIdx]["status"] = "in_progress"
            steps[stepIdx]["timestamp"] = toolTimestamps.get(toolName)

    return steps


def _extractExtractionDetails(toolOutput) -> dict | None:
    """Parse extractReceiptFields output into pathway display details."""
    try:
        if isinstance(toolOutput, str):
            data = json.loads(toolOutput)
        elif hasattr(toolOutput, "content"):
            data = (
                json.loads(toolOutput.content)
                if isinstance(toolOutput.content, str)
                else toolOutput.content
            )
        else:
            data = toolOutput

        if not isinstance(data, dict):
            return None

        fields = data.get("fields", {})
        confidence = data.get("confidence", data.get("confidenceScores", {}))

        if isinstance(confidence, dict) and confidence:
            scores = [float(v) for v in confidence.values() if isinstance(v, (int, float))]
            avgConfidence = round(
                (sum(scores) / len(scores)) * 100
                if scores and all(s <= 1 for s in scores)
                else sum(scores) / len(scores)
                if scores
                else 0,
                1,
            )
        elif isinstance(confidence, (int, float)):
            avgConfidence = round(confidence * 100 if confidence <= 1 else confidence, 1)
        else:
            avgConfidence = 0

        currency = fields.get("currency", "")
        totalAmount = fields.get("totalAmount", "")
        amountStr = f"{currency} {totalAmount}" if currency else str(totalAmount)

        return {
            "confidence": avgConfidence,
            "merchant": fields.get("merchant", "Unknown"),
            "amount": amountStr,
            "date": fields.get("date", "Unknown"),
        }
    except Exception:
        return None


def _decodeToolOutput(toolOutput):
    """Decode LangChain tool output into a Python value when possible."""
    if isinstance(toolOutput, str):
        try:
            return json.loads(toolOutput)
        except (json.JSONDecodeError, TypeError):
            return toolOutput
    if hasattr(toolOutput, "content"):
        content = toolOutput.content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return content
        return content
    return toolOutput


def _toolOutputError(toolOutput) -> str | None:
    """Return a tool error string from dict/string outputs, if present."""
    decoded = _decodeToolOutput(toolOutput)
    if isinstance(decoded, dict) and decoded.get("error"):
        return str(decoded["error"])
    if isinstance(decoded, str) and "error" in decoded.lower():
        return decoded
    return None


def _extractSubmitClaimIdentifiers(toolOutput) -> tuple[int | None, str | None]:
    """Extract (dbClaimId, claimNumber) from a submitClaim tool result.

    LangGraph may surface tool outputs either as raw JSON strings or as
    ToolMessage-like objects with a `.content` field. The early-termination
    acknowledgement path must decode both forms reliably.
    """
    decoded = _decodeToolOutput(toolOutput)
    if not isinstance(decoded, dict):
        return None, None
    claim = decoded.get("claim") or {}
    if not isinstance(claim, dict):
        return None, None
    dbClaimId = claim.get("id")
    claimNumber = claim.get("claim_number") or claim.get("claimNumber")
    try:
        parsedDbClaimId = int(dbClaimId) if dbClaimId is not None else None
    except (TypeError, ValueError):
        parsedDbClaimId = None
    return parsedDbClaimId, str(claimNumber) if claimNumber else None


def _stateHasToolResult(stateValues: dict, toolName: str) -> bool:
    """Return true when prior graph messages include a completed tool result."""
    for msg in stateValues.get("messages", []):
        if getattr(msg, "name", None) == toolName:
            return True
    return False


async def _getFallbackMessage(graph, config: dict) -> str:
    """Extract last AI message from graph state as fallback when token buffer is empty."""
    try:
        finalState = await graph.aget_state(config=config)
        messages = finalState.values.get("messages", [])
        for msg in reversed(messages):
            if (
                hasattr(msg, "type")
                and msg.type == "ai"
                and hasattr(msg, "content")
                and msg.content
            ):
                return _stripToolCallExpressions(
                    _stripThinkingTags(_stripToolCallJson(str(msg.content)))
                )
    except Exception as e:
        logEvent(
            logger,
            "sse.fallback_message_error",
            level=logging.ERROR,
            logCategory="sse",
            error=str(e),
            message="Error in fallback message extraction",
        )
    return ""


def _calcProgressPct(
    thinkingEntries: list,
    graphState: dict | None,
    *,
    askHumanFired: bool = False,
) -> int:
    """Calculate progress from tool milestones.
    extractReceiptFields completed -> 33%
    searchPolicies completed -> 50%
    User confirmed (ready for submission) -> 66%
    submitClaim completed -> 100%

    Plan 13-16: askHumanFired is the runGraph-supplied substitute for the
    former `"askHuman" in completedTools` check, since askHuman is now
    filtered from thinkingEntries. The legacy check is retained for callers
    that still inject askHuman entries directly (e.g. unit tests).
    """
    completedTools = set()
    for e in thinkingEntries:
        if e.get("type") == "tool" and e.get("name"):
            completedTools.add(e["name"])

    if graphState:
        if graphState.get("extractedReceipt"):
            completedTools.add("extractReceiptFields")
        if graphState.get("currencyConversion"):
            completedTools.add("convertCurrency")
        if graphState.get("claimSubmitted"):
            completedTools.add("submitClaim")

    if "submitClaim" in completedTools:
        return 100
    if (
        askHumanFired
        or "askHuman" in completedTools
        or "convertCurrency" in completedTools
    ):
        return 66
    if "searchPolicies" in completedTools:
        return 50
    if "extractReceiptFields" in completedTools:
        return 33
    return 0


def _extractSummaryData(
    thinkingEntries: list,
    graphState: dict | None = None,
    claimId: str = "",
    *,
    askHumanFired: bool = False,
) -> dict | None:
    """Extract summary panel data from tool outputs and graph state.

    Uses thinkingEntries (current turn's tool outputs) first, then falls
    back to graphState for data from prior turns (e.g. extractedReceipt
    from turn 1 when turn 2 only does submission).
    """
    totalAmount = ""
    merchant = ""
    category = ""
    currency = ""
    warningCount = 0
    submitted = False
    convertedAmount = ""
    extractedClaimNumber = ""

    submitCallInEntries = any(
        e.get("name") == "submitClaim" and e.get("type") == "tool" for e in thinkingEntries
    )

    hasReceiptData = False

    for entry in thinkingEntries:
        if entry["type"] != "tool":
            continue

        toolName = entry.get("name", "")
        toolOutput = entry.get("output", "")

        try:
            if isinstance(toolOutput, str):
                data = json.loads(toolOutput)
            elif hasattr(toolOutput, "content"):
                data = (
                    json.loads(toolOutput.content)
                    if isinstance(toolOutput.content, str)
                    else toolOutput.content
                )
            else:
                data = toolOutput

            if not isinstance(data, dict):
                continue

            if toolName == "extractReceiptFields":
                fields = data.get("fields", {})
                merchant = fields.get("merchant", "")
                totalAmount = fields.get("totalAmount", "")
                currency = fields.get("currency", "SGD")
                category = fields.get("category", "")
                hasReceiptData = True

            elif toolName == "searchPolicies":
                results = data.get("results", data.get("policies", []))
                if isinstance(results, list):
                    warningCount = len(results)

            elif toolName == "convertCurrency":
                convertedAmount = str(data.get("convertedAmount", data.get("amountSgd", "")))

            elif toolName == "submitClaim":
                if "error" not in data:
                    submitted = True
                    claimData = data.get("claim", {})
                    extractedClaimNumber = claimData.get("claim_number", "")

        except Exception:
            continue

    # Fall back to graph state for receipt data from prior turns
    if not hasReceiptData and graphState:
        extractedReceipt = graphState.get("extractedReceipt")
        if isinstance(extractedReceipt, dict):
            fields = extractedReceipt.get("fields", extractedReceipt)
            merchant = fields.get("merchant", "")
            totalAmount = fields.get("totalAmount", "")
            currency = fields.get("currency", "SGD")
            category = fields.get("category", "")
            hasReceiptData = bool(merchant or totalAmount)

        conversionData = graphState.get("currencyConversion")
        if isinstance(conversionData, dict) and not convertedAmount:
            convertedAmount = str(
                conversionData.get("convertedAmount", conversionData.get("amountSgd", ""))
            )

    # Check graphState claimSubmitted regardless of hasReceiptData
    # (prior turn may have submitted while current turn has new receipt data)
    if graphState and graphState.get("claimSubmitted"):
        submitted = True

    if not extractedClaimNumber and graphState:
        extractedClaimNumber = graphState.get("claimNumber", "") or ""

    # BUG-013: If graphState says submitted but no submitClaim tool call
    # exists in THIS turn's thinkingEntries, trust the graphState (prior turn
    # did submit). But if submitted was set from thinkingEntries parsing and
    # there's no actual submitClaim entry, suppress it (hallucination).
    if submitted and not submitCallInEntries and not graphState.get("claimSubmitted"):
        logEvent(
            logger,
            "sse.hallucinated_submit_suppressed",
            level=logging.WARNING,
            logCategory="sse",
            message="BUG-013: _extractSummaryData suppressing submitted=True; no submitClaim in thinkingEntries and graphState not submitted",
        )
        submitted = False
        extractedClaimNumber = ""

    if not hasReceiptData:
        return None

    displayAmount = f"SGD {convertedAmount}" if convertedAmount else f"{currency} {totalAmount}"

    progressPct = _calcProgressPct(
        thinkingEntries, graphState, askHumanFired=askHumanFired
    )

    return {
        "totalAmount": displayAmount,
        "itemCount": 1,
        "topCategory": category or "--",
        "warningCount": warningCount,
        "progressPct": progressPct,
        "claimNumber": extractedClaimNumber or "",
        "submitted": submitted,
        "claimId": claimId,
        "batchItems": [
            {
                "merchant": merchant or "Unknown",
                "amount": displayAmount,
                "category": category or "uncategorized",
            }
        ],
    }


def _extractConfidenceScores(thinkingEntries: list) -> dict | None:
    """Extract per-field confidence scores from extractReceiptFields output."""
    for entry in thinkingEntries:
        if entry.get("type") != "tool" or entry.get("name") != "extractReceiptFields":
            continue
        try:
            toolOutput = entry.get("output", "")
            if isinstance(toolOutput, str):
                data = json.loads(toolOutput)
            elif hasattr(toolOutput, "content"):
                data = (
                    json.loads(toolOutput.content)
                    if isinstance(toolOutput.content, str)
                    else toolOutput.content
                )
            else:
                data = toolOutput
            if isinstance(data, dict):
                confidence = data.get("confidence", data.get("confidenceScores"))
                if isinstance(confidence, dict):
                    return {
                        k: int(float(v) * 100) if isinstance(v, float) and v <= 1 else int(v)
                        for k, v in confidence.items()
                    }
        except Exception:
            continue
    return None


def _extractViolations(thinkingEntries: list) -> list | None:
    """Extract policy violation citations from searchPolicies output."""
    violations = []
    for entry in thinkingEntries:
        if entry.get("type") != "tool" or entry.get("name") != "searchPolicies":
            continue
        try:
            toolOutput = entry.get("output", "")
            if isinstance(toolOutput, str):
                data = json.loads(toolOutput)
            elif hasattr(toolOutput, "content"):
                data = (
                    json.loads(toolOutput.content)
                    if isinstance(toolOutput.content, str)
                    else toolOutput.content
                )
            else:
                data = toolOutput
            if isinstance(data, dict):
                results = data.get("violations", data.get("results", []))
                if isinstance(results, list):
                    for r in results:
                        if isinstance(r, dict):
                            text = r.get("text", r.get("clause", r.get("violation", "")))
                            if text:
                                violations.append(str(text))
                        elif isinstance(r, str):
                            violations.append(r)
        except Exception:
            continue
    return violations if violations else None


def _buildGraphInput(graphInput: dict) -> dict:
    """Build LangGraph input from the queue payload."""
    claimId = graphInput["claimId"]
    message = graphInput.get("message", "")
    hasImage = graphInput.get("hasImage", False)

    if hasImage:
        userText = message.strip()
        if userText:
            humanMsg = HumanMessage(
                content=f'User says: "{userText}"\n\n'
                f"I've also uploaded a receipt image for claim {claimId}. "
                "Please process it using extractReceiptFields."
            )
        else:
            humanMsg = HumanMessage(
                content=f"I've uploaded a receipt image for claim {claimId}. "
                "Please process it using extractReceiptFields. "
                "No expense description was provided."
            )
    else:
        humanMsg = HumanMessage(content=message)

    return {
        "claimId": claimId,
        "status": "draft",
        "messages": [humanMsg],
    }


async def runPostSubmissionAgents(graph, threadId: str, claimId: str):
    """Run compliance, fraud, and advisor agents in the background.

    Resumes the graph from its last checkpoint (after intake node with
    claimSubmitted=True). The evaluatorGate routes to postSubmission ->
    compliance || fraud -> markAiReviewed -> advisor.
    """
    config = {"configurable": {"thread_id": threadId}}
    try:
        currentState = await graph.aget_state(config)
        if not currentState.values.get("claimSubmitted"):
            logEvent(
                logger,
                "sse.post_submission_guard_failed",
                level=logging.ERROR,
                logCategory="sse",
                claimId=claimId,
                message="Checkpoint guard failed: claimSubmitted is not True",
            )
            return

        logEvent(
            logger,
            "sse.post_submission_started",
            logCategory="sse",
            claimId=claimId,
            message="Background post-submission started",
        )
        await graph.ainvoke(None, config=config)
        logEvent(
            logger,
            "sse.post_submission_completed",
            logCategory="sse",
            claimId=claimId,
            message="Background post-submission completed",
        )
    except Exception as e:
        logEvent(
            logger,
            "sse.post_submission_error",
            level=logging.ERROR,
            logCategory="sse",
            claimId=claimId,
            error=str(e),
            message="Background post-submission failed",
        )


async def runGraph(graph, graphInput: dict, request: Request, templates: Jinja2Templates):
    """Translate LangGraph astream_events into SSE events.

    Yields ServerSentEvent instances classifying each astream_events event
    into the SseEvent taxonomy. Checks request.is_disconnected() at each
    iteration to break on client disconnect.
    """
    settings = getSettings()
    activeAgentName = "intake-gpt" if settings.intake_agent_mode.lower() == "gpt" else "intake"
    logEvent(
        logger,
        "agent.turn_started",
        logCategory="agent",
        actorType="agent",
        agent=activeAgentName,
        employeeId=employeeIdVar.get(None),
        claimId=graphInput.get("claimId"),
        draftClaimNumber=f"DRAFT-{graphInput.get('claimId', '')[:8]}",
        threadId=graphInput.get("threadId"),
        status="started",
        payload={"graphInput": graphInput},
        message="Intake agent turn started",
    )
    thinkingEntries = []
    tokenBuffer = ""
    reasoningBuffer = ""
    finalResponse = ""
    pendingToolCalls = 0
    hadAnyToolCall = False
    toolStartTimes = {}
    turnStart = time.time()
    # Plan 13-16: substitute local signal for the removed "askHuman" entry in
    # thinkingEntries/completedTools. Set at on_tool_start, consumed by
    # _calcProgressPct to preserve the 66% progress bump.
    askHumanFired = False
    # BUG-016: once submitClaim completes, post-submission agent LLM events
    # must not overwrite the intake agent's clean submission response.
    claimSubmittedFlag = False
    # BUG-026: after submitClaim, capture the final response then break early
    shouldTerminateEarly = False
    usedFallbackThinkingSummary = False

    # Decision Pathway state
    pathwayActiveTools: set = set()
    pathwayCompletedTools: set = set()
    pathwayToolTimestamps: dict = {}
    pathwayExtractionDetails: dict | None = None
    hasImage = graphInput.get("hasImage", False)

    # Submission table state (in-memory claims accumulated during the turn)
    tableClaims: list[dict] = []

    if hasImage:
        pathwayToolTimestamps["receiptUploaded"] = _nowTimestamp()

    threadId = graphInput["threadId"]
    config = {"configurable": {"thread_id": threadId}}
    currentGraphNodeName: str | None = None

    # Seed pathway from prior state so navigation/resume keeps completed steps
    # monotonic. Current-stream tool events can only advance these states.
    try:
        t0 = time.time()
        priorState = await graph.aget_state(config=config)
        logEvent(
            logger,
            "sse.aget_state_timing",
            logCategory="sse",
            claimId=graphInput.get("claimId"),
            elapsedSeconds=round(time.time() - t0, 2),
            message="aget_state timing",
        )
        if priorState and priorState.values:
            sv = priorState.values

            # Reset pathway when new receipt uploaded after prior submission
            if graphInput.get("hasImage") and sv.get("claimSubmitted"):
                pathwayCompletedTools = set()
                pathwayToolTimestamps = {}
                pathwayToolTimestamps["receiptUploaded"] = _nowTimestamp()
                # Skip seeding from prior state — start fresh for new receipt
            else:
                if sv.get("extractedReceipt"):
                    hasImage = True
                    pathwayCompletedTools.add("extractReceiptFields")
                    pathwayExtractionDetails = _extractExtractionDetails(sv.get("extractedReceipt"))
                    if "receiptUploaded" not in pathwayToolTimestamps:
                        pathwayToolTimestamps["receiptUploaded"] = _nowTimestamp()
                    pathwayToolTimestamps.setdefault("extractReceiptFields", _nowTimestamp())
                if _stateHasToolResult(sv, "searchPolicies"):
                    hasImage = True
                    pathwayCompletedTools.add("searchPolicies")
                    pathwayCompletedTools.add("extractReceiptFields")
                    pathwayToolTimestamps.setdefault("receiptUploaded", _nowTimestamp())
                    pathwayToolTimestamps.setdefault("searchPolicies", _nowTimestamp())
                if sv.get("claimSubmitted") or _stateHasToolResult(sv, "submitClaim"):
                    hasImage = True
                    pathwayCompletedTools.update(
                        {"extractReceiptFields", "searchPolicies", "submitClaim"}
                    )
                    pathwayToolTimestamps.setdefault("receiptUploaded", _nowTimestamp())
                    pathwayToolTimestamps.setdefault("submitClaim", _nowTimestamp())
    except Exception as e:
        logEvent(
            logger,
            "sse.prior_state_check_error",
            level=logging.DEBUG,
            logCategory="sse",
            claimId=graphInput.get("claimId"),
            error=str(e),
            message="Could not check prior state for hasImage",
        )

    yield ServerSentEvent(raw_data="<!-- thinking -->", event=SseEvent.THINKING_START)

    # Initial pathway state
    try:
        initialSteps = _buildPathwaySteps(
            pathwayCompletedTools,
            pathwayActiveTools,
            hasImage,
            pathwayToolTimestamps,
            pathwayExtractionDetails,
        )
        pathwayHtml = templates.get_template("partials/decision_pathway.html").render(
            steps=initialSteps
        )
        yield ServerSentEvent(raw_data=pathwayHtml, event=SseEvent.PATHWAY_UPDATE)
    except Exception as e:
        logEvent(
            logger,
            "sse.pathway_render_error",
            level=logging.ERROR,
            logCategory="sse",
            claimId=graphInput.get("claimId"),
            error=str(e),
            message="Error rendering initial pathway",
        )

    if graphInput.get("isResume"):
        invokeInput = Command(resume=graphInput["resumeData"])
    else:
        invokeInput = _buildGraphInput(graphInput)

    # PROBE D — Command(resume) built (resume-contract debug)
    logEvent(
        logger,
        "debug.invoke_input_built",
        level=logging.DEBUG,
        logCategory="sse",
        claimId=graphInput.get("claimId"),
        threadId=graphInput.get("threadId"),
        isResume=graphInput.get("isResume"),
        invokeInputType=type(invokeInput).__name__,
        resumeData=graphInput.get("resumeData"),
        message="Graph input built for astream_events",
    )

    # BUG-027: set sessionClaimIdVar so submitClaim can flush audit steps even
    # when the LLM doesn't pass sessionClaimId as a tool argument
    sessionClaimIdVar.set(graphInput.get("claimId", None))

    try:
        async for event in graph.astream_events(invokeInput, config=config, version="v2"):
            if await request.is_disconnected():
                break

            eventKind = event.get("event")
            if eventKind != "on_chat_model_stream":
                logger.debug("astream_events event: %s - %s", eventKind, event.get("name", ""))

            if eventKind == "on_chain_start":
                currentGraphNodeName = event.get("name", "")

            if eventKind == "on_chat_model_start":
                try:
                    inputData = event.get("data", {}).get("input", {}) or {}
                    rawMessages = inputData.get("messages", [])
                    # astream_events sometimes nests messages as [[msg, msg, ...]]
                    messages = rawMessages[0] if rawMessages and isinstance(rawMessages[0], list) else rawMessages
                    metadata = event.get("metadata", {}) or {}
                    eventAgentName = _inferLlmLogAgent(
                        metadata, currentGraphNodeName, activeAgentName
                    )
                    serializedMessages = []
                    for m in messages:
                        msgType = type(m).__name__
                        content = getattr(m, "content", "")
                        contentStr = content if isinstance(content, str) else str(content)
                        entry = {"type": msgType, "content": contentStr}
                        toolCalls = getattr(m, "tool_calls", None)
                        if toolCalls:
                            entry["toolCalls"] = [
                                {"name": tc.get("name"), "args": tc.get("args")}
                                for tc in toolCalls
                            ]
                        toolName = getattr(m, "name", None)
                        if toolName:
                            entry["toolName"] = toolName
                        serializedMessages.append(entry)
                    logEvent(
                        logger,
                        "llm.call_started",
                        logCategory="llm",
                        actorType="agent",
                        agent=eventAgentName,
                        claimId=graphInput.get("claimId"),
                        threadId=graphInput.get("threadId"),
                        model=metadata.get("ls_model_name"),
                        messageCount=len(messages),
                        messageTypes=[type(m).__name__ for m in messages],
                        messages=serializedMessages,
                        invocationParams=metadata.get("invocation_params"),
                        message="LLM call started",
                    )
                except Exception as logErr:
                    logger.warning("llm.call_started log failed: %r", logErr, exc_info=True)

            if eventKind == "on_chain_start" and shouldTerminateEarly:
                # BUG-027/029: intakeNode has checkpointed — break before post-submission nodes
                nodeName = event.get("name", "")
                if nodeName in POST_SUBMISSION_GRAPH_NODES:
                    break

            if eventKind == "on_chat_model_stream":
                if pendingToolCalls > 0 or shouldTerminateEarly:
                    continue

                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    tokenBuffer += chunk.content
                    if settings.enable_response_streaming and (
                        not hadAnyToolCall or pendingToolCalls == 0
                    ):
                        yield ServerSentEvent(raw_data=chunk.content, event=SseEvent.TOKEN)

                if chunk:
                    reasoning = None
                    if hasattr(chunk, "additional_kwargs"):
                        reasoning = chunk.additional_kwargs.get(
                            "reasoning_content"
                        ) or chunk.additional_kwargs.get("reasoning")
                    if not reasoning and hasattr(chunk, "response_metadata"):
                        reasoning = chunk.response_metadata.get(
                            "reasoning_content"
                        ) or chunk.response_metadata.get("reasoning")
                    if reasoning:
                        reasoningBuffer += str(reasoning)

            elif eventKind == "on_chat_model_end":
                try:
                    endOutput = event.get("data", {}).get("output")
                    metadata = event.get("metadata", {}) or {}
                    eventAgentName = _inferLlmLogAgent(
                        metadata, currentGraphNodeName, activeAgentName
                    )
                    strippedReasoningSummary = reasoningBuffer.strip()
                    endToolCalls = []
                    if endOutput is not None:
                        rawToolCalls = getattr(endOutput, "tool_calls", None) or []
                        endToolCalls = [
                            {"name": tc.get("name"), "args": tc.get("args"), "id": tc.get("id")}
                            for tc in rawToolCalls
                        ]
                    responseContent = ""
                    if endOutput is not None:
                        rawContent = getattr(endOutput, "content", "")
                        responseContent = rawContent if isinstance(rawContent, str) else str(rawContent)
                    usageMetadata = getattr(endOutput, "usage_metadata", None) if endOutput is not None else None
                    responseMetadata = getattr(endOutput, "response_metadata", {}) if endOutput is not None else {}
                    finishReason = responseMetadata.get("finish_reason") if isinstance(responseMetadata, dict) else None
                    logEvent(
                        logger,
                        "llm.call_completed",
                        logCategory="llm",
                        actorType="agent",
                        agent=eventAgentName,
                        claimId=graphInput.get("claimId"),
                        threadId=graphInput.get("threadId"),
                        responseContent=responseContent,
                        reasoningContent=strippedReasoningSummary,
                        hasReasoningSummary=bool(strippedReasoningSummary),
                        reasoningLength=len(strippedReasoningSummary),
                        toolCalls=endToolCalls,
                        toolCallCount=len(endToolCalls),
                        tokenUsage=usageMetadata,
                        finishReason=finishReason,
                        pendingToolCalls=pendingToolCalls,
                        message="LLM call completed",
                    )
                except Exception as logErr:
                    logger.warning("llm.call_completed log failed: %r", logErr, exc_info=True)

                if pendingToolCalls > 0:
                    # Qwen3-class models split prose and tool_call across two
                    # on_chat_model_end events. When the prose event fires
                    # while a prior tool is still counted as pending, the
                    # user-facing content (e.g., extraction table) would be
                    # silently dropped. Route it through the same bubble gate
                    # used in the hasToolCalls branch below before resetting.
                    pendingOutput = event.get("data", {}).get("output")
                    rawPendingContent = tokenBuffer.strip() or (
                        getattr(pendingOutput, "content", "")
                        if pendingOutput is not None
                        else ""
                    )
                    cleanedPending = _stripToolCallJson(rawPendingContent)
                    cleanedPending = _stripThinkingTags(cleanedPending)
                    cleanedPending = _stripToolCallExpressions(cleanedPending)
                    if _isUserFacingProse(cleanedPending):
                        try:
                            template = templates.get_template(
                                "partials/message_bubble.html"
                            )
                            pendingHtml = template.render(
                                content=cleanedPending,
                                isAi=True,
                                confidenceScores=None,
                                violations=None,
                                timestamp=datetime.now(
                                    ZoneInfo("Asia/Singapore")
                                ).strftime("%-I:%M %p"),
                            )
                        except Exception:
                            pendingHtml = (
                                f'<div class="ai-message">{cleanedPending}</div>'
                            )
                        yield ServerSentEvent(
                            raw_data=pendingHtml, event=SseEvent.MESSAGE
                        )
                        logEvent(
                            logger,
                            "sse.mid_stream_bubble_emitted",
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            threadId=graphInput.get("threadId"),
                            contentLength=len(cleanedPending),
                            pendingToolCalls=pendingToolCalls,
                            context="emitted_during_pending_tool_calls",
                        )
                    tokenBuffer = ""
                    reasoningBuffer = ""
                    continue

                output = event.get("data", {}).get("output")
                hasToolCalls = output and hasattr(output, "tool_calls") and output.tool_calls

                if hasToolCalls:
                    suppressMidStreamBubble = (
                        activeAgentName == "intake-gpt"
                        and _isFieldConfirmationToolCall(output.tool_calls)
                    )
                    # Use tokenBuffer when streaming populated it; fall back to
                    # output.content for models that only emit content on the end event.
                    rawContent = tokenBuffer.strip() or (
                        getattr(output, "content", "") if output is not None else ""
                    )
                    cleanedBuffer = _stripToolCallJson(rawContent)
                    cleanedBuffer = _stripThinkingTags(cleanedBuffer)
                    cleanedBuffer = _stripToolCallExpressions(cleanedBuffer)

                    # Fix A (UAT Gap 1): emit user-facing prose as a chat bubble BEFORE
                    # appending to thinkingEntries. Per v5 prompt, content preceding a
                    # tool_call is normal user-addressed text (extraction table, policy
                    # summary) — not internal reasoning. Reasoning models' private thinking
                    # already flows through reasoningBuffer via additional_kwargs.reasoning_content.
                    if _isUserFacingProse(cleanedBuffer) and not suppressMidStreamBubble:
                        try:
                            template = templates.get_template("partials/message_bubble.html")
                            midHtml = template.render(
                                content=cleanedBuffer,
                                isAi=True,
                                confidenceScores=None,
                                violations=None,
                                timestamp=datetime.now(
                                    ZoneInfo("Asia/Singapore")
                                ).strftime("%-I:%M %p"),
                            )
                        except Exception:
                            midHtml = f'<div class="ai-message">{cleanedBuffer}</div>'
                        yield ServerSentEvent(raw_data=midHtml, event=SseEvent.MESSAGE)
                        logEvent(
                            logger,
                            "sse.mid_stream_bubble_emitted",
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            threadId=graphInput.get("threadId"),
                            contentLength=len(cleanedBuffer),
                            toolCallCount=len(output.tool_calls),
                        )
                    elif _isUserFacingProse(cleanedBuffer) and suppressMidStreamBubble:
                        logEvent(
                            logger,
                            "sse.intake_gpt_field_confirmation_prose_suppressed",
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            threadId=graphInput.get("threadId"),
                            contentLength=len(cleanedBuffer),
                            preview=cleanedBuffer[:120],
                            toolCallCount=len(output.tool_calls),
                            message="Suppressed mid-stream prose because intake-gpt field confirmation will render from interrupt payload",
                        )
                    else:
                        # Trivial filler or empty after strip: preserve existing
                        # thinking-entry behaviour.
                        if cleanedBuffer:
                            thinkingEntries.append(
                                {
                                    "type": "reasoning",
                                    "content": cleanedBuffer,
                                }
                            )
                            # Post-ship telemetry: track false-negatives of the prose gate.
                            # If users report missing content, query logs for this event to
                            # tune _isUserFacingProse (40-char / markdown-marker heuristic).
                            logEvent(
                                logger,
                                "sse.content_suppressed_as_reasoning",
                                logCategory="sse",
                                claimId=graphInput.get("claimId"),
                                threadId=graphInput.get("threadId"),
                                contentLength=len(cleanedBuffer),
                                preview=cleanedBuffer[:80],
                                toolCallCount=len(output.tool_calls),
                            )

                    if reasoningBuffer.strip():
                        thinkingEntries.append(
                            {
                                "type": "reasoning_b",
                                "content": reasoningBuffer.strip(),
                            }
                        )
                    # Show brief reasoning summary in thinking panel
                    reasoningText = reasoningBuffer.strip() or ""
                    if reasoningText:
                        preview = reasoningText[:120].replace("\n", " ").strip()
                        if len(reasoningText) > 120:
                            preview += "..."
                        yield ServerSentEvent(
                            raw_data="Reasoning...",
                            event=SseEvent.STEP_NAME,
                        )
                        yield ServerSentEvent(
                            raw_data=(
                                f'<div class="text-xs text-outline/50 italic mt-1">{preview}</div>'
                            ),
                            event=SseEvent.STEP_CONTENT,
                        )
                    tokenBuffer = ""
                    reasoningBuffer = ""
                else:
                    emittedThinkingSummary = False
                    if reasoningBuffer.strip():
                        thinkingEntries.append(
                            {
                                "type": "reasoning_b",
                                "content": reasoningBuffer.strip(),
                            }
                        )
                        # Show brief reasoning summary in thinking panel
                        preview = reasoningBuffer.strip()[:120].replace("\n", " ").strip()
                        if len(reasoningBuffer.strip()) > 120:
                            preview += "..."
                        yield ServerSentEvent(
                            raw_data="Reasoning...",
                            event=SseEvent.STEP_NAME,
                        )
                        yield ServerSentEvent(
                            raw_data=(
                                f'<div class="text-xs text-outline/50 italic mt-1">{preview}</div>'
                            ),
                            event=SseEvent.STEP_CONTENT,
                        )
                        emittedThinkingSummary = True
                    yield ServerSentEvent(
                        raw_data="Preparing response...", event=SseEvent.STEP_NAME
                    )
                    if not emittedThinkingSummary and not hadAnyToolCall:
                        directSummary = "Responding directly without tool calls."
                        usedFallbackThinkingSummary = True
                        thinkingEntries.append(
                            {
                                "type": "reasoning_summary",
                                "content": directSummary,
                            }
                        )
                        yield ServerSentEvent(
                            raw_data=(
                                f'<div class="text-xs text-outline/50 italic mt-1">{directSummary}</div>'
                            ),
                            event=SseEvent.STEP_CONTENT,
                        )
                        logEvent(
                            logger,
                            "sse.fallback_thinking_summary_emitted",
                            logCategory="sse",
                            actorType="agent",
                            agent=activeAgentName,
                            claimId=graphInput.get("claimId"),
                            threadId=graphInput.get("threadId"),
                            summary=directSummary,
                            hasReasoningSummary=False,
                            usedFallbackThinkingSummary=usedFallbackThinkingSummary,
                            message="Fallback Thinking summary emitted",
                        )
                    # BUG-016: only capture the first non-empty finalResponse. The
                    # intake agent's confirmation message is the first non-tool
                    # on_chat_model_end. Post-submission agents (compliance, fraud,
                    # advisor) emit subsequent on_chat_model_end events that must
                    # not overwrite the intake agent's clean submission response.
                    if not finalResponse:
                        cleanedFinalResponse = _stripToolCallJson(tokenBuffer)
                        if not cleanedFinalResponse and _looksLikeStructuredPayloadLeak(tokenBuffer):
                            logEvent(
                                logger,
                                "sse.final_response_suppressed_as_payload",
                                logCategory="sse",
                                claimId=graphInput.get("claimId"),
                                threadId=threadId,
                                preview=tokenBuffer[:120],
                                message="Suppressed final response that looked like a structured payload leak",
                            )
                        finalResponse = cleanedFinalResponse
                    tokenBuffer = ""
                    reasoningBuffer = ""

                    # BUG-026/027/029: if submitClaim already completed, we have the
                    # final response. Set shouldTerminateEarly but do NOT break yet —
                    # let the graph exhaust the intakeNode so it can checkpoint
                    # claimSubmitted=True and call flushSteps. We break when we see
                    # the first post-submission on_chain_start event above.
                    if claimSubmittedFlag:
                        shouldTerminateEarly = True

            elif eventKind == "on_tool_start":
                toolName = event.get("name", "unknown")
                toolStartTimes[toolName] = time.time()
                pendingToolCalls += 1
                hadAnyToolCall = True
                logEvent(
                    logger,
                    "tool.start",
                    logCategory="agent",
                    actorType="agent",
                    agent=activeAgentName,
                    employeeId=employeeIdVar.get(None),
                    claimId=graphInput.get("claimId"),
                    draftClaimNumber=f"DRAFT-{graphInput.get('claimId', '')[:8]}",
                    threadId=threadId,
                    toolName=toolName,
                    status="started",
                    payload={"input": event.get("data", {}).get("input")},
                    message="Intake tool started",
                )
                # Plan 13-16: askHuman uses the INTERRUPT channel (line ~1507),
                # not the thinking panel. Skip STEP_NAME + pathway UI emission
                # entirely while preserving bookkeeping (pendingToolCalls above,
                # plus the askHumanFired signal for _calcProgressPct).
                # Source: 13-DEBUG-tool-name-leak.md.
                if toolName in {"askHuman", "requestHumanInput"}:
                    askHumanFired = True
                    continue
                label = TOOL_LABELS.get(toolName, f"Running {toolName}...")
                yield ServerSentEvent(raw_data=label, event=SseEvent.STEP_NAME)

                # Pathway: mark tool as in_progress
                if toolName in TOOL_TO_STEP:
                    pathwayActiveTools.add(toolName)
                    pathwayToolTimestamps[toolName] = _nowTimestamp()
                    try:
                        steps = _buildPathwaySteps(
                            pathwayCompletedTools,
                            pathwayActiveTools,
                            hasImage,
                            pathwayToolTimestamps,
                            pathwayExtractionDetails,
                        )
                        pathwayHtml = templates.get_template(
                            "partials/decision_pathway.html"
                        ).render(steps=steps)
                        yield ServerSentEvent(raw_data=pathwayHtml, event=SseEvent.PATHWAY_UPDATE)
                    except Exception as e:
                        logEvent(
                            logger,
                            "sse.pathway_render_error",
                            level=logging.ERROR,
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            toolName=toolName,
                            error=str(e),
                            message="Error rendering pathway on tool start",
                        )

            elif eventKind == "on_tool_end":
                toolName = event.get("name", "unknown")
                toolOutput = event.get("data", {}).get("output", "")
                startTime = toolStartTimes.pop(toolName, None)
                elapsed = time.time() - startTime if startTime else 0
                toolError = _toolOutputError(toolOutput)
                logEvent(
                    logger,
                    "tool.end" if not toolError else "tool.error",
                    level=logging.WARNING if toolError else logging.INFO,
                    logCategory="agent",
                    actorType="agent",
                    agent=activeAgentName,
                    employeeId=employeeIdVar.get(None),
                    claimId=graphInput.get("claimId"),
                    draftClaimNumber=f"DRAFT-{graphInput.get('claimId', '')[:8]}",
                    threadId=threadId,
                    toolName=toolName,
                    status="failed" if toolError else "completed",
                    elapsedMs=round(elapsed * 1000),
                    errorType="ToolError" if toolError else None,
                    payload={"output": toolOutput, "error": toolError},
                    message="Intake tool failed" if toolError else "Intake tool completed",
                )
                # Plan 13-16: suppress askHuman UI emission + thinkingEntries
                # append. The INTERRUPT channel (see line ~1507) owns the
                # user-visible surface. Pending-call bookkeeping still runs.
                # Source: 13-DEBUG-tool-name-leak.md section 4 Option C.
                if toolName in {"askHuman", "requestHumanInput"}:
                    pendingToolCalls = max(0, pendingToolCalls - 1)
                    continue
                summary = _summarizeToolOutput(toolName, toolOutput)
                thinkingEntries.append(
                    {
                        "type": "tool",
                        "name": toolName,
                        "elapsed": elapsed,
                        "output": toolOutput,
                    }
                )
                pendingToolCalls = max(0, pendingToolCalls - 1)
                yield ServerSentEvent(
                    raw_data=f'<div class="text-xs text-outline mt-1">{summary}</div>',
                    event=SseEvent.STEP_CONTENT,
                )

                # Pathway: mark tool as completed
                if toolName in TOOL_TO_STEP and not toolError:
                    pathwayActiveTools.discard(toolName)
                    pathwayCompletedTools.add(toolName)
                    pathwayToolTimestamps[toolName] = _nowTimestamp()
                    if toolName == "submitClaim" and "searchPolicies" not in pathwayCompletedTools:
                        pathwayCompletedTools.add("searchPolicies")
                        pathwayToolTimestamps["searchPolicies"] = _nowTimestamp()
                    if (
                        toolName in ("searchPolicies", "submitClaim")
                        and "extractReceiptFields" not in pathwayCompletedTools
                    ):
                        pathwayCompletedTools.add("extractReceiptFields")
                        pathwayToolTimestamps["extractReceiptFields"] = _nowTimestamp()
                    if toolName == "extractReceiptFields":
                        pathwayExtractionDetails = _extractExtractionDetails(toolOutput)
                    try:
                        steps = _buildPathwaySteps(
                            pathwayCompletedTools,
                            pathwayActiveTools,
                            hasImage,
                            pathwayToolTimestamps,
                            pathwayExtractionDetails,
                        )
                        pathwayHtml = templates.get_template(
                            "partials/decision_pathway.html"
                        ).render(steps=steps)
                        yield ServerSentEvent(raw_data=pathwayHtml, event=SseEvent.PATHWAY_UPDATE)
                    except Exception as e:
                        logEvent(
                            logger,
                            "sse.pathway_render_error",
                            level=logging.ERROR,
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            toolName=toolName,
                            error=str(e),
                            message="Error rendering pathway on tool end",
                        )

                # Table: add/update row after extraction or submission
                if toolName == "extractReceiptFields":
                    details = _extractExtractionDetails(toolOutput)
                    if details:
                        # amountStr may be "₫ 510000.0", "€ 50.00", "SGD 12.34", etc.
                        # Strip to digits + decimal point to get a float-safe value —
                        # previously only "SGD "/"USD " prefixes were handled, causing
                        # float() to raise on other currency symbols and fall back to
                        # emitting the raw tool result as content. Source: CLAIM-022.
                        rawAmount = details.get("amount", "--")
                        numericMatch = re.search(r"[\d.]+", str(rawAmount))
                        totalAmountValue = numericMatch.group(0) if numericMatch else "--"
                        tableClaims.append(
                            {
                                "merchant": details.get("merchant", "Processing..."),
                                "receipt_date": details.get("date", "--"),
                                "total_amount": totalAmountValue,
                                "currency": "SGD",
                                "status": "processing",
                                "created_at": datetime.now(ZoneInfo("Asia/Singapore")).strftime(
                                    "%Y-%m-%d %H:%M"
                                ),
                            }
                        )
                elif toolName == "submitClaim":
                    if tableClaims:
                        tableClaims[-1]["status"] = "submitted"
                    # submitClaim completion is the reliable cutover point from
                    # intake chat UX to background post-submission agents. Arm
                    # early termination here so parallel compliance/fraud token
                    # streams never reach the user chat buffer.
                    claimSubmittedFlag = True
                    shouldTerminateEarly = True

                if toolName in ("extractReceiptFields", "submitClaim"):
                    try:
                        renderClaims = tableClaims
                        if toolName == "submitClaim":
                            dbClaims = await fetchClaimsForTable(employeeId=employeeIdVar.get(None))
                            if dbClaims:
                                renderClaims = dbClaims
                        sessionTotal = sum(
                            float(c.get("total_amount", 0) or 0)
                            for c in renderClaims
                            if c.get("total_amount") and str(c.get("total_amount")) != "--"
                        )
                        tableHtml = templates.get_template("partials/submission_table.html").render(
                            claims=renderClaims,
                            sessionTotal=f"SGD {sessionTotal:.2f}",
                            itemCount=len(renderClaims),
                        )
                        yield ServerSentEvent(raw_data=tableHtml, event=SseEvent.TABLE_UPDATE)
                    except Exception as e:
                        logEvent(
                            logger,
                            "sse.table_render_error",
                            level=logging.ERROR,
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            toolName=toolName,
                            error=str(e),
                            message="Error rendering table on tool end",
                        )

    except Exception as e:
        logEvent(
            logger,
            "sse.stream_error",
            level=logging.ERROR,
            logCategory="sse",
            claimId=graphInput.get("claimId"),
            error=str(e),
            message="Error during graph streaming",
        )
        yield ServerSentEvent(raw_data=str(e), event=SseEvent.ERROR)
        return

    # Thinking done summary
    totalElapsed = time.time() - turnStart
    toolCount = sum(1 for e in thinkingEntries if e["type"] == "tool")
    toolLabel = "tool" if toolCount == 1 else "tools"
    summary = f"Thought for {_formatElapsed(totalElapsed)} . {toolCount} {toolLabel}"
    yield ServerSentEvent(raw_data=summary, event=SseEvent.THINKING_DONE)
    logEvent(
        logger,
        "sse.thinking_done",
        logCategory="sse",
        claimId=graphInput.get("claimId"),
        summary=summary,
        message="Thinking done",
    )

    # Fetch graph state once — reused for summary panel, interrupt check, and fallback message
    finalState = None
    graphStateValues = None
    try:
        finalState = await graph.aget_state(config=config)
        graphStateValues = finalState.values if finalState else None
    except Exception as e:
        logEvent(
            logger,
            "sse.graph_state_fetch_error",
            level=logging.ERROR,
            logCategory="sse",
            claimId=graphInput.get("claimId"),
            error=str(e),
            message="Error fetching graph state",
        )

    # Summary panel update (uses graph state for cross-turn receipt data)
    claimId = graphInput.get("claimId", "")
    summaryData = _extractSummaryData(
        thinkingEntries,
        graphState=graphStateValues,
        claimId=claimId,
        askHumanFired=askHumanFired,
    )
    if summaryData:
        try:
            summaryTemplate = templates.get_template("partials/summary_panel.html")
            summaryHtml = summaryTemplate.render(**summaryData)
            yield ServerSentEvent(raw_data=summaryHtml, event=SseEvent.SUMMARY_UPDATE)
        except Exception as e:
            logEvent(
                logger,
                "sse.summary_render_error",
                level=logging.ERROR,
                logCategory="sse",
                claimId=graphInput.get("claimId"),
                error=str(e),
                message="Error rendering summary panel",
            )

    # BUG-026/027/028/029: the astream_events generator exhausts after the inner
    # ReAct agent finishes but BEFORE intakeNode post-processing runs. The
    # intakeNode never gets to set claimSubmitted=True, call flushSteps, or
    # inject confidenceScores. We do all of that here instead.
    if shouldTerminateEarly:
        sessionClaimId = graphInput.get("claimId", "")

        # Extract dbClaimId from the submitClaim tool output captured during streaming
        dbClaimId = None
        claimNumber = None
        for entry in thinkingEntries:
            if entry.get("name") == "submitClaim" and entry.get("type") == "tool":
                parsedDbClaimId, parsedClaimNumber = _extractSubmitClaimIdentifiers(
                    entry.get("output", "")
                )
                if parsedDbClaimId is not None:
                    dbClaimId = parsedDbClaimId
                if parsedClaimNumber:
                    claimNumber = parsedClaimNumber

        if not (finalResponse or "").strip():
            if claimNumber:
                finalResponse = (
                    f"Your claim has been submitted successfully. Claim number: {claimNumber}. "
                    "Please click on New Claim if you would like to submit another receipt. Thank you."
                )
            elif dbClaimId is not None:
                finalResponse = (
                    f"Your claim has been submitted successfully. Claim ID: {dbClaimId}. "
                    "Please click on New Claim if you would like to submit another receipt. Thank you."
                )
            else:
                finalResponse = (
                    "Your claim has been submitted successfully. "
                    "Please click on New Claim if you would like to submit another receipt. Thank you."
                )
            logEvent(
                logger,
                "sse.submission_acknowledgement_synthesized",
                logCategory="sse",
                claimId=sessionClaimId,
                dbClaimId=dbClaimId,
                claimNumber=claimNumber,
                message="Synthesized submission acknowledgement from submitClaim output",
            )

        # BUG-029: Force-update graph checkpoint with claimSubmitted=True so
        # runPostSubmissionAgents checkpoint guard passes
        if dbClaimId is not None:
            try:
                updateValues = {"claimSubmitted": True, "dbClaimId": int(dbClaimId)}
                if claimNumber:
                    updateValues["claimNumber"] = claimNumber
                await graph.aupdate_state(config=config, values=updateValues)
                logEvent(
                    logger,
                    "sse.graph_state_force_updated",
                    logCategory="sse",
                    claimId=sessionClaimId,
                    dbClaimId=dbClaimId,
                    message="Force-updated graph state: claimSubmitted=True",
                )
            except Exception as e:
                logEvent(
                    logger,
                    "sse.graph_state_force_update_error",
                    level=logging.ERROR,
                    logCategory="sse",
                    claimId=sessionClaimId,
                    error=str(e),
                    message="Failed to force-update graph state",
                )

        # BUG-027: Flush buffered audit steps and write claim_submitted entry
        if dbClaimId and sessionClaimId:
            try:
                parsedDbClaimId = int(dbClaimId)
                await flushSteps(sessionClaimId=sessionClaimId, dbClaimId=parsedDbClaimId)
                await logIntakeStep(
                    claimId=parsedDbClaimId,
                    action="claim_submitted",
                    details={"claimNumber": claimNumber or "", "status": "pending"},
                )
                logEvent(
                    logger,
                    "sse.audit_steps_flushed",
                    logCategory="sse",
                    claimId=sessionClaimId,
                    dbClaimId=dbClaimId,
                    message="Flushed audit steps for claim",
                )
            except Exception as e:
                logEvent(
                    logger,
                    "sse.audit_steps_flush_error",
                    level=logging.ERROR,
                    logCategory="sse",
                    claimId=sessionClaimId,
                    error=str(e),
                    message="Failed to flush audit steps",
                )

            # Queue background task for post-submission agents
        if not hasattr(request.state, "backgroundTask"):
            request.state.backgroundTask = None
        request.state.backgroundTask = {
            "graph": graph,
            "threadId": threadId,
            "claimId": sessionClaimId,
        }
        logEvent(
            logger,
            "sse.background_task_queued",
            logCategory="sse",
            claimId=sessionClaimId,
            message="Background task queued for post-submission agents",
        )
        submissionMessage = _stripToolCallExpressions(
            _stripThinkingTags(_stripToolCallJson(finalResponse or ""))
        ).strip()
        if submissionMessage:
            try:
                template = templates.get_template("partials/message_bubble.html")
                messageHtml = template.render(
                    content=submissionMessage,
                    isAi=True,
                    confidenceScores=None,
                    violations=None,
                    timestamp=datetime.now(ZoneInfo("Asia/Singapore")).strftime("%-I:%M %p"),
                )
            except Exception:
                messageHtml = f'<div class="ai-message">{submissionMessage}</div>'
            yield ServerSentEvent(raw_data=messageHtml, event=SseEvent.MESSAGE)
            logEvent(
                logger,
                "assistant.chat_message_rendered",
                logCategory="chat_history",
                actorType="agent",
                agent=activeAgentName,
                employeeId=employeeIdVar.get(None),
                claimId=graphInput.get("claimId"),
                draftClaimNumber=f"DRAFT-{graphInput.get('claimId', '')[:8]}",
                threadId=threadId,
                claimNumber=claimNumber,
                status="rendered",
                payload={"message": submissionMessage},
                message="Assistant chat message rendered",
            )
        return
    else:
        # BUG-016: after the graph completes, refresh the submission table from DB.
        # The advisor node may have updated the claim status (e.g. submitted ->
        # escalated) AFTER the submitClaim TABLE_UPDATE was already emitted during
        # the streaming loop. Fetching from DB here gives the authoritative status.
        if claimSubmittedFlag:
            try:
                dbClaims = await fetchClaimsForTable(employeeId=employeeIdVar.get(None))
                if dbClaims:
                    sessionTotal = sum(
                        float(c.get("total_amount", 0) or 0)
                        for c in dbClaims
                        if c.get("total_amount") and str(c.get("total_amount")) != "--"
                    )
                    finalTableHtml = templates.get_template(
                        "partials/submission_table.html"
                    ).render(
                        claims=dbClaims,
                        sessionTotal=f"SGD {sessionTotal:.2f}",
                        itemCount=len(dbClaims),
                    )
                    yield ServerSentEvent(raw_data=finalTableHtml, event=SseEvent.TABLE_UPDATE)
            except Exception as e:
                logEvent(
                    logger,
                    "sse.table_render_error",
                    level=logging.ERROR,
                    logCategory="sse",
                    claimId=graphInput.get("claimId"),
                    error=str(e),
                    message="Error rendering final table update after advisor",
                )

        # PROBE A — Interrupt detection (resume-contract debug)
        try:
            logEvent(
                logger,
                "debug.interrupt_check",
                level=logging.DEBUG,
                logCategory="sse",
                claimId=graphInput.get("claimId"),
                threadId=graphInput.get("threadId"),
                finalStateExists=finalState is not None,
                finalStateNext=list(finalState.next) if finalState and finalState.next else None,
                taskCount=len(finalState.tasks) if finalState else 0,
                tasksWithInterrupts=[
                    {
                        "name": getattr(t, "name", None),
                        "interruptCount": len(t.interrupts) if hasattr(t, "interrupts") and t.interrupts else 0,
                    }
                    for t in (finalState.tasks if finalState else [])
                ],
                message="Interrupt state check before extraction",
            )
        except Exception as probeErr:
            logger.warning("debug.interrupt_check log failed: %r", probeErr, exc_info=True)

        # Check for interrupt via graph state
        try:
            if finalState and finalState.next:
                for task in finalState.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        payload = task.interrupts[0].value
                        if isinstance(payload, dict):
                            contextMessage = str(payload.get("contextMessage", "") or "").strip()
                            if contextMessage:
                                try:
                                    template = templates.get_template(
                                        "partials/message_bubble.html"
                                    )
                                    contextHtml = template.render(
                                        content=contextMessage,
                                        isAi=True,
                                        confidenceScores=None,
                                        violations=None,
                                        timestamp=datetime.now(
                                            ZoneInfo("Asia/Singapore")
                                        ).strftime("%-I:%M %p"),
                                    )
                                except Exception:
                                    contextHtml = (
                                        f'<div class="ai-message">{contextMessage}</div>'
                                    )
                                yield ServerSentEvent(
                                    raw_data=contextHtml, event=SseEvent.MESSAGE
                                )
                        # Dispatch on uiKind for interrupt-prompt rendering.
                        uiKind = str(payload.get("uiKind", "text"))
                        question = (
                            payload.get("question", str(payload))
                            if isinstance(payload, dict)
                            else str(payload)
                        )
                        logEvent(
                            logger,
                            "sse.interrupt_render",
                            logCategory="sse",
                            claimId=graphInput.get("claimId"),
                            kind=payload.get("kind") if isinstance(payload, dict) else None,
                            uiKind=uiKind,
                            blockingStep=payload.get("blockingStep") if isinstance(payload, dict) else None,
                            message="SSE interrupt render branch selected",
                        )
                        if uiKind == "buttons":
                            options = payload.get("options") or []
                            try:
                                buttonTemplate = templates.get_template(
                                    "partials/interrupt_buttons.html"
                                )
                                interruptHtml = buttonTemplate.render(
                                    question=question,
                                    options=options,
                                )
                            except Exception:
                                # Fallback to plain text if template rendering fails.
                                interruptHtml = str(question)
                            yield ServerSentEvent(
                                raw_data=interruptHtml, event=SseEvent.INTERRUPT
                            )
                        else:
                            # Note: no session mutation here. The checkpointer
                            # already persisted the pending interrupt when
                            # interrupt() fired; the next POST reads state via
                            # isPausedAtInterrupt(graph.aget_state(...)).
                            yield ServerSentEvent(
                                raw_data=str(question), event=SseEvent.INTERRUPT
                            )
                        return
        except Exception as e:
            logEvent(
                logger,
                "sse.interrupt_check_error",
                level=logging.ERROR,
                logCategory="sse",
                claimId=graphInput.get("claimId"),
                error=str(e),
                message="Error checking interrupt state",
            )

    # Extract final response text
    finalText = ""
    if finalResponse and finalResponse.strip():
        finalText = _stripToolCallExpressions(
            _stripThinkingTags(_stripToolCallJson(finalResponse))
        ).strip()
    if not finalText and tokenBuffer.strip():
        finalText = _stripToolCallExpressions(
            _stripThinkingTags(_stripToolCallJson(tokenBuffer))
        ).strip()
    if not finalText:
        # Use already-fetched state if available, otherwise fetch
        if graphStateValues:
            messages = graphStateValues.get("messages", [])
            for msg in reversed(messages):
                if (
                    hasattr(msg, "type")
                    and msg.type == "ai"
                    and hasattr(msg, "content")
                    and msg.content
                ):
                    finalText = _stripToolCallExpressions(
                        _stripThinkingTags(_stripToolCallJson(str(msg.content)))
                    )
                    break
        if not finalText:
            finalText = await _getFallbackMessage(graph, config)

    # BUG-013: Detect hallucinated claim submission (second layer — message)
    # Guard must only fire on actual success phrasing. Mere echo of a CLAIM-XXX
    # number in a refusal is a false positive (e.g., user asks "load CLAIM-010"
    # and the LLM replies "I can't retrieve CLAIM-010").
    if finalText:
        submittedInText = bool(_SUBMISSION_SUCCESS_PATTERN.search(finalText))
        submitCallMade = any(
            e.get("name") == "submitClaim" for e in thinkingEntries if e.get("type") == "tool"
        )
        if submittedInText and not submitCallMade:
            logEvent(
                logger,
                "sse.hallucinated_submit_detected",
                level=logging.WARNING,
                logCategory="sse",
                claimId=graphInput.get("claimId"),
                message="BUG-013: Hallucinated submission detected; AI claimed submission without submitClaim tool call",
            )
            try:
                template = templates.get_template("partials/message_bubble.html")
                errorHtml = template.render(
                    content=(
                        "I encountered an issue submitting your claim. The submission did "
                        "not complete. Please try again by typing 'submit' or 'yes'."
                    ),
                    isAi=True,
                    confidenceScores=None,
                    violations=None,
                    timestamp=datetime.now(ZoneInfo("Asia/Singapore")).strftime("%-I:%M %p"),
                )
            except Exception:
                errorHtml = (
                    '<div class="ai-message">I encountered an issue submitting your claim. '
                    'Please try again by typing "submit".</div>'
                )
            yield ServerSentEvent(raw_data=errorHtml, event=SseEvent.MESSAGE)
            return

    if finalText:
        if _looksLikeStructuredPayloadLeak(finalText):
            logEvent(
                logger,
                "sse.final_response_suppressed_as_payload",
                logCategory="sse",
                claimId=graphInput.get("claimId"),
                threadId=threadId,
                preview=finalText[:120],
                message="Suppressed final response that looked like a structured payload leak",
            )
            finalText = ""
    if finalText:
        confidenceScores = _extractConfidenceScores(thinkingEntries)
        violations = _extractViolations(thinkingEntries)
        try:
            template = templates.get_template("partials/message_bubble.html")
            messageHtml = template.render(
                content=finalText,
                isAi=True,
                confidenceScores=confidenceScores,
                violations=violations,
                timestamp=datetime.now().strftime("%-I:%M %p"),
            )
        except Exception:
            messageHtml = f'<div class="ai-message">{finalText}</div>'
        yield ServerSentEvent(raw_data=messageHtml, event=SseEvent.MESSAGE)
        logEvent(
            logger,
            "assistant.chat_message_rendered",
            logCategory="chat_history",
            actorType="agent",
            agent=activeAgentName,
            employeeId=employeeIdVar.get(None),
            claimId=graphInput.get("claimId"),
            draftClaimNumber=f"DRAFT-{graphInput.get('claimId', '')[:8]}",
            threadId=threadId,
            claimNumber=summaryData.get("claimNumber") if summaryData else None,
            status="rendered",
            payload={"message": finalText},
            message="Assistant chat message rendered",
        )
