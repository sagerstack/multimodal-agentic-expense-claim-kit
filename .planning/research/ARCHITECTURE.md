# Architecture Research

**Domain:** FastAPI + Jinja2 + HTMX replacing Chainlit as the UI layer for a LangGraph multi-agent system
**Researched:** 2026-03-30
**Confidence:** HIGH (FastAPI/Starlette/HTMX patterns from official docs; LangGraph integration verified from working code)

---

## Context: What Changes, What Does Not

This is a UI-layer replacement milestone. The LangGraph backend, MCP servers, PostgreSQL, and Qdrant are unchanged. Only the app service in docker-compose is being replaced.

**Unchanged:**
- `src/agentic_claims/core/graph.py` — StateGraph, `getCompiledGraph()`, `evaluatorGate`
- `src/agentic_claims/core/state.py` — `ClaimState` TypedDict
- `src/agentic_claims/core/imageStore.py` — In-memory `claimId -> base64`
- All 4 MCP servers and their Docker services
- `AsyncPostgresSaver` checkpointer pattern
- `astream_events(version="v2")` streaming interface
- All agent nodes (intake, compliance, fraud, advisor)

**Replaced:**
- `src/agentic_claims/app.py` (Chainlit handlers) → new `src/agentic_claims/web/` package
- `Dockerfile` CMD → `uvicorn` instead of `chainlit run`
- `chainlit` Python dependency → `fastapi`, `uvicorn`, `jinja2`, `python-multipart`
- `.chainlit/` config directory → `templates/`, `static/` directories

**Added:**
- 4 Jinja2 templates (one per Stitch design)
- SSE endpoint bridging `astream_events()` to `text/event-stream`
- Starlette `SessionMiddleware` for `thread_id` / `claim_id` per browser session
- REST endpoints for dashboard, audit log, claim review data
- `static/` for any local assets (Tailwind stays on CDN)

---

## Standard Architecture

### System Overview

```
Browser (Tailwind CDN + HTMX + Alpine.js)
│
│  Page navigation        → GET /  /dashboard  /audit  /review/{id}
│  Chat message           → POST /chat/message  (multipart/form-data)
│  SSE stream connection  → GET  /chat/stream
│  Dashboard data         → GET  /api/claims
│  Audit log data         → GET  /api/audit
│  Claim review data      → GET  /api/claims/{id}
│
▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI app  (replaces chainlit run)                               │
│                                                                     │
│  SessionMiddleware (Starlette)                                      │
│    request.session["thread_id"]  — per browser tab                 │
│    request.session["claim_id"]   — per submission                  │
│                                                                     │
│  Lifespan                                                           │
│    compiled_graph = getCompiledGraph()   ← one instance, shared    │
│    checkpointer_ctx  (async context manager, never closed)         │
│                                                                     │
│  Routers                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  pages/      │  │  chat/       │  │  api/                    │  │
│  │  router.py   │  │  router.py   │  │  router.py               │  │
│  │              │  │              │  │                          │  │
│  │  GET /       │  │  POST        │  │  GET /api/claims         │  │
│  │  GET /dash   │  │  /chat/msg   │  │  GET /api/audit          │  │
│  │  GET /audit  │  │              │  │  GET /api/claims/{id}    │  │
│  │  GET /review │  │  GET         │  │                          │  │
│  │  /{id}       │  │  /chat/      │  │  (serve data for HTMX    │  │
│  │              │  │  stream      │  │   partial swaps on the   │  │
│  │  Returns full│  │  (SSE)       │  │   3 non-chat pages)      │  │
│  │  Jinja2 page │  │              │  │                          │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                                                                     │
│  Jinja2Templates  (templates/)                                      │
│  StaticFiles      (static/)                                         │
└─────────────────────────────────────────────────────────────────────┘
                    │                           │
          ┌─────────┘                           └──────────┐
          ▼                                                ▼
┌──────────────────────┐                    ┌─────────────────────────┐
│  LangGraph Backend   │                    │  PostgreSQL             │
│                      │                    │                         │
│  getCompiledGraph()  │                    │  Claims, Receipts,      │
│  ClaimState          │                    │  AuditLog tables        │
│  astream_events()    │                    │  LangGraph checkpoints  │
│  imageStore          │                    │                         │
└──────────────────────┘                    └─────────────────────────┘
                    │
          ┌─────────┴──────────────────────────────────┐
          ▼           ▼                ▼               ▼
    mcp-rag:8001  mcp-db:8002  mcp-currency:8003  mcp-email:8004
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| `web/main.py` | FastAPI app, lifespan, middleware, router mounting | All routers, templates, static |
| `web/routers/pages.py` | Full-page GET routes returning TemplateResponse | Jinja2Templates |
| `web/routers/chat.py` | POST message handler, GET SSE stream endpoint | LangGraph graph, imageStore, SessionMiddleware |
| `web/routers/api.py` | JSON API for dashboard/audit/review data | PostgreSQL via SQLAlchemy |
| `web/session.py` | Session dependency injection helper | Starlette SessionMiddleware |
| `templates/base.html` | Shared layout: sidebar nav, top nav, head section | All page templates via `{% extends %}` |
| `templates/chat.html` | Chat interface with SSE listener div | base.html |
| `templates/dashboard.html` | Approver dashboard with bento grid | base.html |
| `templates/audit.html` | Audit log with claim detail panel | base.html |
| `templates/review.html` | Claim review/escalation page | base.html |
| `static/` | Local assets only (none required; Tailwind stays CDN) | Jinja2Templates via url_for |

---

## Recommended Project Structure

```
src/agentic_claims/
├── web/                            # NEW — replaces app.py
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, lifespan, middleware, mount routers
│   ├── session.py                  # Dependency: get/create thread_id + claim_id from session
│   ├── dependencies.py             # Shared FastAPI dependencies (graph, templates)
│   └── routers/
│       ├── __init__.py
│       ├── pages.py                # Full-page routes (GET / /dashboard /audit /review/{id})
│       ├── chat.py                 # POST /chat/message, GET /chat/stream (SSE)
│       └── api.py                  # GET /api/claims, /api/audit, /api/claims/{id}
│
├── core/                           # UNCHANGED
│   ├── config.py
│   ├── state.py
│   ├── graph.py
│   └── imageStore.py
│
├── agents/                         # UNCHANGED
│   ├── intake/
│   ├── compliance/
│   ├── fraud/
│   └── advisor/
│
└── infrastructure/                 # UNCHANGED
    ├── database/models.py
    └── openrouter/client.py

