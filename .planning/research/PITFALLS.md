# Pitfalls Research

**Domain:** Chainlit → FastAPI + HTMX + Jinja2 Migration (AI Chat Interface)
**Researched:** 2026-03-30
**Confidence:** HIGH for SSE/HTMX mechanics; MEDIUM for Playwright/SSE test patterns

---

## Critical Pitfalls

These cause rewrites or silent data loss if ignored.

---

### Pitfall 1: Checkpointer Lifecycle Owned by Request Instead of App

**What goes wrong:**
The Chainlit `app.py` creates `AsyncPostgresSaver` once per chat session in `on_chat_start` and destroys it in `on_chat_end`. Migrating this pattern naively to FastAPI means opening a new Postgres connection pool per HTTP request. The graph holds a reference to a connection that was closed at the end of the request handler — producing `psycopg.OperationalError: the connection is closed` on the next graph invocation.

**Why it happens:**
Scripts own their full lifecycle (open → use → close). Servers must keep resources alive across multiple requests and close only on shutdown. Chainlit hid this distinction by binding the checkpointer to the WebSocket session lifecycle. FastAPI has no equivalent automatic lifecycle anchor per session — you have to use `lifespan`.

**How to avoid:**
Move checkpointer initialization into FastAPI's `lifespan` context manager. Enter the `AsyncPostgresSaver` async context manager once at startup, store the compiled graph in `app.state`, and let every request reuse it.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: enter once, persist for server lifetime
    checkpointerCtx = AsyncPostgresSaver.from_conn_string(settings.postgres_dsn)
    checkpointer = await checkpointerCtx.__aenter__()
    await checkpointer.setup()
    graph = buildGraph().compile(checkpointer=checkpointer)
    app.state.graph = graph
    app.state.checkpointer_ctx = checkpointerCtx
    yield
    # Shutdown: close once
    await checkpointerCtx.__aexit__(None, None, None)

app = FastAPI(lifespan=lifespan)
```

Also requires `autocommit=True` and `row_factory=dict_row` on the underlying psycopg connection.

**Warning signs:**
- `psycopg.OperationalError: the connection is closed` on second message in a conversation
- `AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'get_next_version'` — means the context manager was stored without being entered

**Phase to address:**
Phase 1 (FastAPI Scaffold) — establish this before writing any route that touches the graph.

---

### Pitfall 2: SSE Generator Not Cancelled on Client Disconnect

**What goes wrong:**
When a user closes the browser tab mid-stream, the SSE generator keeps running: `astream_events()` continues invoking the LLM, writing to the database, and burning through OpenRouter rate-limit quota. Over time this creates memory leaks (abandoned task references), database locks from incomplete transactions, and cascading resource exhaustion.

**Why it happens:**
Python async generators do not automatically cancel when the HTTP connection drops. FastAPI's `EventSourceResponse` (from `sse-starlette`) sends responses but does not forcibly cancel the upstream generator. The generator only stops if either the loop ends naturally or `asyncio.CancelledError` propagates into it — which requires explicit disconnect detection.

**How to avoid:**
Wrap the SSE endpoint in a disconnect-aware context that monitors `request.receive()` for the `http.disconnect` ASGI message and cancels the generator scope:

```python
import anyio
from fastapi import Request
from fastapi.responses import StreamingResponse

async def generate_with_cancel(request: Request, graph, input, config):
    async def _stream():
        async for event in graph.astream_events(input, config=config, version="v2"):
            if await request.is_disconnected():
                break
            yield format_sse(event)

    return StreamingResponse(_stream(), media_type="text/event-stream")
