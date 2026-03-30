# Technology Stack

**Project:** Agentic Expense Claims — v2.0 UX Redesign (FastAPI + HTMX UI Layer)
**Researched:** 2026-03-30
**Scope:** NEW UI layer only. Existing backend stack (LangGraph, PostgreSQL, Qdrant, MCP servers, OpenRouter) is validated and unchanged.
**Overall Confidence:** HIGH (all critical choices verified via official docs or PyPI)

---

## Context: What Is Being Added

This milestone replaces Chainlit with a custom multi-page FastAPI web application. The backend (LangGraph graph, MCP servers, Postgres, Qdrant) is **not changing**. The research scope covers only:

1. FastAPI + Jinja2 (server-side rendering)
2. HTMX (dynamic page updates, SSE streaming)
3. Alpine.js (client-side local state)
4. Tailwind CSS (production build pipeline)
5. Playwright (browser E2E testing)
6. Middleware (sessions, static files)

---

## Recommended Stack

### Core Web Framework

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI | 0.135.2 | ASGI web framework, SSE streaming, route handling | Already in the stack. v0.135.0 added **native SSE support** (`EventSourceResponse` from `fastapi.sse`) — no external SSE library needed. Async-first, matches LangGraph async patterns. Latest: 0.135.2 (March 23, 2026). |
| Jinja2 | 3.1.6 | Server-side HTML templating | Starlette's built-in template engine; `Jinja2Templates` is part of FastAPI's standard toolkit. Template inheritance enables shared layout (sidebar, status bar) without duplication. Latest: 3.1.6 (March 5, 2025). |
| python-multipart | 0.0.20+ | Multipart form parsing (file uploads) | Required by FastAPI for `UploadFile` / `Form` endpoints. Without it, file upload endpoints silently fail. FastAPI docs flag this as a mandatory companion. |

**Confidence:** HIGH — FastAPI 0.135.2 and Jinja2 3.1.6 verified via PyPI.

---

### SSE Streaming

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `fastapi.sse` (built-in) | FastAPI 0.135.2 | Server-Sent Events for streaming LLM tokens | Native to FastAPI since 0.135.0. `EventSourceResponse` + `ServerSentEvent` cover all required use cases: token streaming, event naming, resume with `Last-Event-ID`. Automatically sets `X-Accel-Buffering: no` (Nginx fix) and sends keep-alive pings every 15s. No extra dependency. |

**Pattern for LangGraph streaming:**
```python
from fastapi.sse import EventSourceResponse, ServerSentEvent

@app.post("/chat/stream", response_class=EventSourceResponse)
async def stream_chat(request: ChatRequest) -> AsyncIterable[ServerSentEvent]:
    async for event in graph.astream_events(input, version="v2"):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content
            yield ServerSentEvent(data=chunk, event="token")
    yield ServerSentEvent(data="[DONE]", event="done")
```

**Do NOT use** `sse-starlette` (3.3.4, March 29, 2026) — still maintained, but redundant now that FastAPI has native SSE. Adding it introduces a dependency with no benefit for this project's use case.

**Confidence:** HIGH — verified via FastAPI official docs at `fastapi.tiangolo.com/tutorial/server-sent-events/`.

---

### Frontend: HTMX

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| HTMX | 2.0.8 | Hypermedia: dynamic page updates, form submissions, SSE connection | Current stable release. Eliminates JavaScript for server round-trips. Declarative via `hx-get`, `hx-post`, `hx-swap` attributes. Directly compatible with Jinja2 fragments (server returns partial HTML). |
| htmx-ext-sse | 2.2.4 | SSE extension for HTMX | Separate from core HTMX since v2. Installs with `hx-ext="sse"`. Provides `sse-connect` and `sse-swap` attributes for declarative SSE streaming into DOM elements. Has exponential-backoff reconnection built in. |

**CDN (development / fallback):**
```html
<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.8/dist/htmx.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4/sse.js"></script>
```

**File upload pattern** (receipt images):
```html
<form hx-post="/chat/upload"
      hx-encoding="multipart/form-data"
      hx-target="#chat-messages"
      hx-swap="beforeend">
  <input type="file" name="receipt" accept="image/*">
  <button type="submit">Upload Receipt</button>
</form>
```

`hx-encoding="multipart/form-data"` is required for file uploads — HTMX defaults to `application/x-www-form-urlencoded` which drops binary data.

**Drag-and-drop:** Alpine.js handles the drag-over/drop state management; HTMX handles the server submission. They operate at different layers and do not conflict.

**Confidence:** HIGH — verified via `htmx.org/extensions/sse/` official docs.

---

### Frontend: Alpine.js

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Alpine.js | 3.x (3.14.x) | Client-side local state: upload drag-and-drop, thinking panel toggle, UI state | No build step. Loads via CDN. `x-data`, `x-show`, `x-on:drop` cover all required local interactivity. Works via MutationObserver — automatically picks up DOM elements injected by HTMX swaps. |