templates/                          # NEW — Jinja2 templates (at repo root, not in src)
├── base.html                       # Shared layout: sidebar, topnav, head (Tailwind config inline)
├── chat.html                       # Page 01 — AI chat + receipt upload + SSE streaming
├── dashboard.html                  # Page 04 — Approver dashboard + bento grid
├── audit.html                      # Page 02 — Audit log + claim detail panel
└── review.html                     # Page 03 — Claim review/escalation

static/                             # NEW — local assets (minimal; CDN preferred)
└── (empty or icons/favicons only)

Dockerfile                          # MODIFIED — CMD changed to uvicorn
docker-compose.yml                  # MINIMAL CHANGE — healthcheck URL update only
```

**Rationale for `templates/` at repo root rather than inside `src/`:**
FastAPI's `Jinja2Templates(directory="templates")` resolves relative to the process working directory. The Dockerfile sets `WORKDIR /app` and copies `src/` to `/app/src/`, so `templates/` at the repo root maps to `/app/templates/` in the container without any path gymnastics. This matches the FastAPI official docs pattern.

---

## Architectural Patterns

### Pattern 1: Graph as Application-Level Singleton (Lifespan)

The Chainlit app called `getCompiledGraph()` per chat session, creating a new checkpointer connection pool each time. This does not port to FastAPI cleanly because the checkpointer is a long-lived async context manager.

**Correct approach:** Initialize the compiled graph once at app startup using FastAPI's lifespan pattern and share it via `app.state`.

```python
# web/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from agentic_claims.core.graph import getCompiledGraph

@asynccontextmanager
async def lifespan(app: FastAPI):
    graph, checkpointerCtx = await getCompiledGraph()
    app.state.graph = graph
    app.state.checkpointerCtx = checkpointerCtx
    yield
    # Shutdown: close the checkpointer connection pool
    await checkpointerCtx.__aexit__(None, None, None)

app = FastAPI(lifespan=lifespan)
```

Per-request access via dependency:

```python
# web/dependencies.py
from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

def getGraph(request: Request) -> CompiledStateGraph:
    return request.app.state.graph
```

**Why:** One checkpointer connection pool shared across all sessions is correct. The checkpointer is thread-safe for concurrent `astream_events()` calls because each call is scoped by `thread_id`. Creating one pool per session (Chainlit pattern) would exhaust database connections under load.

### Pattern 2: Session-Based thread_id + claim_id via Starlette SessionMiddleware

Chainlit used `cl.user_session` (per-websocket storage). FastAPI has no equivalent. Use Starlette's built-in `SessionMiddleware` (signed cookie) to persist `thread_id` and `claim_id` per browser session.

```python
# web/main.py
from starlette.middleware.sessions import SessionMiddleware
import secrets

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,  # from env, not hardcoded
    session_cookie="agentic_session",
    max_age=None,  # browser session (tab-lifetime)
    same_site="lax",
    https_only=False,  # True in prod
)
```

```python
# web/session.py
import uuid
from fastapi import Request

