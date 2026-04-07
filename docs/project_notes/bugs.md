# Bug Log

Bugs discovered during Phase 2.3 UAT testing. Resolved bugs documented for reference; open bugs queued for next phase.

## Resolved

### BUG-001: VLM JSON parse failure from markdown wrapping
- **Found**: Phase 2.3 UAT (CLI)
- **Symptom**: extractReceiptFields returns `{"error": "Failed to parse VLM response as JSON"}`, agent says "I'm having trouble connecting"
- **Root cause**: Gemini models wrap JSON output in ` ```json ``` ` markdown code blocks; `json.loads()` fails on the backtick wrapper
- **Fix**: Added markdown code block stripping in `extractReceiptFields.py` before `json.loads()`
- **File**: `src/agentic_claims/agents/intake/tools/extractReceiptFields.py`

### BUG-002: CLI uses wrong MCP URLs (Docker-internal hostnames)
- **Found**: Phase 2.3 UAT (CLI)
- **Symptom**: MCP calls fail with connection refused; logs show `http://mcp-currency:8000/mcp/` instead of `http://localhost:8003/mcp/`
- **Root cause**: `ConversationRunner` passes `_env_file=".env.e2e"` to its own Settings instance, but tools call `getSettings()` which creates new `Settings()` defaulting to `.env.local`
- **Fix**: Added `load_dotenv(envFile, override=True)` in ConversationRunner constructor to set env vars in `os.environ` before any code runs
- **File**: `src/agentic_claims/cli.py`

### BUG-003: gemma-3-27b-it has no tool-calling endpoints
- **Found**: Phase 2.3 UAT (browser)
- **Symptom**: OpenRouter returns 404 — `No endpoints found that support tool use`
- **Root cause**: Model listed with tool support in OpenRouter docs but no provider endpoint actually supports it
- **Fix**: Queried OpenRouter `/api/v1/models` endpoint to find models with verified `tools` in `supported_parameters`; switched to `google/gemini-2.0-flash-001`
- **File**: `.env.local`, `.env.e2e`

### BUG-004: JSONB insertion fails in submitClaim
- **Found**: Phase 2.3 UAT (previous session)
- **Symptom**: `submitClaim` returns DB error — psycopg3 can't adapt dict to JSONB
- **Root cause**: psycopg3 requires explicit `psycopg.types.json.Json()` wrapper for dict/list values going into JSONB columns
- **Fix**: Wrapped `intakeFindings` and `lineItems` with `Json()` in DB MCP server
- **File**: `mcp_servers/db/server.py`

### BUG-005: Empty response renders blank message in Chainlit
- **Found**: Phase 2.3 UAT (previous session)
- **Symptom**: Agent processes successfully but Chainlit shows empty message bubble
- **Root cause**: No fallback when `astream_events` produces no final text (e.g., interrupt or nested graph event mismatch)
- **Fix**: Added state extraction fallback — reads last AI message from graph state when `finalResponse` is empty
- **File**: `src/agentic_claims/app.py`

### BUG-006: SSL certificate verification fails in Docker container
- **Found**: Phase 2.3 UAT (browser)
- **Symptom**: `SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer certificate`; user sees "I ran into an issue processing your request"
- **Root cause**: Docker container (Python 3.11 base image) missing or has stale CA root certificates for OpenRouter's TLS chain
- **Fix**: Added `ca-certificates` package to Dockerfile and updated `certifi` in requirements; set `REQUESTS_CA_BUNDLE` environment variable
- **File**: `Dockerfile`, `requirements.txt`
- **Phase**: 2.4

### BUG-007: Thinking CoT panels invisible in light mode
- **Found**: Phase 2.3 UAT (browser)
- **Symptom**: No collapsible "Thought for Xs" panel visible above agent responses in light mode
- **Root cause**: CSS in `public/custom.css` uses white-based `rgba(255, 255, 255, ...)` colors designed for dark theme; in light mode everything is white-on-white invisible
- **Fix**: Replaced single-theme CSS with `@media (prefers-color-scheme)` dual-theme CSS for both light and dark modes
- **File**: `public/custom.css`
- **Phase**: 2.4