```

For LangGraph-intensive workloads, use `anyio.create_task_group()` with a watcher task that cancels the scope when disconnect is detected. Always re-raise `asyncio.CancelledError` in cleanup blocks — swallowing it prevents proper task cancellation.

**Warning signs:**
- OpenRouter rate limit errors earlier than expected in a session
- Postgres connections accumulating without closing under load tests
- Memory usage growing linearly with each closed browser tab

**Phase to address:**
Phase 2 (SSE Streaming) — implement disconnect handling from day one, not as a retrofit.

---

### Pitfall 3: HTMX SSE Extension Attribute Placement Bug

**What goes wrong:**
The SSE connection never opens, or `sse-swap` silently drops events. The thinking panel never renders. No JavaScript errors appear in the console.

**Why it happens:**
The HTMX SSE extension has a hard constraint: `hx-ext="sse"` and `sse-connect="<url>"` **must be on the same element**. Swap listeners (`sse-swap`) must be that same element or its direct children. Developers commonly put `hx-ext="sse"` on `<body>` and `sse-connect` on an inner container, following the pattern used by other HTMX extensions — but this breaks SSE specifically.

The correct structure:
```html
<!-- WRONG: hx-ext and sse-connect on different elements -->
<body hx-ext="sse">
  <div sse-connect="/stream/123">  <!-- never connects -->
    <div sse-swap="token"></div>
  </div>
</body>

<!-- CORRECT: same element -->
<div hx-ext="sse" sse-connect="/stream/123">
  <div sse-swap="token" hx-swap="beforeend"></div>
  <div sse-swap="thinking" hx-swap="innerHTML"></div>
</div>
```

**How to avoid:**
Always co-locate `hx-ext="sse"` and `sse-connect` on the same element. Use named events (`event:` field in SSE payload) for every distinct stream type — unnamed events default to `"message"` and require `sse-swap="message"` to catch. Name mismatches drop events silently with zero console output.

**Warning signs:**
- SSE endpoint is called (check Network tab) but DOM never updates
- No `EventSource` visible in browser DevTools Network panel
- Thinking panel stays empty while console shows no errors

**Phase to address:**
Phase 2 (SSE Streaming) — write a smoke test verifying DOM update on first token before building the full thinking panel.

---

### Pitfall 4: Interrupt/Resume State Lost Between SSE Requests

**What goes wrong:**
The human-in-the-loop flow (Chainlit's `askHuman` → interrupt → resume) breaks because the `awaiting_clarification` flag is stored in the Chainlit `user_session`, not in the LangGraph checkpoint. When migrating to FastAPI with stateless SSE requests, each POST message arrives as an independent request with no session memory. The app sends a `Command(resume=...)` when it should start fresh, or starts fresh when it should resume.

**Why it happens:**
Chainlit's `user_session` is a server-side in-memory dict tied to the WebSocket connection. FastAPI has no equivalent unless you explicitly build one. The migration must replicate the `awaiting_clarification` flag using either:
1. A server-side session store (dict keyed by `thread_id`)
2. A client-side flag passed back in each request payload
3. The LangGraph checkpoint state itself (inspect `graph.aget_state()` for pending interrupts)

The safest approach is option 3: after each graph invocation, check if `state.tasks` contains pending interrupts. If yes, the next request must use `Command(resume=...)`. This is self-contained — no extra session store needed.

**How to avoid:**
```python
# After streaming completes, check for pending interrupt
state = await graph.aget_state(config={"configurable": {"thread_id": thread_id}})
is_interrupted = bool(state.tasks)

# On next message arrival:
if is_interrupted:
    graph_input = Command(resume=user_message)
else:
    graph_input = {"messages": [HumanMessage(content=user_message)], ...}