def getOrCreateSession(request: Request) -> dict:
    """Return session dict with thread_id and claim_id, creating if absent."""
    session = request.session
    if "thread_id" not in session:
        session["thread_id"] = str(uuid.uuid4())
    if "claim_id" not in session:
        session["claim_id"] = str(uuid.uuid4())
    return {
        "thread_id": session["thread_id"],
        "claim_id": session["claim_id"],
    }
```

**Session cookie contains:** Only the signed session dict (JSON). The actual LangGraph state lives in PostgreSQL (checkpointer), keyed by `thread_id`. The cookie just identifies which thread to resume.

**Important:** The claim_id is mutable. When a claim is submitted (the `claimSubmitted` flag is set), the next chat session should reset claim_id. Add a `POST /chat/reset` endpoint that clears the session and redirects to `/`.

### Pattern 3: LangGraph astream_events() to SSE Endpoint

This is the core replacement for Chainlit's `@cl.on_message` handler. The streaming bridge maps LangGraph's `astream_events(version="v2")` to `text/event-stream` for the browser.

**Architecture:**
1. Browser POSTs message to `POST /chat/message` (with optional image file)
2. FastAPI handler stores image in `imageStore`, constructs `HumanMessage`, stores in a per-session `asyncio.Queue`
3. SSE stream endpoint (`GET /chat/stream`) connects once per chat session, loops on the queue
4. When queue yields a message, the SSE generator runs `graph.astream_events()` and forwards events

```python
# web/routers/chat.py
import asyncio
import json
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import HumanMessage
from agentic_claims.core.imageStore import storeImage

router = APIRouter(prefix="/chat")

# Per-session message queues: thread_id -> asyncio.Queue
_messageQueues: dict[str, asyncio.Queue] = {}

def getQueue(threadId: str) -> asyncio.Queue:
    if threadId not in _messageQueues:
        _messageQueues[threadId] = asyncio.Queue()
    return _messageQueues[threadId]


@router.post("/message")
async def postMessage(
    request: Request,
    message: str = Form(""),
    image: UploadFile | None = File(None),
):
    """Accept user message + optional image. Enqueues for SSE stream."""
    sessionData = getOrCreateSession(request)
    threadId = sessionData["thread_id"]
    claimId = sessionData["claim_id"]

    imageB64 = None
    if image and image.content_type.startswith("image/"):
        imageBytes = await image.read()
        imageB64 = base64.b64encode(imageBytes).decode("utf-8")
        storeImage(claimId, imageB64)

    if imageB64:
        humanMsg = HumanMessage(
            content=f"I've uploaded a receipt image for claim {claimId}. "
                    "Please process it using extractReceiptFields."
        )
    else:
        humanMsg = HumanMessage(content=message)

    queue = getQueue(threadId)
    await queue.put({"msg": humanMsg, "claimId": claimId})

    # Return HTMX fragment: render the user message bubble immediately
    return templates.TemplateResponse(
        request=request,
        name="partials/user_message.html",
        context={"content": message or "[receipt uploaded]"},
    )


@router.get("/stream", response_class=EventSourceResponse)
async def streamEvents(request: Request):
    """SSE endpoint: bridges LangGraph astream_events to text/event-stream."""
    sessionData = getOrCreateSession(request)
    threadId = sessionData["thread_id"]
    graph = request.app.state.graph
    queue = getQueue(threadId)

    async def eventGenerator():
        while True:
            if await request.is_disconnected():
                break

            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keep-alive ping
                yield ServerSentEvent(comment="ping")
                continue

            humanMsg = item["msg"]
            claimId = item["claimId"]

            graphInput = {
                "claimId": claimId,
                "status": "draft",
                "messages": [humanMsg],
            }
            config = {"configurable": {"thread_id": threadId}}

            # Signal thinking start
            yield ServerSentEvent(
                data=json.dumps({"type": "thinking_start"}),
                event="status",
            )

            toolCount = 0
            finalResponse = None
            tokenBuffer = ""

            async for event in graph.astream_events(graphInput, config=config, version="v2"):
                eventKind = event.get("event")

                if eventKind == "on_tool_start":
                    toolName = event.get("name", "unknown")
                    yield ServerSentEvent(
                        data=json.dumps({"type": "tool_start", "tool": toolName}),
                        event="status",
                    )

                elif eventKind == "on_tool_end":
                    toolCount += 1
                    yield ServerSentEvent(
                        data=json.dumps({"type": "tool_end", "tool": event.get("name")}),
                        event="status",
                    )

                elif eventKind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        tokenBuffer += chunk.content

                elif eventKind == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    hasToolCalls = (
                        output and hasattr(output, "tool_calls") and output.tool_calls
                    )
                    if not hasToolCalls and tokenBuffer.strip():
                        finalResponse = tokenBuffer.strip()
                    tokenBuffer = ""

            # Send final AI message as HTML fragment
            if finalResponse:
                yield ServerSentEvent(
                    data=finalResponse,
                    event="ai_message",
                )

            yield ServerSentEvent(
                data=json.dumps({"type": "done", "toolCount": toolCount}),
                event="status",
            )

    return EventSourceResponse(eventGenerator())