### BUG-008: submitClaim called twice on unique constraint violation
- **Found**: Phase 2.3 UAT (browser, Docker logs)
- **Symptom**: Phase 2 shows CLAIM-001, Phase 3 confirmation shows CLAIM-002; two claims created in DB
- **Root cause**: Model generates CLAIM-001 which hits `claims_claim_number_key` unique constraint (already exists from E2E test run), model self-recovers by retrying with CLAIM-002
- **Fix**: Added `idempotency_key` column with `ON CONFLICT DO NOTHING` in `insertClaim` tool; prevents duplicate submissions
- **File**: `mcp_servers/db/server.py`, `alembic/versions/004_add_idempotency_key.py`
- **Phase**: 2.4

### BUG-009: CLAIM-NNN collision across sessions
- **Found**: Phase 2.3 UAT (browser, Docker logs)
- **Symptom**: `duplicate key value violates unique constraint "claims_claim_number_key" — Key (claim_number)=(CLAIM-001) already exists`
- **Root cause**: Model generates sequential claim numbers (CLAIM-001, CLAIM-002) without checking DB for existing entries; each new session starts from CLAIM-001
- **Fix**: DB sequence generates claim numbers via `nextval('claim_number_seq')`; agent no longer generates CLAIM-NNN in Phase 2
- **File**: `alembic/versions/004_add_idempotency_key.py`, `mcp_servers/db/server.py`, `src/agentic_claims/agents/intake/tools/submitClaim.py`, `src/agentic_claims/agents/intake/agentSystemPrompt.py`
- **Phase**: 2.4

### BUG-011: finalResponse set prematurely by intermediate LLM generation
- **Found**: Phase 2.3 UAT (log analysis)
- **Symptom**: No user-visible impact currently; `finalResponse` variable gets set to a 553-char intermediate response between extractReceiptFields and convertCurrency, then overwritten by the actual 473-char final response
- **Root cause**: ReAct loop emits `on_chat_model_end` with no tool calls for intermediate reasoning; app.py treats this as `finalResponse` assignment; only works because the actual final response overwrites it later
- **Fix**: Added `pendingToolCalls` counter; `finalResponse` only set from last non-tool generation after all tool calls complete
- **File**: `src/agentic_claims/app.py`
- **Phase**: 2.4

## Open

### BUG-018: Duplicate intake audit entries (receipt_uploaded, ai_extraction) — **RESOLVED Phase 8 QA**
- **Found**: Phase 8 UAT (DB inspection, claim 19)
- **Root cause**: `bufferStep` had no deduplication. In multi-turn conversations `intakeNode` re-scanned all accumulated messages on each turn and called `bufferStep` again for prior turns' tool messages. `flushSteps` flushed all N copies.
- **Fix**: Made `bufferStep` idempotent per action — silently skips if the action is already buffered for that session.
- **Files**: `src/agentic_claims/agents/intake/auditLogger.py`
- **Commit**: `3d75e1b`

### BUG-019: Advisor silent failure — claim 17 stuck in PENDING — **RESOLVED Phase 8 QA**
- **Found**: Phase 8 UAT (DB inspection, claim 17)
- **Root cause**: Any exception beyond 402 credit errors in `advisorNode` (network timeout, LLM parse failure, etc.) propagated uncaught, leaving the claim in "pending" with no audit_log entry.
- **Fix**: Added `_advisorErrorFallback` that catches all non-402 exceptions, writes an `advisor_decision` audit entry with `reason: advisor_error`, calls `updateClaimStatus` to set status to "escalated", and returns a valid state update.
- **Files**: `src/agentic_claims/agents/advisor/node.py`
- **Commit**: `7f231be`

### BUG-016: Advisor raw JSON response leaks into chat UI + claim status stuck on PENDING — **RESOLVED Phase 8 QA**
- **Found**: Phase 8 UAT (browser)
- **Fix**:
  1. `finalResponse` now only updated from the first non-empty assignment. Intake agent captures it first; subsequent advisor `on_chat_model_end` events are ignored.
  2. Added post-loop TABLE_UPDATE after graph completes that re-fetches claim status from DB whenever `claimSubmittedFlag` is True, so advisor status transitions are reflected.
- **Files**: `src/agentic_claims/web/sseHelpers.py`
- **Commit**: `6f4ac6a`

### BUG-017: Audit Log page crashes on dict confidence value — renders empty — **RESOLVED Phase 8 QA**
- **Found**: Phase 8 UAT (browser)
- **Fix**:
  1. Added `isinstance(conf, dict)` check before `float()` in `_buildTimelineSteps` with `score`/`value`/`confidence` key unwrapping and a `try/except (TypeError, ValueError)` guard.
  2. Split single try block into two independent blocks so `_fetchAllClaims` failure cannot be triggered by a `_fetchTimeline` exception.