```

Pass `thread_id` as a query param or header on every SSE request. Store it client-side in a cookie or `<meta>` tag set on page load.

**Warning signs:**
- "I've already processed that receipt" when user submits a second time (resume sent as new message)
- Clarification question asked but app proceeds without waiting for answer
- `GraphInterrupt` exception surfacing in logs on every user message

**Phase to address:**
Phase 3 (Human-in-the-Loop) — design the interrupt detection pattern before implementing the clarification flow.

---

### Pitfall 5: Chainlit's `cl.Step` Thinking Panel Has No Direct HTMX Equivalent

**What goes wrong:**
The progressive thinking panel — name updates in real-time (`"Analyzing..."` → `"Checking policies..."` → `"Thought for 8s · 3 tools"`), collapsible/expandable, contains markdown-rendered tool summaries — is a first-class Chainlit widget. Migrating this to HTMX requires reimplementing the entire behavior from scratch. Teams underestimate this and ship a plain text log instead, losing the designed UX entirely.

**Why it happens:**
Chainlit's `cl.Step` handles: (1) immediate display with spinner, (2) real-time name mutation via `step.update()`, (3) final content render with markdown, (4) collapsible DOM structure. HTMX's SSE extension does DOM swaps — it does not have a concept of mutating an existing element's attribute while also appending to its children. You need two separate SSE event types: one for name updates (`hx-swap="innerHTML"` on the step header) and one for appending content (`hx-swap="beforeend"` on the step body).

**How to avoid:**
Design the SSE event taxonomy to match the UI requirements before writing the backend stream. Minimum required events:

| SSE event name | Payload | HTMX action |
|----------------|---------|-------------|
| `thinking_start` | `<div id="step-panel">...</div>` | `innerHTML` swap creates panel |
| `step_name` | `<span id="step-name">Checking policies...</span>` | `outerHTML` swap updates name |
| `step_content` | `<p>Found 3 policy clauses</p>` | `beforeend` appends to body |
| `thinking_done` | `<span id="step-name">Thought for 8s · 3 tools</span>` | `outerHTML` finalizes name |
| `token` | `<span>word</span>` | `beforeend` appends to response area |
| `done` | sentinel | closes connection client-side via JS |

Use Alpine.js `x-show` for the collapse/expand toggle on the panel.

**Warning signs:**
- "We'll figure out the thinking panel later" in planning (it affects the SSE event schema)
- Step name never updates — only the final name renders
- Thinking panel content appears all at once after the response, not progressively

**Phase to address:**
Phase 2 (SSE Streaming) — define event taxonomy in the design doc before writing a single line of backend streaming code.

---

### Pitfall 6: Alpine.js State Destroyed on HTMX DOM Swap

**What goes wrong:**
When HTMX swaps a DOM region containing Alpine.js `x-data` components, Alpine destroys and re-initializes those components. Any local state (collapsed/expanded panel, uploaded file preview, form input values) resets to the initial `x-data` value. This is especially damaging for the thinking panel — if HTMX swaps the parent container, the expand/collapse state resets mid-stream.

**Why it happens:**
HTMX replaces DOM nodes wholesale. Alpine attaches its reactive state to specific DOM nodes via MutationObserver. When the node is destroyed, the state goes with it. Alpine does trigger `init()` on newly inserted nodes — but it starts fresh from the `x-data` declaration, not the previous state.

**How to avoid:**
Structure your swaps so that HTMX **never replaces a container that owns Alpine state**. Use targeted `id`-based swaps on leaf nodes only:

```html
<!-- WRONG: HTMX swaps this container, destroying the Alpine x-data -->
<div id="thinking-panel" hx-swap-oob="true" x-data="{ expanded: false }">
  <span id="step-name">Analyzing...</span>
</div>

<!-- CORRECT: HTMX swaps only the inner span, Alpine state on outer div survives -->
<div x-data="{ expanded: false }">
  <span id="step-name" hx-swap-oob="true">Analyzing...</span>