```

**Why queue-based rather than direct streaming:** The POST and SSE GET are separate HTTP connections. The queue decouples them. This is the correct pattern for SSE + form submission with HTMX.

### Pattern 4: Jinja2 Template Inheritance from Stitch HTML

All 4 Stitch HTML files share identical structure: the same `<head>` with Tailwind CDN and config, same top nav, same side nav. Extract these into `base.html` blocks.

**Extraction strategy:**

```
Stitch file           → Jinja2 mapping
─────────────────────────────────────────────────────
<head> section        → base.html entirely (same across all 4)
<header> top nav      → base.html {% block topnav %}
<aside> side nav      → base.html {% block sidenav %}
                        with {% if active_page == 'chat' %}...{% endif %}
                        for the active state highlight (rounded-r-full class)
<main> content        → child template {% block content %}
Page-specific <style> → child template {% block extra_styles %}
```

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html class="dark" lang="en">
<head>
  <meta charset="utf-8"/>
  <meta content="width=device-width, initial-scale=1.0" name="viewport"/>
  <title>{% block title %}Cognitive Atelier{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://unpkg.com/htmx-ext-sse@2.2.2/sse.js"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script id="tailwind-config">
    tailwind.config = { darkMode: "class", theme: { extend: {
      /* paste the shared color/font config here once */
      colors: { /* ...identical across all 4 Stitch files... */ },
      fontFamily: { /* ... */ },
      borderRadius: { /* ... */ }
    }}}
  </script>
  <style>
    .material-symbols-outlined { font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; }
    .hide-scrollbar::-webkit-scrollbar { display: none; }
    .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
  </style>
  {% block extra_styles %}{% endblock %}
</head>
<body class="bg-surface text-on-surface font-body selection:bg-secondary/30">

<!-- Top Nav (identical across all 4 Stitch files) -->
<header class="fixed top-0 w-full z-50 ...">
  ...
</header>

<!-- Side Nav with active state driven by template variable -->
<aside class="fixed left-0 top-0 h-full flex flex-col py-8 bg-[#091328] w-64 hidden md:flex z-40">
  <nav class="flex-1 space-y-1">
    <a class="flex items-center gap-3 {% if active_page == 'chat' %}bg-[#1f2b49] text-[#62fae3] rounded-r-full shadow-[0_0_15px_rgba(98,250,227,0.2)]{% else %}text-[#dee5ff] opacity-50 hover:bg-[#192540] hover:opacity-100{% endif %} ..."
       href="/">
      <span class="material-symbols-outlined">chat_spark</span> Chat AI
    </a>
    <a class="flex items-center gap-3 {% if active_page == 'dashboard' %}bg-[#1f2b49] text-[#62fae3] rounded-r-full...{% else %}text-[#dee5ff] opacity-50...{% endif %} ..."
       href="/dashboard">
      <span class="material-symbols-outlined">insert_chart</span> Analytics
    </a>
    <!-- repeat for audit, review -->
  </nav>
</aside>

<!-- Page content -->
<main class="md:ml-64 pt-16">
  {% block content %}{% endblock %}
</main>

</body>
</html>
```

```html
<!-- templates/chat.html -->
{% extends "base.html" %}
{% block title %}Chat AI | Cognitive Atelier{% endblock %}
{% block extra_styles %}
  <style>
    .intelligence-pulse { /* ... from Stitch file ... */ }
  </style>
{% endblock %}
{% block content %}
  <!-- Chat history container -->
  <div id="chat-messages" class="flex-1 overflow-y-auto p-6 space-y-8 hide-scrollbar">
    <!-- Welcome message rendered server-side -->
    {% include "partials/ai_message.html" with context %}
  </div>

  <!-- SSE listener: connects on page load, listens for ai_message and status events -->
  <div hx-ext="sse"
       sse-connect="/chat/stream"
       sse-swap="ai_message"
       hx-target="#chat-messages"
       hx-swap="beforeend scroll:#chat-messages:bottom">
  </div>

  <!-- Message input form -->
  <form hx-post="/chat/message"
        hx-target="#chat-messages"
        hx-swap="beforeend scroll:#chat-messages:bottom"
        hx-encoding="multipart/form-data"
        hx-on::before-request="this.reset()"
        class="...">
    <!-- file upload + text input + submit -->
  </form>
{% endblock %}
```

