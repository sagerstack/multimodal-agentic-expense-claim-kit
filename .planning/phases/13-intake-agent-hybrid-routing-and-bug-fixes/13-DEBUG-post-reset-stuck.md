---
status: diagnosed
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
gap_ref: 13-UAT.md Gap 3
created: 2026-04-13
trigger: "After chat.auto_reset fires, the next user message on the new thread is not processed by the intake graph."
---

## Symptoms (from live UAT 2026-04-12/13, Session 1)

- 23:56:09  evaluator_gate decision=submitted (CLAIM-007, thread 3fe5976a, claim 168f3fb0)
- 23:56:12.112  `chat.auto_reset` fires -> new threadId `6ee78a10-...`, new claimId `50bb44e7-...`
- 23:56:12.122  `user.chat_message_submitted` "yes" on new thread 6ee78a10 (+10 ms after reset)
- 23:56:12.174  `claim.draft_created` (dbClaimId=29)
- (silence)  No `agent.turn_queued`, no `intake.started`, no `llm.call_started`, no SSE frames on thread 6ee78a10
- 23:56:21  `sse.post_submission_completed` on OLD claim 168f3fb0 (background task, expected)
- 23:57:04  User manually hits `/chat/reset`

Expected path on a fresh turn: `user.chat_message_submitted` -> POST 204 -> SSE GET loop dequeues -> `agent.turn_queued` -> `agent.turn_started` -> intake graph runs. What is missing between `claim.draft_created` and `agent.turn_queued` is the single signal that the SSE generator dequeued the graph input. The input was enqueued but never consumed.

## Current Focus

hypothesis: Queue-to-consumer orphaning across threadId rotation. The SSE GET generator bound its local `queue` to the OLD threadId at stream-open time and never rebinds. After `auto_reset`, POST puts the new graph input on the NEW threadId's queue while the only live SSE consumer is still `.get()`-ing on the OLD (now-removed) queue.
test: Trace the lifetime of `queue` in `streamChat` vs the lifetime of `threadId` in `postMessage`.
expecting: streamChat captures threadId once at request open; postMessage rotates `request.session["thread_id"]` but does not tear down the active SSE generator.
next_action: Document the exact mismatch and name a minimal fix.

## Evidence

### 1. SSE client holds ONE long-lived connection to `/chat/stream`

`templates/chat.html:5`

```
<div id="sseContainer" hx-ext="sse" sse-connect="/chat/stream" ...>
```

htmx opens `/chat/stream` once when `chat.html` renders. There is no `HX-Redirect`, no page reload, and no `HX-Trigger` emitted by auto_reset (grep of `src/agentic_claims/web` and `templates` shows zero references). The browser's EventSource stays attached to the stream the user opened at login.

### 2. streamChat captures threadId once per request

`src/agentic_claims/web/routers/chat.py:250-266`

```python
@router.get("/chat/stream", response_class=EventSourceResponse)
async def streamChat(request: Request):
    sessionIds = getSessionIds(request)
    threadId = sessionIds["threadId"]          # <-- captured ONCE
    queue = getOrCreateQueue(threadId)         # <-- bound to OLD threadId
    graph = request.app.state.graph

    while True:
        if await request.is_disconnected():
            break
        try:
            graphInput = await asyncio.wait_for(queue.get(), timeout=30.0)
            ...
```

`threadId` and `queue` are local variables assigned before the `while True:` loop. The loop only re-checks disconnect and pings. It never re-reads `request.session["thread_id"]`, so the generator consumes from the same `asyncio.Queue` for its entire lifetime.

### 3. postMessage rotates thread_id AND destroys the old queue

`src/agentic_claims/web/routers/chat.py:90-123` (auto-reset branch)

```python
if priorState and priorState.values and priorState.values.get("claimSubmitted"):
    oldClaimId = claimId
    oldThreadId = threadId
    if oldClaimId:
        clearImage(oldClaimId)
    if oldThreadId:
        removeQueue(oldThreadId)                       # <-- kills the old queue dict entry
    request.session["thread_id"] = str(uuid.uuid4())   # <-- rotate cookie-backed id
    request.session["claim_id"] = str(uuid.uuid4())
    ...
    threadId = request.session["thread_id"]            # local var, used below
    claimId  = request.session["claim_id"]
    autoResetFired = True
```