</div>
```

Use `hx-swap-oob` (out-of-band swaps) to target specific elements by ID without replacing their parent. If full container replacement is unavoidable, use HTMX's `morph` extension (`hx-ext="morph"`) which diffs and patches the DOM instead of replacing — this preserves Alpine state on unchanged nodes.

**Warning signs:**
- Thinking panel collapses itself whenever a new tool starts executing
- File upload preview disappears after the first SSE token arrives
- `x-show` transitions trigger on every SSE update (sign Alpine is reinitializing)

**Phase to address:**
Phase 2 (SSE Streaming) and Phase 3 (Thinking Panel) — design swap targets explicitly before writing any templates.

---

## Moderate Pitfalls

These cause delays and technical debt but not full rewrites.

---

### Pitfall 7: Jinja2 Template Path Breaks Across Routers

**What goes wrong:**
Templates render fine from the main router but throw `TemplateNotFound: base.html` when called from a sub-router (`/claims`, `/receipts`). The base template is "missing" even though the file exists.

**Why it happens:**
Each `APIRouter` that creates its own `Jinja2Templates` instance uses a relative path resolved from its own file location. If your router is in `src/agentic_claims/routes/claims.py` and templates are in `src/agentic_claims/templates/`, the relative `templates` path resolves differently than in `app.py`.

**How to avoid:**
Create a single `Jinja2Templates` instance in a shared module and import it everywhere:

```python
# src/agentic_claims/templates_config.py
from pathlib import Path
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```

Never use `Jinja2Templates(directory="templates")` — always use `Path(__file__).parent / "templates"` to anchor the path to the file's location.

**Warning signs:**
- `TemplateNotFound` only in sub-router routes, not main routes
- Works locally, fails in Docker (different working directory)

**Phase to address:**
Phase 1 (FastAPI Scaffold) — establish the single templates instance before writing any routes.

---

### Pitfall 8: Static Asset URLs Break in Docker Due to Missing StaticFiles Mount

**What goes wrong:**
CSS and JS load locally but return 404 in Docker. Alternatively, CSS paths are hardcoded as `/static/style.css` in the Stitch HTML designs but Jinja2 renders different paths.

**Why it happens:**
Stitch exports static HTML with relative asset paths. When converting to Jinja2, the paths must be replaced with `url_for('static', path='...')` calls. If `StaticFiles` is not mounted with the exact name `"static"`, `url_for('static', ...)` raises `NoMatchFound`. If mounted with a different name, all `url_for` calls silently produce wrong URLs.

**How to avoid:**
```python
# Mount BEFORE defining routes
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```

In Jinja2 templates, always use:
```html
<link rel="stylesheet" href="{{ url_for('static', path='css/main.css') }}">
```

Never use hardcoded `/static/...` paths — they will break if the mount point changes.

**Warning signs:**
- Browser DevTools shows 404 for `.css` and `.js` files
- Page renders but looks unstyled (Tailwind classes present but CSS missing)
- `starlette.routing.NoMatchFound: No route exists for name "static"` in logs

**Phase to address:**
Phase 1 (FastAPI Scaffold) — mount static files as part of the initial app setup.

---

### Pitfall 9: HTTP/1.1 Browser SSE Connection Limit (6 per domain)

**What goes wrong:**
The 7th browser tab opened to the app hangs indefinitely — no messages appear, the thinking panel never shows. The user refreshes, which creates a new SSE connection, pushing another tab over the limit.

**Why it happens:**
HTTP/1.1 browsers limit concurrent connections per domain to 6 (across all tabs). Each SSE stream holds one connection open indefinitely. Chrome and Firefox have marked this as "Won't Fix" for HTTP/1.1. The fix is HTTP/2, which multiplexes all SSE streams over a single TCP connection — effectively removing the limit.

**How to avoid:**
Configure the Docker app service to serve over HTTP/2. With Uvicorn + h2 package:

```bash
pip install h2
uvicorn app:app --ssl-keyfile key.pem --ssl-certfile cert.pem  # HTTP/2 requires TLS
```

For local development (no TLS), the limit is not a practical problem since users won't have 6+ tabs open. For production: put Nginx or Caddy as a reverse proxy with HTTP/2 enabled — the browser connects to the proxy over HTTP/2, the proxy to Uvicorn over HTTP/1.1.

**Warning signs:**
- SSE connection works in first tab, subsequent tabs hang at "Processing..."
- Browser DevTools shows SSE request "pending" with no response
- Issue disappears when other tabs are closed

**Phase to address:**
Phase 5 (Production Polish) — not a day-1 concern for local dev, but document it early to avoid confusion during testing.

---

### Pitfall 10: HTMX Image Upload Cannot Be Combined with JSON Body

**What goes wrong:**
The receipt image upload fails with a 422 `Unprocessable Entity` when the backend expects both a file and JSON metadata in the same request.

**Why it happens:**
When a form includes `<input type="file">`, the browser encodes the entire request as `multipart/form-data`. FastAPI cannot mix `Body(media_type="application/json")` fields with `File()` parameters in the same endpoint — the HTTP spec does not allow it.

The existing Chainlit app handled this by receiving the image and text separately (Chainlit `message.elements` vs `message.content`). In the HTMX version, you must send them in the same form.

**How to avoid:**
Use `Form()` and `File()` parameters together — not JSON body + File:

```python
@router.post("/chat/{thread_id}/message")
async def sendMessage(
    thread_id: str,
    message: Annotated[str, Form()],
    image: Annotated[UploadFile | None, File()] = None,
):
    ...