**Key insight on sse-swap target:** The `sse-swap="ai_message"` attribute listens for `event: ai_message` events and swaps the data into `#chat-messages` using `beforeend`. The `hx-target` and `hx-swap` on the SSE div control where the content lands. This requires HTMX 2.x with the `htmx-ext-sse` extension (separate script tag).

### Pattern 5: HTMX Partial Responses for Non-Chat Pages

The dashboard, audit, and review pages contain data-driven sections (claim lists, stat cards, etc.) that need real data, not Stitch's hardcoded HTML. Use HTMX `hx-get` with `hx-trigger="load"` to fetch data after the page loads, keeping initial page render fast.

```html
<!-- templates/dashboard.html — bento grid stats section -->
<section id="stats-grid" class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12"
         hx-get="/api/dashboard/stats"
         hx-trigger="load"
         hx-swap="outerHTML">
  <!-- Skeleton placeholder while loading -->
  <div class="animate-pulse bg-surface-container-low rounded-3xl h-48"></div>
  <div class="animate-pulse bg-surface-container-low rounded-3xl h-48"></div>
  <div class="animate-pulse bg-surface-container-low rounded-3xl h-48"></div>
</section>
```

The `/api/dashboard/stats` endpoint returns an HTML fragment (not JSON), rendered from a partial template.

---

## Data Flow

### Chat Turn: User Sends Message with Receipt Image

```
1. User fills form (text + image file)
   ↓
2. HTMX posts multipart/form-data to POST /chat/message
   ↓
3. FastAPI handler:
   a. Reads image bytes → base64 encode → storeImage(claimId, b64)
   b. Constructs HumanMessage referencing claimId
   c. Enqueues into asyncio.Queue[threadId]
   d. Returns HTML fragment (user message bubble) → HTMX appends to #chat-messages
   ↓
4. SSE stream (already connected via sse-connect="/chat/stream"):
   a. Dequeues item from asyncio.Queue
   b. Calls graph.astream_events(graphInput, config={"configurable": {"thread_id": threadId}})
   c. For each on_tool_start → yields ServerSentEvent(event="status", data={"type":"tool_start"...})
   d. For each on_chat_model_stream → buffers tokens
   e. For on_chat_model_end (no tool calls) → yields ServerSentEvent(event="ai_message", data=html_fragment)
   ↓
5. HTMX SSE extension receives event="ai_message":
   sse-swap="ai_message" fires → appends AI message bubble to #chat-messages
   ↓
6. Alpine.js handles status events (tool indicators, thinking spinner) via:
   @htmx:sse-message.window="updateThinkingState($event.detail)"
```

### Chat Turn: Interrupt/Resume (Human-in-the-Loop)

The existing `askHuman` tool triggers a LangGraph `interrupt()`. The astream_events stream pauses with an `__interrupt__` sentinel in the graph state. The FastAPI layer handles this identically to Chainlit's interrupt handling:

```
1. SSE stream detects interrupt during astream_events traversal
   (no on_chat_model_end with final content; graph state has __interrupt__)
   ↓
2. Emit ServerSentEvent(event="ai_message", data=<clarification question html>)
   Emit ServerSentEvent(event="status", data={"type":"awaiting_input"})
   ↓
3. Browser: HTMX renders clarification question, Alpine.js marks form as "resume mode"
   ↓
4. User types answer → HTMX posts to POST /chat/message
   ↓
5. FastAPI handler: detects "awaiting_input" flag in session → wraps message in
   Command(resume=userAnswer) instead of HumanMessage → enqueues
   ↓
6. SSE stream: graph.astream_events(Command(resume=...), config) → continues execution
```

**Session flag for interrupt state:**
```python
request.session["awaiting_interrupt"] = True  # set when interrupt detected
# Cleared after resume
```

### Page Navigation Flow (Non-Chat Pages)

