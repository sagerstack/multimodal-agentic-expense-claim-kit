# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-30)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Milestone v2.0 — Phases 11 and 13 complete; Phase 8.1, 10, 12 remain

## Current Position

Phase: 14 — Intake GPT React Replacement (in progress)
Plan: 6/7 plans complete (14-01, 14-02, 14-03, 14-04, 14-05, 14-06 done)
Status: Phase 14 active. Plan 14-06 (No-path recovery flows) complete: correction loop + submit-cancel session reset, 37/37 tests pass.
Last activity: 2026-04-14 — Completed 14-06-PLAN.md (No-path recovery: correction_requested outcome, field_correction loop, sessionReset flag + chat.py rotation)

```
v2.0 Progress: [###################################] 35/38 plans
Phase 6:       [##########] 3/3 plans (complete)
Phase 7:       [##########] 3/3 plans (complete)
Phase 6.1:     [##########] complete
Phase 6.2:     [##########] 4/4 plans (complete)
Phase 6.3:     [##########] 6/6 plans (complete)
Phase 8:       [##########] 5/5 plans (complete)
Phase 8.1:     [####......] 0/4 plans (in progress — bugs documented)
Phase 8.2:     [##########] 3/3 plans (complete)
Phase 10:      [..........] 0/2 plans
Phase 11:      [##########] 4/4 plans (complete)
Phase 12:      [##########] 4/4 plans (complete — checkpoint pending)
Phase 13:      [##########] 9/9 plans (complete)
Phase 14:      [####......] 3/7 plans (in progress)
```

## Performance Metrics

**Velocity (from v1.0):**
- Total plans completed: 31
- Average duration: 8 min
- Total execution time: ~3.5 hours

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

Carried forward from v1.0:
- LangGraph orchestration: validated, continues
- MCP servers as Docker services: validated, continues
- Vertical slice architecture per agent: validated, continues
- CamelCase naming throughout: validated, continues
- OpenRouter via OpenAI SDK: validated, continues
- FastMCP with Streamable HTTP: validated, continues

Phase 12 decisions (2026-04-11):
- Eval suite uses plain dataclass (not pydantic-settings) — standalone, decoupled from app
- LiteLLMModel model string is `openrouter/openai/gpt-4o` (litellm provider/model format)
- ER-018/019/020 scoringType = "safety" (not "verifier" per PDF tier table wording)
- 18.pdf missing from eval/invoices/ — capture handles gracefully (file-not-found error JSON)
- deepeval/litellm installed via pip --trusted-host due to SSL cert issue with poetry on this machine
- ER-013 uses buildDuplicateCapturePrompt (two-session pattern, logout between sessions)
- Enrichment uses psycopg (not asyncpg) — already in project dependencies
- Qdrant enrichment uses scroll API with section metadata filter on expense_policies collection
- DB enrichment overrides browser-scraped agentDecision with authoritative advisor_decision column
- claude-code-sdk query() used for subagent capture (not ClaudeSDKClient -- benchmarks are stateless)
- parseSubagentResponse() 3-tier extraction: plain JSON -> markdown-fenced -> balanced-brace scan
- stepScore() reads metric.score attributes post-evaluate() (not EvaluationResult.test_results iteration)
- LiteLLMModel uses base_url (not deprecated api_base)

New for v2.0:
- Chainlit replaced by FastAPI + Jinja2 + HTMX
- Stitch HTML designs (`docs/ux/`) are the UI spec
- Dark theme only ("Neon Nocturne")
- Playwright for browser E2E tests (Phase 10)
- SSE for chat streaming via HTMX sse extension (Phase 7)
- Alpine.js for local UI state (Phase 7, 9)
- `asyncio.Queue` per session to decouple POST from SSE GET (Phase 7)
- Checkpointer as lifespan singleton — not per-request (Phase 6, critical pitfall prevention)
- Tailwind v4 CSS-first via pytailwindcss — not CDN, not v3 config (migrated to @import/@theme format)

Phase 6 discoveries:
- pytailwindcss v0.3 downloads Tailwind v4.2.2 (not v3). Migrated to v4 CSS-first format (@import "tailwindcss", @theme block). tailwind.config.js deleted.
- Starlette 1.0 changed TemplateResponse API: now `(request, name, context=)` instead of `(name, {"request": request, ...})`
- Circular import between main.py and pages.py resolved by extracting templates to `web/templating.py`
- itsdangerous required for SessionMiddleware cookie signing (added as dependency)