- **Files**: `src/agentic_claims/web/routers/audit.py`
- **Commit**: `5c89708`

### BUG-015: Model fails to use user-provided employee ID
- **Found**: Phase 6.1 UAT (browser, QA cycles 3-4 + post-delivery testing)
- **Symptom**: Two failure modes observed:
  1. User provides "EMP-042" → model ignores it and uses prompt example "EMP-001" in claim summary and DB
  2. User provides plain numeric ID "1010736" → model doesn't recognize it as an employee ID, re-asks ("You haven't provided your employee ID yet")
- **Root cause**: Prompt-following issue with Qwen3-235B-A22B. The Phase 2 instruction says "look for patterns like EMP-001, EMP001, or any alphanumeric ID" but the model either ignores the value or fails to match non-EMP formats. The turn routing advances to Phase 2 correctly (extractReceiptFields exists) but the model generates a text response (0 tools) instead of calling searchPolicies.
- **Severity**: Medium — blocks submission flow or persists wrong data to DB
- **Fix planned**: Phase 6.2 — extract employee ID server-side from the user message and inject into submitClaim, rather than relying on the model to propagate it. Remove EMP-001 example from prompt entirely.

### BUG-013: LLM hallucinated claim submission — CLAIM-1523 never persisted — **RESOLVED Phase 6.1**
- **Found**: Phase 7 UAT (browser + DB verification)
- **Symptom**: Chat shows "Claim Reference: CLAIM-1523" with "successfully submitted" message, but claim does not exist in PostgreSQL.
- **Root cause**: QwQ-32B skipped `submitClaim` tool call and hallucinated the submission response.
- **Fix (Phase 6.1)**:
  1. Switched to `qwen/qwen3-235b-a22b-2507` (better tool compliance)
  2. V2 system prompt with "Submission Reality" guardrails and Phase 3 self-verification
  3. BUG-013 dual guard in sseHelpers.py: Layer 1 suppresses submitted=True when no submitClaim in thinkingEntries; Layer 2 replaces hallucinated response with error message
  4. 3 unit tests covering guard behavior
- **Verified**: QA Scenario 2 (Phase 6.1 UAT) confirmed submitClaim actually called, claim exists in DB

### BUG-012: Submission Summary panel not updating after claim submission — **RESOLVED Phase 6.1**
- **Found**: Phase 7 UAT (browser)
- **Symptom**: Summary panel shows "Current Session", "USD 98.56" (unconverted), "50% Complete", category "--", submit button visible after submission
- **Fix (Phase 6.1)**:
  1. Summary panel header shows CLAIM-XXX after submission (conditional template)
  2. progressPct milestone-driven: 33/50/66/100%
  3. SGD converted amount displayed
  4. Receipt thumbnail via GET /chat/receipt-image
  5. Submit button hidden after submission (conditional template)
- **Verified**: QA Scenario 3 (Phase 6.1 UAT) confirmed all fields correct after submission
- **Residual**: Category still shows "--" (tracked as BUG-014)

### BUG-010: Post-submission agents produce no visible output — **RESOLVED Phase 8**
- **Found**: Phase 2.3 UAT (analysis)
- **Symptom**: After submitClaim, compliance/fraud/advisor nodes run but their messages are not rendered in Chainlit
- **Root cause**: Post-submission nodes are plain function nodes (not LLM calls); they append AIMessages to state but don't emit `on_chat_model_stream` events that app.py listens for
- **Fix**: Phase 8 replaced stubs with LLM-powered agents that emit stream events

### BUG-020: Receipt image NULL in database — image_path not persisted — **RESOLVED Phase 8 QA**
- **Found**: Phase 8 UAT (Claim Review page — no receipt image shown)
- **Root cause**: `submitClaim` tool expected the LLM to pass `imagePath` in claimData, but the LLM never reliably provides it. The receipt image was stored in-memory (imageStore) but its disk path was not injected into the tool.
- **Fix**: Created `imagePathContext.py` with a ContextVar. Chat router sets it from `getImagePath(sessionIds["claimId"])` before graph execution. `submitClaim` reads it and merges into claimData.
- **Regression**: Initial fix by maverick-dev used undefined `claimId` variable instead of `sessionIds["claimId"]`, causing `NameError` that crashed the SSE stream silently. Fixed manually.
- **Files**: `src/agentic_claims/web/imagePathContext.py` (new), `src/agentic_claims/web/routers/chat.py`, `src/agentic_claims/agents/intake/tools/submitClaim.py`