```
User clicks "Approvals" in sidebar
   ↓
Browser GET /dashboard
   ↓
FastAPI pages.py returns TemplateResponse("dashboard.html", {"active_page": "dashboard", ...})
   ↓
Browser renders full page with sidebar (active item highlighted), skeleton stats
   ↓
HTMX hx-trigger="load" fires → GET /api/dashboard/stats
   ↓
FastAPI api.py queries PostgreSQL → returns HTML fragment via TemplateResponse("partials/stats_grid.html")
   ↓
HTMX swaps skeleton → real data
```

---

## Integration Points

### Existing Backend Integration

| Integration Point | Chainlit Pattern | FastAPI Pattern |
|-------------------|-----------------|-----------------|
| Graph initialization | `getCompiledGraph()` per session in `@on_chat_start` | Once in lifespan → `app.state.graph` |
| Session identity | `cl.user_session.set("thread_id", ...)` | `request.session["thread_id"]` via SessionMiddleware |
| Streaming | `async for event in graph.astream_events(...)` in `@on_message` | Same call, inside SSE generator function |
| Image storage | `storeImage(claimId, b64)` in `@on_message` | Same call, in `POST /chat/message` handler |
| Tool indicators | `step.name = TOOL_LABELS[toolName]; await step.update()` | `ServerSentEvent(event="status", ...)` → Alpine.js updates DOM |
| Thinking display | `cl.Step(...)` context manager | Alpine.js reactive state + status SSE events |
| Final response | `await cl.Message(content=finalResponse).send()` | `ServerSentEvent(event="ai_message", data=html)` → HTMX swap |

### New API Endpoints (Non-Chat Pages)

| Endpoint | Method | Returns | Template Used |
|----------|--------|---------|---------------|
| `/` | GET | Full page | `chat.html` |
| `/dashboard` | GET | Full page | `dashboard.html` |
| `/audit` | GET | Full page | `audit.html` |
| `/review/{claim_id}` | GET | Full page | `review.html` |
| `/chat/message` | POST | HTML fragment | `partials/user_message.html` |
| `/chat/stream` | GET | text/event-stream | (generator, no template) |
| `/chat/reset` | POST | redirect to `/` | (resets session) |
| `/api/dashboard/stats` | GET | HTML fragment | `partials/stats_grid.html` |
| `/api/claims` | GET | HTML fragment | `partials/claims_list.html` |
| `/api/claims/{id}` | GET | HTML fragment | `partials/claim_detail.html` |
| `/api/audit` | GET | HTML fragment | `partials/audit_log.html` |

**Critical design decision:** All API endpoints that serve UI data return HTML fragments (TemplateResponse with partial templates), not JSON. This is the HTMX-native pattern — the server sends markup, not data. Keeps JavaScript to zero for DOM manipulation.

### External Services (Unchanged)

| Service | Integration | Notes |
|---------|-------------|-------|
| mcp-rag:8001 | LangGraph tools via mcpClient.py | No change |
| mcp-db:8002 | LangGraph tools + direct SQLAlchemy queries for review/audit pages | New: direct DB queries for non-agent pages |
| mcp-currency:8003 | LangGraph tools | No change |
| mcp-email:8004 | LangGraph tools | No change |
| PostgreSQL | AsyncPostgresSaver (checkpointer) + SQLAlchemy (app queries) | Both pools co-exist |

### Docker Compose Changes

Minimal changes to `docker-compose.yml`:

1. **`app` service CMD:** Dockerfile CMD changes from `chainlit run src/agentic_claims/app.py ...` to `uvicorn agentic_claims.web.main:app --host 0.0.0.0 --port 8000 --reload` (dev) or `--workers 1` (prod, single worker required because of in-process `asyncio.Queue` and `imageStore`).

2. **Healthcheck:** `curl -f http://localhost:8000/` still works (FastAPI root route returns 200).

3. **No new services required.** All 4 MCP servers unchanged. PostgreSQL and Qdrant unchanged.

4. **`SESSION_SECRET_KEY`** environment variable added to `app` service env and `.env.local`.

```yaml
# docker-compose.yml — app service only changes
app:
  # ... same build, ports, depends_on ...
  environment:
    POSTGRES_HOST: postgres
    QDRANT_HOST: qdrant
    SESSION_SECRET_KEY: ${SESSION_SECRET_KEY}  # ADD THIS
```

---

## Alpine.js Integration Pattern

Alpine.js handles client-side state that cannot be done with pure HTMX:

1. **Upload progress indicator** — show spinner during file read before POST
2. **Thinking panel toggle** — expand/collapse tool call details
3. **Status event handling** — receive `event: status` SSE events and update UI state