```

On the HTMX side, use `hx-encoding="multipart/form-data"` on any form that contains file inputs:
```html
<form hx-post="/chat/{{ thread_id }}/message"
      hx-encoding="multipart/form-data"
      hx-target="#response-area">
  <input type="text" name="message" />
  <input type="file" name="image" accept="image/*" />
</form>
```

**Warning signs:**
- 422 error with "value is not a valid string" for the message field
- File arrives but message is `None`, or vice versa
- Works with curl but fails via HTMX form submission

**Phase to address:**
Phase 3 (Receipt Upload) — design the multipart endpoint signature before writing the form template.

---

### Pitfall 11: Playwright Cannot `page.route()` SSE EventSource Connections

**What goes wrong:**
E2E tests try to intercept the SSE stream using `page.route('/stream/*', ...)` to inject mock events or assert on tokens. The route handler is never called. The test hangs waiting for DOM updates that never arrive.

**Why it happens:**
Playwright's `page.route()` intercepts fetch/XHR requests. `EventSource` (which the HTMX SSE extension uses under the hood) opens connections via a different browser mechanism that `page.route()` does not intercept. This is a documented limitation — `EventSource` connections pass through the network layer unintercepted.

**How to avoid:**
Two viable strategies:

**Strategy A: Test against the real server (integration tests)**
Let the SSE stream run normally. Use `page.waitForSelector('[data-testid="response-complete"]')` to wait for the final response element to appear. The server must emit a `done` event that the frontend uses to set a visible sentinel element.

```python
# In the HTMX template: when SSE closes, Alpine sets a flag
# <div x-data="{ done: false }" @sse:done="done = true">
#   <span x-show="done" data-testid="response-complete">Done</span>
# </div>

async def test_chat_message(page):
    await page.goto("/chat/test-thread")
    await page.fill("[name=message]", "Process this receipt")
    await page.click("[type=submit]")
    await page.wait_for_selector("[data-testid='response-complete']", timeout=30000)
    response_text = await page.inner_text("#response-area")
    assert len(response_text) > 0
```

**Strategy B: Test mode that bypasses SSE**
Add a `?test_mode=1` query param that makes the server return a regular `application/json` response instead of `text/event-stream`. The frontend detects this and renders synchronously. Use only for unit-level E2E tests where SSE behavior is not what's being tested.

**Warning signs:**
- `page.route()` handler never called for `/stream/` URLs
- Test hangs at `await page.wait_for_response('/stream/*')` indefinitely
- Intermittent failures because `waitForTimeout(5000)` sometimes isn't enough

**Phase to address:**
Phase 6 (E2E Tests) — define the testing strategy before writing any Playwright tests.

---

### Pitfall 12: `sse-swap` Event Name Case Sensitivity Silently Drops Events

**What goes wrong:**
The thinking panel receives some events but not others. Token streaming works but tool status updates never appear. No errors anywhere.

**Why it happens:**
The HTMX SSE extension matches `sse-swap="<name>"` against the SSE `event:` field exactly, including case. If the server emits `event: StepName` but the template uses `sse-swap="stepName"`, the event is silently dropped. This commonly happens when Python code uses snake_case or CamelCase and the template uses a different convention.

**How to avoid:**
Define all SSE event names as constants in a shared Python module and a corresponding JS/template constants list. Use lowercase-with-hyphens for all event names (e.g., `step-name`, `thinking-done`, `token`). Never derive event names from Python class names or function names.

```python
# constants.py
class SseEvent:
    TOKEN = "token"
    STEP_NAME = "step-name"
    STEP_CONTENT = "step-content"
    THINKING_DONE = "thinking-done"
    DONE = "done"