Then later, `queue = getOrCreateQueue(threadId)` at line 244 uses the NEW threadId and `.put()`s the graph input there (line 245).

`src/agentic_claims/web/sessionQueues.py:15-17`:

```python
def removeQueue(threadId: str) -> None:
    _queues.pop(threadId, None)
```

Critically, `removeQueue` only deletes the dict entry. The in-flight `asyncio.Queue` object still exists in memory because the `streamChat` generator is holding a strong reference to it through its local `queue` variable. No exception is raised inside `queue.get()`; the generator is still awaiting, on a queue object that nobody can reach anymore to put items into.

### 4. POST /chat/message puts to the NEW queue

`src/agentic_claims/web/routers/chat.py:244-247`:

```python
queue = getOrCreateQueue(threadId)   # threadId is NEW uuid after auto_reset
await queue.put(graphInput)
return Response(status_code=204)
```

`getOrCreateQueue` creates a brand-new `asyncio.Queue` keyed by the new threadId. There is no live consumer on this queue. The SSE GET generator is still blocked on `queue.get()` against the orphaned old-thread queue.

### 5. draft_claim_created fires because it is synchronous in the POST path

`src/agentic_claims/web/routers/chat.py:152-189` runs the `insertClaim` MCP call inline inside `postMessage`, BEFORE the `queue.put(graphInput)` on line 245. That is why the log shows `claim.draft_created` (23:56:12.174) but never `agent.turn_queued` - the draft row is inserted by the HTTP handler, but the queued input never reaches a consumer. Consistent with the observed log.

### 6. Background post-submission task is NOT the blocker

`src/agentic_claims/web/routers/chat.py:318-337` launches `runPostSubmissionAgents` via `asyncio.create_task(...)`. That task opens its own `config = {"configurable": {"thread_id": threadId}}` scoped to the OLD submitted thread (`sseHelpers.py:632-677`). It does not touch `_queues`, does not hold a lock, and runs to completion (`sse.post_submission_completed` at 23:56:21 confirms). It is temporally adjacent but causally independent.

## Eliminated

- hypothesis: (b) Background post-submission task holds a queue reference belonging to the old thread
  evidence: `runPostSubmissionAgents(graph, threadId, claimId)` in `sseHelpers.py:632-677` only calls `graph.aget_state(config)` and `graph.ainvoke(None, config)`. No queue access. It completes at 23:56:21 without side-effects on the new thread's queue.
  timestamp: 2026-04-13

- hypothesis: (d) /chat/message POST path short-circuits on a recent auto_reset flag
  evidence: `postMessage` has no such guard. After auto_reset, it unconditionally continues through draft_created, `queue = getOrCreateQueue(threadId); await queue.put(graphInput)` (`chat.py:244-245`). POST returns 204; input is on the queue.
  timestamp: 2026-04-13

- hypothesis: (a, narrow reading) "SSE stream drained then reconnects late" - implies the browser opens a new EventSource after auto_reset
  evidence: `chat.html:5` uses a single `sse-connect="/chat/stream"` declared at page load. There is no HX-Redirect, no htmx event, nothing in auto_reset that closes or reconnects the EventSource. The browser keeps the same TCP connection. The stream never disconnects and never reconnects, so it never rebinds to the new threadId's queue.
  timestamp: 2026-04-13

## Resolution

### Root cause (confirmed)

**Variant of hypothesis (c): `threadId` rotation on auto_reset leaves the SSE GET generator bound to the OLD queue, while POST puts messages into a freshly-created NEW queue that has no consumer.**

The `/chat/stream` endpoint captures `threadId` and the `asyncio.Queue` reference ONCE at connection-open (`chat.py:254-255`). The POST `/chat/message` handler rotates `request.session["thread_id"]` in-place during auto_reset (`chat.py:101`) and creates a NEW queue under the new key (`chat.py:244`). The old queue is `.pop()`-ed from the `_queues` dict (`sessionQueues.py:15-17`), but the SSE generator still holds a strong reference to it, so Python does not GC it and `queue.get()` does not raise - it simply blocks forever on a queue nobody can reach.