```html
<!-- In chat.html: Alpine component wrapping the chat UI -->
<section x-data="{
  thinking: false,
  currentTool: '',
  toolCount: 0,
  awaitingInput: false
}" x-on:htmx:sse-message.window="handleStatusEvent($event)">

  <!-- Thinking indicator, shown while graph is running -->
  <div x-show="thinking" class="flex items-center gap-2">
    <div class="intelligence-pulse"></div>
    <span x-text="currentTool || 'Analyzing...'" class="text-xs text-secondary"></span>
  </div>

  <!-- Chat messages (HTMX manages content) -->
  <div id="chat-messages" ...></div>

  <!-- SSE listener div -->
  <div hx-ext="sse" sse-connect="/chat/stream"
       sse-swap="ai_message"
       hx-target="#chat-messages"
       hx-swap="beforeend"
       x-on:sse:status="handleStatus(JSON.parse($event.detail.data))">
  </div>

</section>

<script>
function handleStatus(payload) {
  if (payload.type === 'thinking_start') { this.thinking = true; }
  if (payload.type === 'tool_start') { this.currentTool = payload.tool; }
  if (payload.type === 'done') { this.thinking = false; this.toolCount = payload.toolCount; }
}
</script>
```

**Important:** When HTMX swaps new content via SSE, Alpine.js automatically initializes `x-data` on newly inserted elements because HTMX dispatches `htmx:afterSwap` and Alpine.js v3 observes DOM mutations. No manual re-initialization needed.

---

## Suggested Build Order

Dependencies determine this order. Each step is buildable and testable in isolation.

### Step 1 — FastAPI App Skeleton (no templates yet)
**Deliverables:** `web/main.py`, `web/dependencies.py`, `web/session.py`, updated Dockerfile, `SESSION_SECRET_KEY` in env
**Test:** `docker compose up app` — container starts, `GET /` returns 404 (no routes yet), graph initializes in lifespan log

**Why first:** Validates that `getCompiledGraph()` works in a lifespan context, that the checkpointer connection pool stays alive, and that the Docker image builds. Catches import errors before any UI work.

### Step 2 — Base Template + Static Infrastructure
**Deliverables:** `templates/base.html` (Tailwind config, nav, head), `static/` directory, `pages.py` router with GET routes returning TemplateResponse
**Test:** `GET /` renders sidebar + topnav, correct page highlighted per `active_page`

**Why second:** Base template is the foundation for all 4 pages. Extracting shared layout first prevents duplicating Tailwind config 4 times.

### Step 3 — Chat Page + SSE Streaming
**Deliverables:** `templates/chat.html`, `routers/chat.py` (POST /chat/message + GET /chat/stream), `partials/user_message.html`, `partials/ai_message.html`
**Test:** Upload receipt → user bubble appears → AI response streams in → thinking indicator shows tools

**Why third:** This is the highest-risk integration. Validates the SSE bridge, queue pattern, session management, and image upload all working together. Catching issues here before building the other pages is critical.

### Step 4 — Dashboard Page
**Deliverables:** `templates/dashboard.html`, `routers/api.py` with `/api/dashboard/stats`, `partials/stats_grid.html`, `partials/claims_list.html`
**Test:** `GET /dashboard` renders with skeleton → real data loads via HTMX

**Why fourth:** Lowest risk (no streaming, no image handling). Validates the HTMX lazy-load pattern with real PostgreSQL data.

### Step 5 — Audit Log Page
**Deliverables:** `templates/audit.html`, `/api/audit` endpoint, `/api/claims/{id}` endpoint for detail panel
**Test:** `GET /audit` renders claim list → click claim → detail panel swaps in

**Why fifth:** The audit log has a list-detail split-panel pattern (from Stitch 02). The detail panel swap is an HTMX `hx-get + hx-target` pattern, slightly more complex than the dashboard.

### Step 6 — Review Page + Interrupt Resume
**Deliverables:** `templates/review.html`, interrupt detection in SSE generator, `awaiting_interrupt` session flag, resume via `Command(resume=...)`
**Test:** Trigger an interrupt from intake agent → clarification question appears → user answers → graph resumes

**Why last:** The interrupt/resume flow requires the full SSE pipeline (Step 3) and session state to be working. Most complex integration.

---

## Anti-Patterns

### Anti-Pattern 1: One Graph Instance Per Request

**What people do:** Call `getCompiledGraph()` inside the SSE endpoint handler, creating a new checkpointer pool per streaming call.

**Why it's wrong:** The `AsyncPostgresSaver.from_conn_string()` context manager opens a new psycopg connection pool. Calling this per request exhausts Postgres connections quickly and adds ~500ms latency per call.

**Do this instead:** Lifespan pattern. One graph, one checkpointer pool, shared via `app.state.graph`.

### Anti-Pattern 2: Returning JSON from HTMX-Targeted Endpoints