**CDN:**
```html
<script defer src="https://cdn.jsdelivr.net/npm/[email protected]/dist/cdn.min.js"></script>
```

**Division of responsibilities:**
- **Alpine.js owns:** Upload drag-over highlight, file preview, thinking panel expand/collapse, button loading states, tab switching within a page section.
- **HTMX owns:** All server round-trips — submitting receipts, loading claim lists, SSE token streaming.
- **They do not overlap.** Alpine manages `x-data` state; HTMX manages `hx-*` HTTP requests. Different attribute prefixes, different DOM layers.

**Critical integration note:** Alpine.js sets up a MutationObserver on `document`. When HTMX swaps new HTML into the page, Alpine automatically initializes `x-data` on new elements — no manual re-initialization needed for simple cases. However, if HTMX **replaces** an element that contains Alpine state, that state is destroyed. Use `hx-swap="beforeend"` (append) for chat messages to preserve existing Alpine state.

**Confidence:** HIGH — verified via `alpinejs.dev/start-here` official docs.

---

### CSS: Tailwind

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| pytailwindcss | 0.3.0 (wraps Tailwind v3.x) | Production CSS build from Jinja2 templates | No Node.js required. Installs Tailwind standalone CLI via pip. Scans Jinja2 templates, generates purged CSS. Supports `TAILWINDCSS_VERSION` env var for pinning. Latest: 0.3.0 (October 29, 2025). |

**Why Tailwind v3, not v4:**
The Stitch HTML designs (`docs/ux/`) use `cdn.tailwindcss.com` with inline JS config (`tailwind.config = { theme: { extend: { colors: {...} } } }`). This is the **Tailwind v3 CDN format** — the `theme.extend.colors` pattern with hex values. Tailwind v4 changed to CSS-first config with `@theme { --color-*: oklch(...) }`. Migrating 60+ design tokens from v3 hex format to v4 OKLCH CSS variables adds risk with zero value for this course project. Stay on v3 to match the designs exactly.

**Build configuration:**
```bash
# Install
pip install pytailwindcss

# One-time: init config from Stitch design tokens
npx tailwindcss init  # OR extract from docs/ux/ inline config

# Development watch
pytailwindcss -i src/agentic_claims/static/css/input.css \
              -o src/agentic_claims/static/css/output.css \
              --watch

# Production build
pytailwindcss -i src/agentic_claims/static/css/input.css \
              -o src/agentic_claims/static/css/output.css \
              --minify
```

`tailwind.config.js` needs `content` pointing at Jinja2 templates:
```js
module.exports = {
  darkMode: "class",
  content: ["./src/agentic_claims/templates/**/*.html"],
  theme: {
    extend: {
      colors: { /* extracted from docs/ux/ Stitch designs */ }
    }
  }
}
```

**The design HTML files reference `cdn.tailwindcss.com` — do not ship CDN in production.** Replace with the built `output.css` link in the base template.

**Confidence:** HIGH for approach (pytailwindcss verified via PyPI, Tailwind v3 vs v4 analysis based on Stitch design files inspection). MEDIUM for pytailwindcss v4 compatibility claim in search results (source is indirect; pinning to v3 avoids this risk entirely).

---

### Browser E2E Testing: Playwright

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| playwright | 1.58.0 | Browser automation, E2E test driver | Latest Python release (January 30, 2026). Supports Chromium, Firefox, WebKit. Headless mode for CI. Auto-waits for elements, handles async content (important for SSE streaming). |
| pytest-playwright | 0.7.2 | pytest plugin for synchronous Playwright tests | Standard pytest integration. Provides `page`, `browser`, `browser_context` fixtures. Latest: 0.7.2 (November 24, 2025). |
| pytest-playwright-asyncio | 0.7.2 | pytest plugin for async Playwright tests | Required if writing tests as `async def`. Same version as pytest-playwright. Provides async-native fixtures. Use this instead of the sync version given the project's async-first stance (pytest-asyncio already in use). |

**FastAPI live server fixture pattern** (required for E2E tests):
```python
# tests/conftest.py
import threading
import uvicorn
import pytest
from agentic_claims.app import app

@pytest.fixture(scope="session")
def live_server():
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8001))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for server ready
    import time, httpx
    for _ in range(30):
        try:
            httpx.get("http://127.0.0.1:8001/health")
            break
        except Exception:
            time.sleep(0.1)
    yield "http://127.0.0.1:8001"
    server.should_exit = True
```

**Confidence:** HIGH — playwright 1.58.0 and pytest-playwright 0.7.2 verified via PyPI. pytest-playwright-asyncio 0.7.2 confirmed separate async variant.

---