Net effect: after auto_reset, POST-side producer and GET-side consumer point to different queue instances. First post-reset message is stranded on the new queue. Subsequent messages on the same new thread are also stranded (same mechanism). Only a fresh page load (or an htmx `hx-post="/chat/reset"` that closes+reopens the SSE stream via reload) reconnects the consumer to the correct queue.

### Key invariant being violated

> The SSE GET generator's `queue` reference MUST always point to the same queue instance that the next POST `/chat/message` for this session will write to.

Currently this invariant holds at stream-open, then is silently broken the first time auto_reset fires.

### Proposed fix outline (code-side, minimal surface area)

Pick ONE of these; they are listed in order of increasing invasiveness. My recommendation is **Option 1**, which is 5-10 lines and preserves the existing architecture.

- **Option 1 (recommended): Re-resolve queue per iteration in `streamChat`.**
  Inside the `while True:` loop in `chat.py:258-316`, call `getSessionIds(request)` and `getOrCreateQueue(...)` on every iteration (before the `queue.get()` await), and `asyncio.wait_for` against a short timeout. When the session's thread_id has rotated, the generator picks up the new queue on the next iteration without requiring a reconnect. Requires a way to break out of the old `queue.get()` when rotation happens - simplest is to keep the existing 30 s timeout AND have `auto_reset` explicitly put a sentinel on the OLD queue so the generator wakes immediately, re-reads session, and rebinds.

- **Option 2: Emit an HX-Redirect (or HX-Trigger + small JS) from the POST response on auto_reset.**
  Change `postMessage` to return a 205/286 + `HX-Refresh: true` when `autoResetFired` is True, which forces htmx to reload the page. The new `chat.html` render opens a fresh `/chat/stream` bound to the new thread_id. Heavier UX (visible reload, scroll position lost) but zero backend queue surgery.

- **Option 3: Session-indexed queue instead of thread-indexed queue.**
  Key `_queues` by the Starlette session id (stable across auto_reset) rather than by `threadId`. `streamChat` reads session queue once; POST always writes to the same queue; the thread_id rotation only affects the LangGraph config, not the transport. Correct and minimal at runtime, but requires updating `getOrCreateQueue`/`removeQueue` call sites and semantics. Re-evaluate if Option 1 proves flaky under load.

- **Option 4: Detect orphaning defensively.**
  In `postMessage`, after `auto_reset` removes the old queue, additionally `await oldQueue.put(_SENTINEL)` on the still-live object so the SSE generator unblocks and its next loop iteration re-reads `request.session["thread_id"]` via `getSessionIds`. Combines with a small refactor of `streamChat` to re-resolve `queue` after processing each input. Essentially Option 1 + the wake-up signal made explicit.

### Files to touch (for Option 1)

- `src/agentic_claims/web/routers/chat.py` - `streamChat` loop: re-resolve `threadId` and `queue` before each `queue.get()`. Also in `postMessage` auto_reset branch: push a sentinel to the OLD queue object before `removeQueue(oldThreadId)`.
- `src/agentic_claims/web/sessionQueues.py` - `removeQueue` may need to return the popped queue so the caller can push the sentinel; or add a helper `popAndReturn(threadId)`.
- No template changes, no JS changes, no graph changes.

### Out of scope for this fix

- Gap 1 (display regression) - unrelated transport issue.
- Gap 2 (policy-exception loop) - prompt/state issue upstream.
- Gaps 4-6 - separate code paths.

## Verification plan (for the fix, not this debug doc)

1. Reproduce Session 1 trace: submit a claim, wait for `chat.auto_reset`, send "yes" within 2 s.
2. Assert: within 5 s of the second POST, logs show `agent.turn_queued`, `agent.turn_started`, and at least one SSE frame on the new threadId.
3. Assert: the old-thread background `sse.post_submission_completed` still fires and does not corrupt the new thread.
4. Regression: cold-start flow (no auto_reset) still works; manual `/chat/reset` still works.