Phase 6 v2 redo discoveries (2026-04-02):
- projectRoot path resolution broken inside Docker — `Path(__file__).parent` resolves to site-packages, not /app. Fixed with directory-walking detection + /app fallback.
- mcp-rag container crashes on restart due to SSL cert error downloading sentence-transformers model. Fixed by mounting host HuggingFace cache as read-only volume with HF_HUB_OFFLINE=1.
- Ruff N802/N803/N806 rules conflict with CamelCase convention — suppressed in pyproject.toml.

Phase 7 discoveries (2026-04-02):
- FastAPI `EventSourceResponse` with manual construction expects strings/bytes, not `ServerSentEvent` objects. Fix: use `response_class=EventSourceResponse` on the endpoint decorator.
- `ServerSentEvent(data=...)` JSON-serializes strings (adds quotes). Use `raw_data=` for HTML/text payloads that HTMX injects directly into the DOM.
- Ruff N999 (module naming) and N812 (import alias) also conflict with CamelCase convention — added to suppression list.
- HTMX SSE dispatches `htmx:sseMessage` (camelCase with colon), not `sse-message`. Use CustomEvent + window listener pattern for Alpine.js integration.

### Critical Pitfalls to Avoid

From research (see .planning/research/PITFALLS.md):

1. **Checkpointer per-request** (HIGH recovery cost) — RESOLVED in Phase 6 (lifespan singleton)
2. **SSE generator not cancelled on disconnect** (MEDIUM) — Must check `request.is_disconnected()` in Phase 7
3. **HTMX SSE attribute placement** — `hx-ext="sse"` and `sse-connect` must be on the same element in Phase 7
4. **Interrupt/resume state lost** — Use `graph.aget_state()` to detect interrupts; no session flags in Phase 7
5. **Alpine.js state destroyed on HTMX swap** — Target inner leaf nodes; keep Alpine on stable outer containers in Phase 7+

### Phase Dependencies

- Phase 6 COMPLETE
- Phase 7 COMPLETE
- Phase 8 depends on Phase 7 (HTMX partial patterns established, backend data available from intake) — UNBLOCKED
- Phase 9 depends on Phase 8 (page navigation patterns established, claims data available)
- Phase 8 depends on Phase 6.3 (auth + reviewer pages must exist before agent output feeds into them)
- Phase 10 depends on Phase 8 (all agents must be functional before E2E test authoring)

### Research Flags (from SUMMARY.md)

- **Phase 9** — Fraud/Advisor agent data storage schema not yet researched; `003_add_agent_output_columns.py` migration likely needed. Run `/gsd:research-phase` before Phase 9 planning.
- **Phase 10** (conditional) — Playwright async SSE sentinel patterns may need deeper research if `waitForSelector` proves insufficient for multi-step LangGraph streaming.

### Pending Todos

- Verify actual requirement count: REQUIREMENTS.md header says 54 but enumeration yields 61. Update header during Phase 7.
- Phase 2.5 has 2 skipped plans (CSS reasoning block styles, E2E browser verification) — these are superseded by the new v2.0 UI and Playwright suite respectively.
- Pre-existing test failure: `testSubmitClaimCallsInsertClaimAndInsertReceipt` — FIXED in Phase 6.2 (commit ed1e16d, field key alignment).

### Blockers/Concerns

- Phase 2.5 remains not started (it was open when v2.0 was initialized). The new UI supersedes the Chainlit-specific plans (02.5-04 CSS, 02.5-05 E2E). Plans 02.5-01 through 02.5-03 (QwQ-32B, schema-driven prompt, progressive streaming) should be completed or skipped depending on whether the Chainlit migration context is still needed — MIGR-07 and MIGR-08 in Phase 7 carry these capabilities forward.

## Session Continuity

Last session: 2026-04-14
Stopped at: Completed Phase 14 Plan 06 — No-path recovery flows: correction_requested outcome, field_correction loop, sessionReset flag + chat.py session rotation. 37/37 tests pass.
Resume file: None

### Roadmap Evolution