**What people do:** Return `{"claims": [...]}` from `/api/claims` and handle it with Alpine.js or JavaScript.

**Why it's wrong:** Contradicts the HTMX philosophy. Requires JavaScript for DOM manipulation. Increases cognitive load. Alpine.js becomes a mini-framework with template strings.

**Do this instead:** Return HTML fragments. The FastAPI endpoint calls `TemplateResponse("partials/claims_list.html", {"claims": claims_data})`. HTMX swaps it in. Zero JavaScript for data rendering.

### Anti-Pattern 3: Streaming Tokens to the DOM One at a Time

**What people do:** Forward every `on_chat_model_stream` token as a separate SSE event, updating the DOM with each token.

**Why it's wrong:** Causes hundreds of HTMX swaps per response. DOM thrashing, visible flicker, poor performance.

**Do this instead:** Buffer tokens until `on_chat_model_end` (final response identified), then send one `event: ai_message` with the complete AI message rendered as an HTML fragment. Use Alpine.js typing animation locally if streaming effect is needed.

**Exception:** If a streaming typing effect is required for UX, buffer into a single Alpine.js reactive variable and let Alpine update the DOM smoothly — do not use HTMX for token-by-token swaps.

### Anti-Pattern 4: Multiple Workers with In-Process State

**What people do:** `uvicorn ... --workers 4` for performance.

**Why it's wrong:** `_messageQueues` (asyncio.Queue dict) and `imageStore` (module-level dict) are in-process memory. Multiple workers = multiple independent processes = queues and image store are not shared. A POST to worker 1 puts into worker 1's queue; the SSE stream on worker 2 never sees it.

**Do this instead:** Run with `--workers 1`. For this course project, one async worker handles concurrent SSE streams efficiently (async I/O, not blocking). If scaling is needed post-demo, replace `_messageQueues` with Redis pub/sub and `imageStore` with Redis or S3.

### Anti-Pattern 5: Mounting HTMX and Alpine.js via npm Build

**What people do:** Add webpack/vite build step for HTMX and Alpine.js.

**Why it's wrong:** Introduces a build pipeline that does not exist in this project. Over-engineering for a course project.

**Do this instead:** CDN for both. The Stitch HTML files already use Tailwind CDN. Adding `<script src="https://unpkg.com/htmx.org@2.0.4">` and `<script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js">` in `base.html` is sufficient. Pin exact versions to avoid surprises.

---

## Scaling Considerations

This is a course project. Scaling notes are for awareness, not action.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-5 users (demo) | Single `--workers 1` uvicorn. In-memory queue and imageStore. All fine. |
| 10-50 users | Add Redis for `_messageQueues` and `imageStore`. Multiple workers become possible. |
| 50+ users | Replace AsyncPostgresSaver with LangGraph Cloud or a proper connection pool manager. Add CDN for static assets. |

---

## Sources

**Official Documentation (HIGH confidence):**
- [FastAPI Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — `EventSourceResponse`, `ServerSentEvent`, native SSE support added in FastAPI 0.135.0
- [FastAPI Templates](https://fastapi.tiangolo.com/advanced/templates/) — `Jinja2Templates`, `TemplateResponse`, `StaticFiles` pattern
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — `@asynccontextmanager`, `app.state`, startup/shutdown
- [Starlette SessionMiddleware](https://www.starlette.dev/middleware/) — `request.session`, signed cookie, `HttpOnly` flag, parameters
- [HTMX SSE Extension](https://htmx.org/extensions/sse/) — `hx-ext="sse"`, `sse-connect`, `sse-swap`, HTMX 2.x

**Community (MEDIUM confidence, verified against official patterns):**
- [Agentic Chatbot with HTMX (Dec 2025)](https://medium.com/data-science-collective/javascript-fatigued-build-an-agentic-chatbot-with-htmx-503569adf2f9) — queue-based POST/SSE decoupling pattern, message append pattern
- [Streaming AI Agent with FastAPI + LangGraph (2025-26)](https://dev.to/kasi_viswanath/streaming-ai-agent-with-fastapi-langgraph-2025-26-guide-1nkn) — `astream_events()` to SSE bridge, nginx headers, `get_stream_writer()`

**Codebase (HIGH confidence — directly verified):**
- `src/agentic_claims/app.py` — Chainlit handler logic being ported; streaming event handling patterns
- `src/agentic_claims/core/graph.py` — `getCompiledGraph()`, checkpointer context manager lifecycle
- `docker-compose.yml` — service topology, port assignments, health check patterns

---

*Architecture research for: FastAPI + Jinja2 + HTMX UI layer replacing Chainlit*
*Researched: 2026-03-30*