### Middleware

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Starlette `SessionMiddleware` (built-in) | bundled with FastAPI | Cookie-based session state (thread_id, claim_id per browser session) | Already part of Starlette which FastAPI depends on. Signed cookie sessions. Stores `thread_id` and `claim_id` so each browser tab gets isolated LangGraph state. No extra dependency. |
| Starlette `StaticFiles` (built-in) | bundled with FastAPI | Serve CSS, JS, images from `/static` | Already part of Starlette. Mount at `/static` in FastAPI app. Serves the built Tailwind CSS, HTMX, Alpine.js (downloaded/vendored), and any font assets. |

**No CORS middleware needed** — this is a server-rendered app, not an API consumed from external origins.

**Session key management:** `SESSION_SECRET_KEY` must be in `.env.local` (not hardcoded). Starlette's `SessionMiddleware` requires a secret key for cookie signing.

**Confidence:** HIGH — verified via FastAPI and Starlette official documentation.

---

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-multipart` | 0.0.20+ | Multipart form parsing for file uploads | Required for any `UploadFile` or `Form` parameter in FastAPI routes |
| `aiofiles` | 24.x | Async file I/O | If receipt images need to be written to disk (currently base64 in memory — only needed if storage strategy changes) |
| `httpx` | Latest | Async HTTP client | Already in stack. Used in live-server health check fixture |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `sse-starlette` | Redundant — FastAPI 0.135.0 has native `EventSourceResponse` with all required features | `fastapi.sse.EventSourceResponse` (built-in) |
| Tailwind CSS v4 CDN (`cdn.jsdelivr.net/npm/@tailwindcss/browser@4`) | Stitch designs use v3 token format. v4 breaks `theme.extend.colors` JS config pattern; migration adds scope without value | `pytailwindcss` (v3 standalone CLI) |
| `cdn.tailwindcss.com` in production | CDN processes CSS in-browser at runtime: slow, unoptimized, no purging. Official Tailwind docs explicitly say "not intended for production" | `pytailwindcss` build + serve via `StaticFiles` |
| React / Vue / any SPA framework | Adds Node.js build pipeline and increases JS bundle size. Project constraint explicitly excludes SPAs. HTMX + Alpine.js achieves all required interactivity | HTMX + Alpine.js |
| WebSocket | Adds bidirectional complexity not needed here. SSE is one-directional (server → client) which is all that's needed for token streaming | FastAPI native SSE |
| `fastapi-jinja` (third-party) | Abandoned library (last commit 2022). FastAPI ships `Jinja2Templates` natively via Starlette | `from fastapi.templating import Jinja2Templates` (built-in) |
| pytest-playwright sync version alone | Project uses pytest-asyncio throughout. Mixing sync and async test fixtures causes event loop conflicts | `pytest-playwright-asyncio` (async variant) |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| FastAPI 0.135.2 | Starlette 0.46.x | FastAPI depends on specific Starlette version; pip resolves automatically |
| HTMX 2.0.8 | htmx-ext-sse 2.2.4 | SSE extension must match HTMX major version. v1.x extension is incompatible with HTMX 2.x |
| Alpine.js 3.x | HTMX 2.0.8 | No known conflicts. Use `defer` on Alpine script tag to load after DOM. Alpine MutationObserver picks up HTMX swaps automatically |
| pytailwindcss 0.3.0 | Tailwind v3.x | Wraps v3 standalone CLI. Do not use with v4 config syntax (`@theme`) |
| playwright 1.58.0 | pytest-playwright-asyncio 0.7.2 | Same release cycle; both from January–November 2025 |
| python-multipart | FastAPI 0.135.2 | FastAPI docs list it as required companion for form/file endpoints; any recent version works |

---

## Installation

```bash
# Web framework (FastAPI already in stack — verify version is 0.135.2+)
poetry add "fastapi>=0.135.2"
poetry add jinja2 python-multipart

# CSS build (dev dependency — not needed at runtime)
poetry add --group dev pytailwindcss

# E2E testing (dev dependency)
poetry add --group dev playwright pytest-playwright-asyncio
poetry run playwright install chromium  # download browser binaries