- v1.0 archived to MILESTONES.md (24/26 plans across phases 1–2.5)
- v2.0 milestone started: Phases 6–10, 14 plans total
- Phase 11 added: Intake Multi-Turn Fix — restore askHuman interrupt for multi-turn confirmation flow (2026-04-11)
- Phase 6 completed: 2026-04-01 (3 plans, 3 waves)
- Phase 7 completed: 2026-04-02 (3 plans, 3 waves, 36 new tests, browser UAT passed)
- Phase 11 completed: 2026-04-11 (4 plans, 2 waves, 18/18 must-haves verified)
- Phase 13 added: Intake Agent Hybrid Routing + Bug Fixes — align intake agent with docs/deep-research-*.md (hybrid code-enforced routing + prompt-driven conversation); closes 6 open intake-layer bugs (2, 3, 4, 5, 6, 7) as symptoms of the misalignment (2026-04-12)

Phase 13 decisions (2026-04-12, Plan 06):
- messages delta form chosen in _mergeSubgraphResult: slice result["messages"][priorCount:] so outer add_messages reducer appends only new messages without duplicates
- phase field absent from IntakeSubgraphState: 13-02 boolean-flag decomposition supersedes single enum; phase key does not exist in ClaimState
- _intakeConditionalRouter: postIntakeRouter + evaluatorGate composed inline in a single conditional edge — escalation takes precedence over submitted/pending routing
- _buildLlmAndTools extracted as shared factory for both getIntakeAgent and intakeNode

Phase 13 decisions (2026-04-12):
- convertCurrency structured contract: two-layer normalisation — MCP server (source of truth) + intake tool wrapper (defence-in-depth for legacy shapes)
- rate-is-None guard in MCP server returns {supported: False} (not just HTTP 404)
- No secondary currency provider (Frankfurter → manual-rate askHuman is the two-tier chain, wired in Plan 06)
- No currency caching (locked decision per 13-CONTEXT.md)
- logEvent keyword is logCategory= (not category=) — confirmed from core/logging.py
- v5 prompt: 8-section layered operating manual; all routing removed; Section 6 synthetic directive contract readies LLM for ROUTING DIRECTIVE SystemMessages from pre-model hook (Plan 05)
- v5 confidence thresholds: High >=0.85, Medium 0.60-0.84, Low <0.60 (tightened from v4.1)
- deep-research-report.md is upstream synthesis; systemprompt-chat-agent.md and technical.md are the authoritative cite-sites for implementation (intentional traceability model)
- Boolean-flag decomposition chosen over single phase enum: composable flags (clarificationPending + askHumanCount + unsupportedCurrencies) provide finer routing granularity without enum exhaustion (13-02)
- preModelHook returns llm_input_messages (ephemeral channel, never writes state.messages); directives prepended before baseMessages (13-04)
- postModelHook trigger: all three must be true (hasContent + no tool_calls + clarificationPending); retry bound = 1 (13-04)
- humanEscalationNode uses getSettings().db_mcp_url — consistent with all existing call sites; zero hardcoded URL literals in codebase (13-04)
- TypedDict fields have no default factories — consuming code uses .get(field, default) convention (13-02)
- postToolFlagSetter scans only trailing unbroken ToolMessage run (this-turn scope) to avoid double-counting across turns (13-05)
- submitClaimGuard escalates immediately on hallucination detection — no soft-rewrite for submitClaim hallucinations per 13-CONTEXT.md (13-05)
- logEvent(logger, event, logCategory=...) is the correct call convention — plan examples used wrong dict-as-first-arg form (13-05)

Phase 13 decisions (2026-04-13, Plan 09):
- PROBE A and PROBE D retained at logging.DEBUG level instead of deleted — user directive (overrides plan's "fully remove" must_haves). Rationale: probes remain diagnostically useful; DEBUG level prevents default log noise. ROADMAP Criterion #7 reinterpreted as "probes no longer emit at default log level" and treated as satisfied.
- Single aget_state() per /chat/message request: single fetch wrapped by sse.aget_state_timing (logCategory="chat" to disambiguate from sseHelpers' own timing event); auto-reset short-circuits the resume check because a new thread_id has no pending interrupts by construction — satisfies ROADMAP Criterion #8 without second DB read.
- priorStateFetchFailed flag: when the single aget_state raises, chat.resume_check_failed fires once; both auto-reset and resume checks skip their state-dependent logic.
- interruptDetection.py (Option 3 resume contract) committed alongside chat.py refactor — the module is the authoritative source for pending-interrupt state (checkpointer, not session cookie).