```

```html
<!-- Template uses same constants -->
<div sse-swap="step-name" hx-swap="innerHTML"></div>
<div sse-swap="token" hx-swap="beforeend"></div>
```

**Warning signs:**
- SSE connection established, some events work, others silently disappear
- Works when you manually open the SSE URL in a browser but not via HTMX

**Phase to address:**
Phase 2 (SSE Streaming) — define the event name contract before implementing either side.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `waitForTimeout(5000)` in Playwright | Test passes locally | Flaky CI (CI is slower than local) | Never |
| Store `thread_id` only in server dict (no cookie) | Simpler code | Users lose conversation on refresh | Never for prod |
| Hardcode SSE event names as strings in templates | Fast to write | Silent mismatches when names change | Never |
| Use `innerHTML` swap for token stream | Simple | Full DOM replacement on every token, O(n) repaint | Never for real streams |
| Open checkpointer context per request | Matches script pattern | Connection closed error on 2nd request | Never |
| Skip disconnect detection on SSE endpoint | Ship faster | Memory/CPU leak on every tab close | Never |
| One Jinja2Templates instance per router file | Easy to write | `TemplateNotFound` in Docker | Never |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| LangGraph + FastAPI | Opening `AsyncPostgresSaver` in request handler | Open once in `lifespan`, reuse via `app.state.graph` |
| HTMX SSE + LangGraph `astream_events` | Stream all internal events raw | Filter to user-facing events only; suppress `on_chain_stream` for internal nodes |
| HTMX + Alpine.js | Putting Alpine state on HTMX-swapped container | Target inner leaf nodes with swaps; keep Alpine state on stable outer containers |
| FastAPI + File Upload | Mixing `Body(...)` JSON with `File(...)` | Use `Form()` for all fields alongside `File()` |
| Playwright + SSE | `page.route()` to intercept EventSource | Use `waitForSelector` on sentinel element; or test-mode bypass |
| Jinja2 + HTMX partial responses | Returning full `base.html` on HTMX requests | Check `HX-Request` header; return partial template for HTMX, full template for direct load |
| SSE + Nginx reverse proxy | Nginx buffers SSE responses | Set `X-Accel-Buffering: no` header (FastAPI's `EventSourceResponse` does this automatically) |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `beforeend` appending full HTML per token | DOM has 500 `<span>` nodes per message | Append raw text and re-render once on `done` event | ~50 tokens |
| No `hx-boost` or navigation strategy | Full page reload on every page navigation | Use `hx-boost` on `<a>` tags or HTMX AJAX navigation | Immediate UX degradation |
| Returning full page from HTMX partial routes | Double-renders nav/head on every interaction | Check `request.headers.get("HX-Request")` before choosing template | Every request |
| astream_events without event filtering | Thousands of internal LangGraph events hit the SSE stream | Filter to `on_chat_model_stream`, `on_tool_start`, `on_tool_end` | Every multi-step agent run |

---

## "Looks Done But Isn't" Checklist

- [ ] **Thinking panel:** Has animated spinner while tools run — verify `step_name` event fires with new text on `on_tool_start`, not just on completion
- [ ] **Token streaming:** Tokens appear progressively — verify `beforeend` swap accumulates text rather than replacing it
- [ ] **Interrupt resume:** Works after page refresh — verify `graph.aget_state()` is checked before each message dispatch
- [ ] **Image upload:** File preview shown before submit — verify Alpine.js `@change` handler on file input sets `previewUrl`
- [ ] **SSE cleanup:** Generator stops when tab is closed — verify in server logs that graph invocation terminates on disconnect
- [ ] **Static assets:** CSS loads in Docker — verify `url_for('static', ...)` is used everywhere, not hardcoded paths
- [ ] **Multi-page navigation:** Active nav item highlights correctly — verify Jinja2 receives `current_page` context variable on every route
- [ ] **Thread ID persistence:** Conversation continues after soft navigation — verify `thread_id` is in a cookie or URL, not only server memory

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Checkpointer per-request lifecycle | HIGH | Refactor all SSE routes to use `app.state.graph`; test all conversation flows |
| No disconnect handling | MEDIUM | Wrap all SSE generators in disconnect-aware context; monitor for CPU drop |
| HTMX/Alpine swap conflict | MEDIUM | Audit all `hx-swap` targets; move Alpine state up to stable parent nodes |
| Wrong SSE event names | LOW | Update constants module + templates in sync; add a smoke test per event type |
| Template path not anchored | LOW | Replace all relative `Jinja2Templates(directory="templates")` with absolute Path |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Checkpointer lifecycle | Phase 1 (FastAPI Scaffold) | Can send 3 sequential messages on same `thread_id` without connection errors |
| SSE disconnect cleanup | Phase 2 (SSE Streaming) | Close browser tab mid-stream; verify server log shows generator terminated |
| HTMX SSE attribute placement | Phase 2 (SSE Streaming) | DOM updates on first token from smoke test |
| Interrupt/resume state | Phase 3 (Human-in-the-Loop) | `askHuman` flow completes end-to-end through page refresh |
| Thinking panel event taxonomy | Phase 2 (SSE Streaming) | All 6 event types render correctly in isolation before integration |
| Alpine/HTMX swap conflict | Phase 2 + 3 (streaming + thinking) | Collapse state survives 10 consecutive tool executions |
| Jinja2 template path | Phase 1 (FastAPI Scaffold) | All routes render in Docker with zero `TemplateNotFound` errors |
| Static asset URL generation | Phase 1 (FastAPI Scaffold) | All CSS/JS loads in Docker; no 404s in Network tab |
| HTTP/1.1 connection limit | Phase 5 (Production Polish) | Document as known limitation; configure HTTP/2 for prod |
| Multipart form + file | Phase 3 (Receipt Upload) | Image + text submit in single form, both received on backend |
| Playwright SSE intercept | Phase 6 (E2E Tests) | All SSE tests use sentinel element pattern, zero `waitForTimeout` calls |
| Event name case mismatch | Phase 2 (SSE Streaming) | Centralized `SseEvent` constants used in both server and templates |

---

## Sources

- [HTMX SSE Extension Official Docs](https://htmx.org/extensions/sse/) — HIGH confidence: attribute placement constraints, event name matching, swap behavior
- [FastAPI SSE Documentation](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — HIGH confidence: `EventSourceResponse`, `ServerSentEvent`, keep-alive, proxy headers
- [I Built a LangGraph + FastAPI Agent and Spent Days Fighting Postgres](https://medium.com/@termtrix/i-built-a-langgraph-fastapi-agent-and-spent-days-fighting-postgres-8913f84c296d) — HIGH confidence: three specific errors from real production migration (connection closed, context manager mismatch, missing setup())
- [Stop Burning CPU on Dead FastAPI Streams](https://jasoncameron.dev/posts/fastapi-cancel-on-disconnect) — HIGH confidence: `request.receive()` disconnect detection pattern
- [Alpine.js + HTMX integration issues — GitHub Discussions #4478](https://github.com/alpinejs/alpine/discussions/4478) — HIGH confidence: Alpine state loss on HTMX swaps, `Alpine.initTree()` workaround
- [Mastering LangGraph Checkpointing: Best Practices for 2025](https://sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025) — MEDIUM confidence: connection pool patterns, lifespan recommendation
- [SSE Browser Connection Limit — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) — HIGH confidence: HTTP/1.1 6-connection limit, HTTP/2 resolution
- [Playwright + SSE EventSource limitation — GitHub Issue #15353](https://github.com/microsoft/playwright/issues/15353) — HIGH confidence: `page.route()` does not intercept EventSource connections
- [Jinja2 Template Inheritance in FastAPI — GitHub Discussion #2630](https://github.com/fastapi/fastapi/discussions/2630) — MEDIUM confidence: template path resolution across routers
- [FastAPI File Upload — Official Docs](https://fastapi.tiangolo.com/tutorial/request-files/) — HIGH confidence: cannot mix JSON body with File parameters
- [LangGraph HITL + FastAPI — Shaveen Silva](https://shaveen12.medium.com/langgraph-human-in-the-loop-hitl-deployment-with-fastapi-be4a9efcd8c0) — MEDIUM confidence: interrupt/resume thread_id consistency requirement
- [HTMX SSE extension hx-ext placement bug — GitHub Issue #3467](https://github.com/bigskysoftware/htmx/issues/3467) — HIGH confidence: confirmed attribute placement constraint from official repo

---
*Pitfalls research for: Chainlit → FastAPI + HTMX migration (AI chat interface)*
*Researched: 2026-03-30*
