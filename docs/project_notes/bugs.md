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

### BUG-014: Summary panel category shows "--" instead of extracted category
- **Found**: Phase 6.1 UAT (browser, QA cycle 4 for Plan 01 and cycle 1 for Plan 02)
- **Symptom**: Chat response correctly identifies "Meal" as the category, but summary panel shows "--" in both Top Category widget and Batch Details
- **Root cause**: `_extractSummaryData` in `sseHelpers.py` parses category from thinkingEntries tool output, but the field name/path from the model's extractReceiptFields response doesn't match the expected key. The extraction result includes category but the summary data pipeline doesn't map it through.
- **Severity**: Low — cosmetic, all other summary panel fields populate correctly
- **Fix planned**: Phase 6.2 — trace the category field from extractReceiptFields tool result through thinkingEntries to `_extractSummaryData` and fix the key mapping

### BUG-015: Model uses prompt example employee ID instead of user-provided value
- **Found**: Phase 6.1 UAT (browser, QA cycles 3 and 4)
- **Symptom**: User provides "EMP-042" but claim summary and DB show "EMP-001". The model uses the example employee ID from the v2 system prompt instead of the actual value from the user's message.
- **Root cause**: Prompt-following issue with Qwen3-235B-A22B. Despite replacing all example values with placeholders and adding "Use the actual employee ID the user provided, not an example value", the model occasionally ignores the user-provided ID. Works on retry (Turn 3 if user repeats it).
- **Severity**: Medium — incorrect data persisted to DB, but user can work around by repeating the value
- **Fix planned**: Phase 6.2 — consider extracting employee ID server-side from the user message and injecting it into the submitClaim call, rather than relying on the model to propagate it

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

### BUG-010: Post-submission agents produce no visible output
- **Found**: Phase 2.3 UAT (analysis)
- **Symptom**: After submitClaim, compliance/fraud/advisor nodes run but their messages are not rendered in Chainlit
- **Root cause**: Post-submission nodes are plain function nodes (not LLM calls); they append AIMessages to state but don't emit `on_chat_model_stream` events that app.py listens for
- **Severity**: Low — expected for Phase 1 (stubs with "Hello world" placeholder text)
- **Suggested fix**: When real agents are implemented, either make them LLM-based (will emit stream events) or add explicit rendering in app.py for post-submission messages