### BUG-021: Claim Review intelligence cards invisible on dark theme — **RESOLVED Phase 8 QA**
- **Found**: Phase 8 UAT (Claim Review page — Fraud Check card completely white)
- **Root cause**: Used `bg-green-500/5` and `text-green-300` which rendered as invisible white on the dark theme. Similarly, Compliance and AI Insight cards had styling that didn't match the established Flag Reason card pattern.
- **Fix**: Rewrote all 3 intelligence cards (Compliance, Fraud, AI Insight) to use `bg-surface-container-highest` + `bg-{color}-container/10` pattern matching the Flag Reason card. Each card uses error (red) or secondary (green) colors depending on pass/fail outcome.
- **Files**: `templates/review.html`

### BUG-022: Approval badge shows "AUTO-APPROVED BY AI" for reviewer-approved claims
- **Found**: Phase 8 UAT (Claim Review page)
- **Root cause**: Template only checked `claim.status == "approved"` without distinguishing agent vs reviewer approval.
- **Fix**: Template now checks `claim.approvedBy` — "agent" shows "AUTO-APPROVED BY AI", any other value shows "APPROVED BY REVIEWER".
- **Files**: `templates/review.html`

### BUG-023: Claim Review shows "auto-approved" for escalated claims
- **Found**: Phase 8 UAT (Claim Review page)
- **Root cause**: Same template logic as BUG-022 — status check without approvedBy distinction.
- **Fix**: Combined with BUG-022 fix.
- **Files**: `templates/review.html`

### BUG-024: Decision Pathway shows premature COMPLETED status
- **Found**: Phase 8.1 UAT (browser)
- **Symptom**: Chat shows "Analyzing..." (LLM still processing first tool call) but Decision Pathway already shows AI Extraction COMPLETED (0% confidence, Merchant: Unknown) and Policy Check COMPLETED
- **Root cause**: `runGraph` in sseHelpers.py (lines 548-576) reconstructs pathway state from `graph.aget_state()` before the current agent run starts. If the checkpointed state has any prior data (e.g., from a previous turn or stale state), the pathway marks steps as completed immediately on the initial render.
- **Severity**: Medium — misleading UX, user sees completed steps that haven't actually run yet
- **Files**: `src/agentic_claims/web/sseHelpers.py`

### BUG-026: Post-submission agents block SSE stream — should run in background
- **Found**: Phase 8.1 UAT (browser, multiple occurrences)
- **Symptom**: After claim submission, the thinking panel shows "Preparing response..." for 60-90s while compliance, fraud, and advisor agents run. Timer restarts from 1s at ~50-59s. User thinks the app is frozen.
- **Root cause**: The SSE stream waits for the ENTIRE graph (`intake → compliance || fraud → advisor → END`) to complete before emitting the "done" event. The chat should return immediately after intake submits the claim to DB. Post-submission agents should not block the user's chat.
- **Severity**: High — 60-90s unnecessary wait, users think app is broken
- **Fix**: Decouple post-submission agents from the SSE stream. After intake submits the claim, fire the "done" event immediately. Run compliance, fraud, and advisor agents as a background task (`asyncio.create_task` or similar). Claim Review page shows results when the background pipeline completes.
- **Files**: `src/agentic_claims/web/sseHelpers.py`, `src/agentic_claims/core/graph.py`

### BUG-025: Chat stuck at "Analyzing..." with no error toast on LLM timeout
- **Found**: Phase 8.1 UAT (browser, multiple occurrences)
- **Symptom**: Receipt uploaded, "Analyzing..." spinner shown, but chat never progresses. No error toast appears. Logs show `on_chat_model_start - ChatOpenRouter` with no subsequent events.
- **Root cause**: OpenRouter LLM call hangs indefinitely (no timeout configured). The SSE stream stays open waiting for `astream_events` to yield, but no events come. The global error toast system catches JS errors, HTMX errors, and SSE errors, but a hanging LLM call produces none of these — it's a silent infinite wait.
- **Severity**: High — blocks entire claim flow with no user feedback
- **Suggested fix**: Add timeout to OpenRouter client calls. Emit SSE error event if no `astream_events` output within N seconds.
- **Files**: `src/agentic_claims/infrastructure/openrouter/client.py`, `src/agentic_claims/web/sseHelpers.py`
