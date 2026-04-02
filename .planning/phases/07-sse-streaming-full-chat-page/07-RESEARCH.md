# Phase 7: SSE Streaming + Full Chat Page - Research

**Researched:** 2026-04-02
**Domain:** FastAPI SSE + HTMX + LangGraph astream_events + Alpine.js reactive state
**Confidence:** HIGH — all critical patterns verified against installed library versions and official docs

---

## Summary

Phase 7 is a migration + wiring phase, not a greenfield build. The goal is to port the working `app.py` (Chainlit) streaming logic into the FastAPI scaffold built in Phase 6, and wire up the static `chat.html` template to become a fully functional page.

The core SSE stack is already decided and verified: `fastapi.sse.EventSourceResponse` (FastAPI 0.135.2 built-in, confirmed installed), HTMX SSE extension (`sse.js` already in `/static/js/`), and `graph.astream_events(version="v2")` (same LangGraph call used in `app.py`). The hardest technical problems are: (1) decoupling the POST trigger from the GET SSE stream so HTMX can handle both, (2) correct interrupt/resume detection without session flags, and (3) preventing Alpine.js state loss on HTMX DOM swaps.

The reference implementation is `src/agentic_claims/app.py`. All streaming logic (`_stripToolCallJson`, `_stripThinkingTags`, `_summarizeToolOutput`, `TOOL_LABELS`, the event classification loop) must be preserved and ported — not re-implemented.

**Primary recommendation:** One `asyncio.Queue` per session (keyed by `thread_id`) held in a module-level dict. POST endpoint puts the graph input into the queue and returns 204. SSE GET endpoint reads from the queue, invokes `graph.astream_events`, and streams events. This cleanly decouples HTMX's form POST from the HTMX SSE connection without websockets or global state.

---

## Standard Stack

### Core (already installed, no changes to pyproject.toml)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| `fastapi.sse.EventSourceResponse` | FastAPI 0.135.2 | SSE response type for streaming | Confirmed in installed FastAPI — `from fastapi.sse import EventSourceResponse, ServerSentEvent` works |
| `fastapi.sse.ServerSentEvent` | FastAPI 0.135.2 | Individual SSE event with `data`, `event`, `id`, `retry` fields | Same import, confirmed `ServerSentEvent(data=..., event=..., id=...)` works |
| `langgraph` (astream_events) | >=0.4 | Token-by-token streaming from graph | Existing — `graph.astream_events(input, config=..., version="v2")` |
| `langgraph.types.Command` | >=0.4 | Resume interrupted graph | Existing — `Command(resume={...})` confirmed importable |
| HTMX SSE extension | 2.2.4 | `sse-connect`, `sse-swap` on chat container | Already at `/static/js/sse.js` |
| Alpine.js | current | Local UI state for collapse/expand, image preview, processing indicator | Already at `/static/js/alpine.min.js` |
| `python-multipart` | >=0.0.20 | Multipart form parsing for receipt image upload | Already in pyproject.toml |

### No New Dependencies Required

Phase 7 requires zero new Python packages. All needed libraries are already installed. Do not add `sse-starlette` — it is redundant given `fastapi.sse`.

---

## Architecture Patterns

### Pattern 1: POST + SSE Decoupled via asyncio.Queue (STRE-03)