# HTMX and Alpine.js — vendor or CDN
# Option A: Vendor into static/ (recommended for reproducibility)
# Download htmx.min.js and sse.js into src/agentic_claims/static/js/
# Option B: CDN links in base template (simpler, requires internet at runtime)
```

**Note:** `aiofiles` is optional — only add if receipt images move from in-memory to disk storage.

---

## Alternatives Considered

| Category | Recommended | Alternative | When Alternative Makes Sense |
|----------|-------------|-------------|------------------------------|
| SSE library | `fastapi.sse` (built-in) | `sse-starlette` 3.3.4 | If you need advanced connection pooling or multi-client broadcast patterns beyond what built-in provides |
| CSS build | `pytailwindcss` (v3) | Tailwind v4 with `@config` | If you're starting a new project from scratch without existing v3 design tokens |
| CSS build | `pytailwindcss` | Node.js + `npm run build` | If team already has Node.js toolchain in place |
| Frontend interactivity | HTMX + Alpine.js | React / Next.js | If app has complex client-side state that can't be expressed as simple x-data objects |
| E2E testing | `pytest-playwright-asyncio` | Selenium + `pytest-selenium` | If you need IE11 support (not relevant here) |
| Session storage | Starlette `SessionMiddleware` (cookie) | Redis-backed sessions | If session data exceeds ~4KB cookie limit (thread_id + claim_id are tiny; this won't happen) |

---

## Stack Patterns by Use Case

**Streaming LLM tokens to browser:**
- FastAPI SSE endpoint (`EventSourceResponse`) wraps LangGraph `astream_events(version="v2")`
- HTMX `hx-ext="sse"` + `sse-connect` + `sse-swap` renders tokens into chat div
- Alpine.js handles scroll-to-bottom behavior on new token arrival

**Receipt image upload with drag-and-drop:**
- Alpine.js: `x-on:dragover.prevent`, `x-on:drop.prevent` manage drag state and file preview
- HTMX: `hx-post="/chat/upload" hx-encoding="multipart/form-data"` submits file to FastAPI
- FastAPI: `UploadFile` parameter receives file, base64-encodes, stores in `imageStore`

**LangGraph interrupt/resume (clarification questions):**
- SSE stream sends a `ServerSentEvent(event="interrupt", data=question)` when interrupt detected
- HTMX: `sse-swap="interrupt"` injects the clarification prompt into the chat UI
- User types response; HTMX `hx-post="/chat/resume"` sends it; backend calls `Command(resume=...)`

**Dynamic page navigation (sidebar):**
- HTMX `hx-get="/dashboard" hx-target="#main-content" hx-push-url="true"` swaps page content
- No full page reload; browser URL updates via `hx-push-url`

**Python ≥ 3.11 requirement for streaming:**
- LangGraph `get_stream_writer()` uses `ContextVar` for propagation across async tasks
- Python < 3.11 has ContextVar propagation bugs in async task trees
- Project already on Python 3.12+ (confirmed in CLAUDE.md), so no action needed

---

## Sources

| Source | Topics Verified | Confidence |
|--------|----------------|------------|
| `fastapi.tiangolo.com/tutorial/server-sent-events/` | FastAPI native SSE, `EventSourceResponse`, `ServerSentEvent` API, caveats | HIGH |
| `pypi.org/project/fastapi/` | FastAPI version 0.135.2, release date March 23, 2026 | HIGH |
| `htmx.org/extensions/sse/` | HTMX SSE extension v2.2.4, attributes, CDN URL | HIGH |
| `htmx.org/posts/2024-06-17-htmx-2-0-0-is-released/` | HTMX 2.0 release notes, extension separation | HIGH |
| `alpinejs.dev/start-here` | Alpine.js v3 CDN URL, x-data, x-on, x-show, x-model | HIGH |
| `pypi.org/project/playwright/` | Playwright 1.58.0, released January 30, 2026 | HIGH |
| `pypi.org/project/pytest-playwright/` | pytest-playwright 0.7.2, sync-only, November 24, 2025 | HIGH |
| `pypi.org/project/pytest-playwright-asyncio/` | pytest-playwright-asyncio 0.7.2, async fixtures | HIGH |
| `pypi.org/project/pytailwindcss/` | pytailwindcss 0.3.0, supports Tailwind v3/v4, October 29, 2025 | HIGH |
| `tailwindcss.com/docs/installation/play-cdn` | CDN is dev-only, not for production | HIGH |
| `tailwindcss.com/docs/installation/tailwind-cli` | Standalone CLI (no Node.js), v4.2 current | HIGH |
| `tailwindcss.com/docs/upgrade-guide` | v3→v4 breaking changes: JS config → CSS `@theme`, color token format | HIGH |
| `docs/ux/01_ai_chat_submission.html` (project file) | Confirms designs use Tailwind v3 CDN + JS config format | HIGH (direct inspection) |
| `starlette.dev/middleware/` | SessionMiddleware, StaticFiles built into Starlette | HIGH |
| `pypi.org/project/jinja2/` | Jinja2 3.1.6, March 5, 2025 | HIGH |
| `dev.to/kasi_viswanath/streaming-ai-agent-with-fastapi-langgraph-2025-26-guide-1nkn` | LangGraph astream_events + FastAPI SSE integration pattern | MEDIUM (community article, consistent with LangGraph docs) |

---

*Stack research for: FastAPI + HTMX multi-page AI chat application (v2.0 UX Redesign)*
*Researched: 2026-03-30*
*Scope: UI layer additions only. Backend stack unchanged from v1.0.*