The fundamental challenge: HTMX SSE connects via GET (the browser's EventSource opens a GET connection). But submitting a message is a POST. These are two separate HTTP connections. The graph invocation must bridge them.

**Solution: module-level session queue dict**

```python
# src/agentic_claims/web/sessionQueues.py
import asyncio
from typing import Dict

# Module-level dict: thread_id -> asyncio.Queue
_queues: Dict[str, asyncio.Queue] = {}

def getOrCreateQueue(threadId: str) -> asyncio.Queue:
    if threadId not in _queues:
        _queues[threadId] = asyncio.Queue(maxsize=10)
    return _queues[threadId]

def removeQueue(threadId: str) -> None:
    _queues.pop(threadId, None)
```

**POST endpoint (chat/message router):**
```python
@router.post("/chat/message")
async def postMessage(
    request: Request,
    message: str = Form(...),
    receipt: UploadFile | None = File(default=None),
):
    sessionIds = getSessionIds(request)
    threadId = sessionIds["threadId"]
    claimId = sessionIds["claimId"]
    queue = getOrCreateQueue(threadId)
    # Build graph input, store image if receipt present
    await queue.put({"threadId": threadId, "claimId": claimId, "message": message, "receipt": receipt_b64})
    return Response(status_code=204)  # HTMX: no swap needed
```

**SSE GET endpoint:**
```python
@router.get("/chat/stream")
async def streamChat(request: Request):
    sessionIds = getSessionIds(request)
    threadId = sessionIds["threadId"]
    queue = getOrCreateQueue(threadId)
    graph = request.app.state.graph

    async def eventGenerator():
        while True:
            if await request.is_disconnected():
                break
            try:
                graphInput = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield ServerSentEvent(data="", event="ping")
                continue
            async for sseEvent in runGraph(graph, graphInput, request):
                yield sseEvent
            yield ServerSentEvent(data="done", event="done")

    return EventSourceResponse(eventGenerator())
```

**Source:** CONTEXT.md decision + sse-starlette broadcast pattern (Context7, HIGH confidence)

---

### Pattern 2: HTMX SSE Wiring (STRE-05)

**Critical rule:** `hx-ext="sse"` and `sse-connect` MUST be on the same element. `sse-swap` can be on the same element or on child elements.

```html
<!-- chat.html: wire SSE on the chat history container -->
<div id="chatHistory"
     hx-ext="sse"
     sse-connect="/chat/stream"
     class="flex-1 overflow-y-auto ...">

    <!-- Token stream target: sse-swap appends tokens to this div -->
    <div id="aiResponseStream"
         sse-swap="token"
         hx-swap="beforeend"></div>

    <!-- Thinking panel step name: replaces label -->
    <div id="thinkingStepName"
         sse-swap="step-name"
         hx-swap="innerHTML"></div>

    <!-- Thinking panel done: collapses panel -->
    <div sse-swap="thinking-done"
         hx-swap="innerHTML"
         id="thinkingDone"></div>

    <!-- Full AI message (sent once, after stream complete) -->
    <div sse-swap="message"
         hx-swap="beforeend"
         id="aiMessages"></div>

    <!-- Done sentinel (for Playwright tests) -->
    <div sse-swap="done"
         data-testid="response-complete"></div>
</div>
```

**Token accumulation:** Use `hx-swap="beforeend"` for `token` events — each token appends a `<span>` to the response div. Do NOT use `innerHTML` for token events — it replaces the full div on every token (O(n) repaint, visible flicker at ~50 tokens).

**Source:** HTMX SSE extension official docs (Context7, HIGH confidence); PITFALLS.md Pitfall 12

---

### Pattern 3: SSE Event Taxonomy (STRE-01)

All event names defined as constants — never as inline strings in templates or server code.

```python
# src/agentic_claims/web/sseEvents.py
class SseEvent:
    TOKEN = "token"              # LLM text token (beforeend into response div)
    THINKING_START = "thinking-start"  # Thinking panel opens
    STEP_NAME = "step-name"      # Tool step label update (innerHTML)
    STEP_CONTENT = "step-content" # Tool output summary (beforeend into thinking panel)
    THINKING_DONE = "thinking-done"  # Thinking panel collapses to summary line
    MESSAGE = "message"          # Final complete AI message (beforeend)
    SUMMARY_UPDATE = "summary-update"  # Right panel data (innerHTML on summary bento)
    DONE = "done"                # Stream complete sentinel
    ERROR = "error"              # Agent or server error
    INTERRUPT = "interrupt"      # LangGraph askHuman triggered
```

**Data payloads (JSON strings in `data` field):**

| Event | Data shape |
|-------|-----------|
| `token` | `"text chunk"` (raw string, not JSON) |
| `thinking-start` | `""` |
| `step-name` | `"Extracting receipt fields..."` |
| `step-content` | `"Extracted receipt: Starbucks, SGD 4.50"` |
| `thinking-done` | `"Thought for 12s · 3 tools"` (summary line) |
| `message` | HTML fragment of the full AI message bubble |
| `summary-update` | HTML fragment of updated summary panel content |
| `done` | `""` |
| `error` | `"Error message string"` |
| `interrupt` | `"Clarification question text"` |

**Source:** PITFALLS.md Pitfall 12 (case sensitivity) + CONTEXT.md decisions; HIGH confidence

---

### Pattern 4: LangGraph astream_events Mapping (STRE-02)

Port the event classification loop from `app.py` directly into the SSE generator. The mapping is:

```python
async def runGraph(graph, graphInput, request):
    """Translate LangGraph astream_events into SSE events."""
    thinkingEntries = []
    tokenBuffer = ""
    reasoningBuffer = ""
    pendingToolCalls = 0
    toolStartTimes = {}
    turnStart = time.time()

    yield ServerSentEvent(data="", event=SseEvent.THINKING_START)

    config = {"configurable": {"thread_id": graphInput["threadId"]}}

    # Handle interrupt resume vs fresh message
    if graphInput.get("isResume"):
        invokeInput = Command(resume=graphInput["resumeData"])
    else:
        invokeInput = buildGraphInput(graphInput)

    async for event in graph.astream_events(invokeInput, config=config, version="v2"):
        if await request.is_disconnected():
            break

        eventKind = event.get("event")

        if eventKind == "on_chat_model_stream":
            if pendingToolCalls > 0:
                continue
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                tokenBuffer += chunk.content
                yield ServerSentEvent(data=chunk.content, event=SseEvent.TOKEN)
            # Capture Type B reasoning (QwQ reasoning_content)
            if chunk and hasattr(chunk, "additional_kwargs"):
                reasoning = chunk.additional_kwargs.get("reasoning_content") or chunk.additional_kwargs.get("reasoning")
                if reasoning:
                    reasoningBuffer += str(reasoning)

        elif eventKind == "on_chat_model_end":
            if pendingToolCalls > 0:
                tokenBuffer = ""
                reasoningBuffer = ""
                continue
            output = event.get("data", {}).get("output")
            hasToolCalls = output and hasattr(output, "tool_calls") and output.tool_calls
            if hasToolCalls:
                cleanedBuffer = _stripToolCallJson(tokenBuffer.strip())
                if cleanedBuffer:
                    thinkingEntries.append({"type": "reasoning", "content": cleanedBuffer})
                if reasoningBuffer.strip():
                    thinkingEntries.append({"type": "reasoning_b", "content": reasoningBuffer.strip()})
                tokenBuffer = ""
                reasoningBuffer = ""

        elif eventKind == "on_tool_start":
            toolName = event.get("name", "unknown")
            toolStartTimes[toolName] = time.time()
            pendingToolCalls += 1
            label = TOOL_LABELS.get(toolName, f"Running {toolName}...")
            yield ServerSentEvent(data=label, event=SseEvent.STEP_NAME)

        elif eventKind == "on_tool_end":
            toolName = event.get("name", "unknown")
            toolOutput = event.get("data", {}).get("output", "")
            elapsed = time.time() - toolStartTimes.pop(toolName, time.time())
            summary = _summarizeToolOutput(toolName, toolOutput)
            thinkingEntries.append({"type": "tool", "name": toolName, "elapsed": elapsed, "output": toolOutput})
            pendingToolCalls = max(0, pendingToolCalls - 1)
            yield ServerSentEvent(data=summary, event=SseEvent.STEP_CONTENT)
            if pendingToolCalls == 0:
                yield ServerSentEvent(data="Analyzing...", event=SseEvent.STEP_NAME)

    # After stream: emit thinking-done summary
    totalElapsed = time.time() - turnStart
    toolCount = sum(1 for e in thinkingEntries if e["type"] == "tool")
    toolLabel = "tool" if toolCount == 1 else "tools"
    summary = f"Thought for {_formatElapsed(totalElapsed)} · {toolCount} {toolLabel}"
    yield ServerSentEvent(data=summary, event=SseEvent.THINKING_DONE)

    # Build final message HTML fragment and emit
    # (use graph.aget_state() fallback if tokenBuffer empty, same as app.py)
    finalText = _stripThinkingTags(_stripToolCallJson(tokenBuffer)) if tokenBuffer.strip() else await getFallbackMessage(graph, config)
    if finalText:
        messageHtml = renderMessageBubble(finalText)  # Jinja2 fragment render
        yield ServerSentEvent(data=messageHtml, event=SseEvent.MESSAGE)
```

**Key: helpers to port from app.py (do not reimplementi):**
- `_stripToolCallJson` — removes trailing `{"name": ...}` artifacts from QwQ-32B
- `_stripThinkingTags` — removes `<think>`, `<Thinking>` XML wrappers
- `_summarizeToolOutput` — human-readable tool output for thinking panel
- `_formatElapsed` — "12s", "1m 3s"
- `TOOL_LABELS` — step name strings

**Source:** `src/agentic_claims/app.py` (existing, HIGH confidence)

---

### Pattern 5: Interrupt/Resume Detection (MIGR-05)

The graph pauses when `askHuman` triggers `langgraph.types.interrupt()`. Detection uses `graph.aget_state()` — NOT session flags in cookies or module-level dicts.

```python
# After graph.astream_events() loop completes, check for interrupt
finalState = await graph.aget_state(config={"configurable": {"thread_id": threadId}})
if finalState.next:
    for task in finalState.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            payload = task.interrupts[0].value
            question = payload.get("question", str(payload))
            yield ServerSentEvent(data=question, event=SseEvent.INTERRUPT)
```

**On the frontend:** When `interrupt` SSE event arrives, Alpine.js sets `awaitingClarification = true`. The input box stays active but the next POST is built with `isResume: true` in the session data (stored in session cookie, not Alpine state). The POST endpoint checks whether the session is in interrupt mode and builds `Command(resume=...)` instead of a fresh HumanMessage.

**Resume detection in POST endpoint:**
```python
# POST endpoint checks session flag to decide graph input type
awaitingClarification = request.session.get("awaiting_clarification", False)
if awaitingClarification:
    graphInput = {"isResume": True, "resumeData": {"response": message, "action": "confirm"}}
    request.session["awaiting_clarification"] = False
else:
    graphInput = {"isResume": False, "message": message, ...}
```

**Source:** `src/agentic_claims/cli.py` (existing pattern) + LangGraph interrupt docs (Context7, HIGH confidence)

---

### Pattern 6: Receipt Image Upload (MIGR-03)

**Multipart form with HTMX:**
```html
<form id="chatForm"
      hx-post="/chat/message"
      hx-encoding="multipart/form-data"
      hx-target="this"
      hx-swap="none">
    <input type="hidden" name="thread_id" value="{{ threadId }}">
    <input type="file" id="receiptFile" name="receipt" accept="image/*" class="hidden"
           x-ref="fileInput"
           @change="handleFileSelect($event)">
    <textarea name="message" x-model="messageText"></textarea>
    <button type="button" @click="$refs.fileInput.click()">
        <span class="material-symbols-outlined">attach_file</span>
    </button>
    <button type="submit">Send</button>
</form>
```

**FastAPI endpoint signature:**
```python
@router.post("/chat/message")
async def postMessage(
    request: Request,
    message: str = Form(default=""),
    receipt: UploadFile | None = File(default=None),
):
    if receipt:
        imageBytes = await receipt.read()
        imageB64 = base64.b64encode(imageBytes).decode("utf-8")
        storeImage(claimId, imageB64)
```

**Image preview via Alpine.js** (before submit):
```javascript
handleFileSelect(event) {
    const file = event.target.files[0]
    if (file) {
        this.previewUrl = URL.createObjectURL(file)
        this.fileName = file.name
    }
}
```

**Source:** PITFALLS.md Pitfall 10 + FastAPI File upload docs; HIGH confidence

---

### Pattern 7: Alpine.js + HTMX Coexistence

**Critical rule:** Never put Alpine `x-data` on an element that HTMX swaps. HTMX replaces the DOM node — Alpine's reactive context is destroyed.

**Correct structure:**
```html
<!-- Alpine state on outer stable container — NEVER swapped by HTMX -->
<div x-data="{
    processing: false,
    awaitingClarification: false,
    thinkingCollapsed: false,
    previewUrl: null,
    fileName: null,
    messageText: ''
}">
    <!-- HTMX swap targets are INNER leaf nodes -->
    <div id="aiResponseStream" sse-swap="token" hx-swap="beforeend"></div>
    <div id="thinkingPanel" ...>
        <!-- Alpine x-show here is fine — it's on a stable node -->
        <div x-show="!thinkingCollapsed">...</div>
    </div>
</div>
```

**Alpine store for cross-component state** (summary panel update):
```javascript
// Defined in base.html or a <script> block
Alpine.store('claim', {
    total: '$0.00',
    itemCount: 0,
    warningCount: 0,
    topCategory: '--',
    progressPct: 0,
})
```

Summary panel updates are triggered by the `summary-update` SSE event delivering an HTML fragment, or by Alpine store mutations dispatched from SSE event listeners.

**Source:** PITFALLS.md Integration Gotchas + Alpine.js docs (Context7, HIGH confidence)

---

### Pattern 8: New Claim Reset (CHAT-01)

Reset clears session IDs, wipes `imageStore`, and navigates to `/` which regenerates fresh session IDs.

```python
@router.post("/chat/reset")
async def resetChat(request: Request):
    # Clear old claim image from store
    oldClaimId = request.session.get("claim_id")
    if oldClaimId:
        from agentic_claims.core.imageStore import clearImage
        clearImage(oldClaimId)
    # Generate fresh session IDs
    request.session["thread_id"] = str(uuid.uuid4())
    request.session["claim_id"] = str(uuid.uuid4())
    request.session.pop("awaiting_clarification", None)
    # HTMX redirect to /
    return Response(status_code=204, headers={"HX-Redirect": "/"})
```

**Source:** CONTEXT.md + STATE.md; HIGH confidence

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE response type | Custom `StreamingResponse` with manual `text/event-stream` headers | `fastapi.sse.EventSourceResponse` | Native: sets `Content-Type`, `Cache-Control`, `X-Accel-Buffering: no` (Nginx), keep-alive pings automatically |
| SSE event serialization | Manual `f"event: {name}\ndata: {payload}\n\n"` | `ServerSentEvent(data=..., event=..., id=...)` | Handles encoding, escaping, multi-line data |
| Token streaming loop | New implementation | Port `app.py` event classification loop verbatim | Already tested, handles QwQ-32B artifacts, Type A+B reasoning |
| Tool label mapping | New dict | Reuse `TOOL_LABELS` from `app.py` | Already maps all 5 tools |
| Output cleanup | New regex | Port `_stripToolCallJson`, `_stripThinkingTags` | Already handles QwQ-32B edge cases |
| Disconnect detection | Manual signal handling | `await request.is_disconnected()` inside generator loop | Native Starlette method — checks at each loop iteration |
| Interrupt detection | Session flag boolean | `graph.aget_state()` check after stream | Source of truth is the checkpointer, not session |

---

## Common Pitfalls

### Pitfall 1: `hx-ext="sse"` Not on Same Element as `sse-connect`
**What goes wrong:** SSE connection never established. No events, no errors in browser console.
**Root cause:** HTMX SSE extension requires both attributes on the same DOM element. `sse-swap` can be on child elements but `sse-connect` must co-locate with `hx-ext="sse"`.
**How to avoid:** `<div hx-ext="sse" sse-connect="/chat/stream" ...>` — both on the same container.
**Source:** PITFALLS.md Pitfall 3; HIGH confidence

### Pitfall 2: SSE Generator Runs After Client Disconnect
**What goes wrong:** Tab closed mid-stream → LLM call continues → burns OpenRouter quota, holds DB connections.
**Root cause:** FastAPI does not auto-cancel the generator when client disconnects.
**How to avoid:** Check `await request.is_disconnected()` at the top of every loop iteration inside the generator.
**Source:** PITFALLS.md Pitfall 2; HIGH confidence

### Pitfall 3: Token Stream Using `innerHTML` Instead of `beforeend`
**What goes wrong:** Each token replaces the full div — visible flicker, O(n) DOM repaint per token, accumulated tokens lost.
**Root cause:** Default `hx-swap` is `innerHTML`. For `token` event accumulation, must be `beforeend`.
**How to avoid:** `hx-swap="beforeend"` on the token target div. Use `innerHTML` only for `step-name` and `thinking-done` replacements.
**Source:** PITFALLS.md Performance Traps; HIGH confidence

### Pitfall 4: Alpine.js State Destroyed on HTMX Swap
**What goes wrong:** Thinking panel collapse state, processing flag, file preview URL lost when HTMX updates a parent element.
**Root cause:** HTMX replaces the DOM node entirely — Alpine's reactive scope is bound to the node and is garbage collected.
**How to avoid:** Keep Alpine `x-data` on stable outer containers that HTMX never targets. Only swap inner leaf nodes.
**Source:** PITFALLS.md Pitfall (Alpine/HTMX); HIGH confidence

### Pitfall 5: SSE Event Name Case Mismatch
**What goes wrong:** Some events work, others silently disappear. No errors.
**Root cause:** HTMX SSE extension matches `sse-swap="<name>"` against SSE `event:` field exactly — case sensitive.
**How to avoid:** Define all names as lowercase-with-hyphens constants in `sseEvents.py`. Use the constant in both the server yield and the template `sse-swap` attribute. Never derive event names from class/function names.
**Source:** PITFALLS.md Pitfall 12; HIGH confidence

### Pitfall 6: asyncio.Queue Holds Graph Input Across Sessions
**What goes wrong:** After New Claim reset, the old queue still exists with the old `thread_id` key. New conversation gets routed to old queue.
**Root cause:** Module-level dict is not cleared on session reset.
**How to avoid:** Call `removeQueue(oldThreadId)` in the reset endpoint before generating new session IDs.
**Source:** Pattern reasoning; MEDIUM confidence

### Pitfall 7: Interrupt Resume Uses Wrong Input Shape
**What goes wrong:** Graph receives a `HumanMessage` when it expects `Command(resume=...)`. The interrupt is not resolved, graph loops or errors.
**Root cause:** The SSE stream ended at the interrupt — next POST is a "continuation", not a new message. Must send `Command(resume={"response": userText, ...})` not a fresh `{"messages": [HumanMessage(...)]}`.
**How to avoid:** Set `awaiting_clarification` in session cookie when `interrupt` SSE event is received. POST endpoint checks the cookie to build the correct graph input type.
**Source:** `src/agentic_claims/cli.py` pattern + LangGraph docs; HIGH confidence

---

## Code Examples

### SSE Endpoint (verified pattern)
```python
# Source: fastapi.sse confirmed installed at 0.135.2
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi import APIRouter
from starlette.requests import Request

router = APIRouter()

@router.get("/chat/stream")
async def streamChat(request: Request) -> EventSourceResponse:
    async def generator():
        while True:
            if await request.is_disconnected():
                break
            # ... queue.get() + graph.astream_events() + yield ServerSentEvent(...)
    return EventSourceResponse(generator())
```

### HTMX SSE + multipart form together
```html
<!-- SSE connection on stable container -->
<div hx-ext="sse" sse-connect="/chat/stream">
    <div id="tokenTarget" sse-swap="token" hx-swap="beforeend"></div>
    <form hx-post="/chat/message"
          hx-encoding="multipart/form-data"
          hx-swap="none">
        <input type="file" name="receipt">
        <textarea name="message"></textarea>
        <button type="submit">Send</button>
    </form>
</div>
```

### LangGraph interrupt detection after stream
```python
# Source: LangGraph docs + src/agentic_claims/cli.py
finalState = await graph.aget_state(config={"configurable": {"thread_id": threadId}})
if finalState.next:
    for task in finalState.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            payload = task.interrupts[0].value
            yield ServerSentEvent(data=str(payload), event=SseEvent.INTERRUPT)
```

### Alpine.js state on stable outer container
```html
<div x-data="{
    processing: false,
    awaitingClarification: false,
    previewUrl: null,
    fileName: null
}">
    <!-- HTMX swap targets inside — Alpine on outer -->
    <div id="messages" sse-swap="message" hx-swap="beforeend"></div>
</div>
```

---

## Recommended File Structure for Phase 7

New files to create (within existing web/ slice):

```
src/agentic_claims/web/
├── routers/
│   ├── pages.py              # Existing — unchanged
│   └── chat.py               # NEW: POST /chat/message, GET /chat/stream, POST /chat/reset
├── sessionQueues.py           # NEW: module-level asyncio.Queue dict per thread_id
├── sseEvents.py               # NEW: SseEvent constants class
└── sseHelpers.py              # NEW: port _stripToolCallJson, _stripThinkingTags, _summarizeToolOutput, _formatElapsed, TOOL_LABELS, runGraph()
```

Template changes:
```
templates/
└── chat.html                  # Wire SSE attributes, Alpine state, form POST, image preview
```

**Register the new router in `main.py`:**
```python
from agentic_claims.web.routers.chat import router as chatRouter
app.include_router(chatRouter)
```

---

## State of the Art

| Old Approach (Chainlit) | New Approach (FastAPI) | Impact |
|------------------------|------------------------|--------|
| `cl.Step` + `cl.Message` for streaming | `EventSourceResponse` + SSE events + HTMX swap | UI framework independent, reusable |
| Chainlit session (`cl.user_session`) | Starlette `SessionMiddleware` cookie | Survives page refresh |
| `async with cl.Step(...)` for thinking panel | SSE `thinking-start` → tokens → `thinking-done` events | Frontend controls collapse behavior |
| Chainlit handles image upload | FastAPI `UploadFile` + imageStore | Same imageStore, new upload path |
| Chainlit interrupt popup | SSE `interrupt` event → Alpine sets `awaitingClarification` flag | Text-only clarification in chat thread |

---

## Open Questions

1. **Jinja2 fragment rendering for `message` SSE event**
   - What we know: The `message` SSE event should deliver an HTML fragment (the AI message bubble) to `beforeend` into `#chatHistory`
   - What's unclear: Best pattern to render a Jinja2 template fragment from within the SSE generator (inside the router, not a request handler)
   - Recommendation: Pass `templates` instance to `sseHelpers.py` and call `templates.get_template("partials/message_bubble.html").render(content=finalText)` — no HTTP round-trip needed
   - **This requires creating `templates/partials/message_bubble.html`**

2. **Summary panel update mechanism**
   - What we know: Summary panel must update in real-time as fields are extracted (CONTEXT.md decision)
   - What's unclear: Whether to use SSE `summary-update` event with HTML fragment OR Alpine.js store mutations from custom JS event listeners on SSE events
   - Recommendation: SSE `summary-update` event delivers HTML fragment directly — simpler, no JS. Alpine.js store used only for local UI state (processing flag, collapse).

3. **`imageStore.clearImage` function**
   - What we know: `imageStore.py` has `storeImage` and `getImage`. Reset endpoint should clear old images.
   - What's unclear: Whether `clearImage` exists or needs to be added.
   - Recommendation: Check `imageStore.py` at implementation time — add `clearImage(claimId)` if missing.

---

## Sources

### Primary (HIGH confidence)
- `src/agentic_claims/app.py` — Working Chainlit streaming implementation (reference for porting)
- `src/agentic_claims/cli.py` — Interrupt/resume pattern using `aget_state()`
- FastAPI 0.135.2 installed — `from fastapi.sse import EventSourceResponse, ServerSentEvent` confirmed working
- LangGraph interrupt docs (Context7 `/websites/langchain_oss_python_langgraph`) — `Command(resume=...)` pattern
- HTMX SSE extension docs (Context7 `/bigskysoftware/htmx`) — `hx-ext`, `sse-connect`, `sse-swap` placement rules

### Secondary (MEDIUM confidence)
- Context7 `/sysid/sse-starlette` — asyncio.Queue per session broadcast pattern (adapted for single-session use)
- Alpine.js docs (Context7 `/alpinejs/alpine`) — `x-data` placement, `$store` for cross-component state

### Research from prior phases (HIGH confidence)
- `.planning/research/PITFALLS.md` — SSE disconnect, HTMX attribute placement, Alpine/HTMX swap conflict, event name case sensitivity
- `.planning/research/STACK.md` — `fastapi.sse` native SSE confirmed, HTMX 2.2.4 SSE extension version

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries confirmed installed and importable
- Architecture (POST+SSE decoupling): HIGH — asyncio.Queue pattern from official sse-starlette docs, matches CONTEXT.md decision
- LangGraph astream_events mapping: HIGH — direct port from working `app.py`
- HTMX SSE wiring: HIGH — official HTMX docs + PITFALLS.md
- Alpine.js integration: HIGH — established swap rule, confirmed in prior research
- Interrupt/resume: HIGH — verified in `cli.py` + LangGraph docs
- File upload: HIGH — existing `python-multipart` + FastAPI File docs

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable stack, 30-day window)
