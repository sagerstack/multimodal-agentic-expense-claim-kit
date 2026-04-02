# Phase 7: SSE Streaming + Full Chat Page - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Complete migration of the Chainlit chat interface to the FastAPI + Jinja2 + HTMX application. The Chat Page (Page 1) becomes fully functional: SSE streams token-by-token AI responses from the LangGraph Intake Agent, receipt upload stores images and triggers VLM extraction, LangGraph interrupt/resume works for clarifications, the thinking panel streams named steps interleaved with reasoning, and all v1.0 Intake Agent capabilities work identically through the new UI.

This phase does NOT add new agent capabilities — it migrates the existing Intake Agent workflow (Phases 1–2.5) to the new UI with feature parity.

</domain>

<decisions>
## Implementation Decisions

### Streaming UX
- Sequential flow: thinking panel completes FIRST, then AI response appears below — not overlapping
- Thinking panel auto-collapses to a summary line (e.g. "Thought for 12s · 3 tools") when final response starts — user can re-expand
- Reuse existing `TOOL_LABELS` from `app.py` for step names: "Extracting receipt fields...", "Checking policies...", "Converting currency...", "Submitting claim..."
- Type B reasoning (QwQ-32B `reasoning_content` tokens) visible in thinking panel, interleaved with tool summaries — matches current Chainlit behavior

### Receipt upload flow
- Both drag-and-drop onto chat area AND click attach button trigger file picker
- Upload preview in chat thread: thumbnail image + filename as a user message bubble
- Image quality rejection (blurry/low-res) comes through the agent's response — the `extractReceiptFields` tool handles rejection and the model communicates the error naturally in chat. No separate UI error element needed.
- One receipt per conversation — matches v1.0 architecture (single claimId per session)

### Chat interaction model
- Input remains active during agent processing — user can type next message, queued via asyncio.Queue
- Clarification prompts (LangGraph askHuman interrupt) appear as normal AI chat messages, input re-enables for user to respond — no special card/banner styling
- Text-based confirmations only — no Confirm/Edit quick-reply buttons. User types "yes" or corrections as normal chat messages (matches v1.0 behavior)
- Explicit "New Claim" reset button in the UI that clears chat and generates new session IDs (new thread_id + claim_id)

### Submission summary panel
- Real-time updates during processing — panel updates progressively as fields are extracted (amount, category appear as VLM returns them)
- Keep batch UI layout from Stitch design (cosmetic) — batch details show the single submitted claim, "Submit Entire Batch" button stays disabled. Future-proofs the UI.
- Warning/flags count updates live from agent — reflects policy violations found by searchPolicies during processing
- Per-field confidence scores shown in BOTH chat response AND summary panel for quick reference

### End-to-end Intake Agent (migration parity)
- OpenRouter integration: LLM model for agent reasoning + VLM model for receipt extraction — both via existing OpenRouterClient, unchanged
- All 5 Intake Agent tools must work: extractReceiptFields, searchPolicies, convertCurrency, submitClaim, askHuman
- getClaimSchema tool (schema-driven prompt) works identically to v1.0
- Graph invocation uses lifespan singleton from Phase 6 (graph + checkpointer from app.state)
- Session state (thread_id, claim_id) from SessionMiddleware cookie — established in Phase 6
- Full pipeline: receipt upload → VLM extraction → policy validation → currency conversion → clarification → claim submission to DB
- Reference Phases 1 through 2.5 for the full evolved requirement set

### Claude's Discretion
- Exact SSE event JSON payload structure
- CSS animation for intelligence pulse during processing
- New Claim button placement and styling
- How progressive summary panel updates are triggered (SSE events vs HTMX polling)
- Error message styling for edge cases
- Exact layout of confidence score badges in summary panel

</decisions>

<specifics>
## Specific Ideas

- Streaming must feel like the existing Chainlit app — CoT in thinking panel FIRST, then actual response below. Sequential, not simultaneous.
- Reference existing `app.py` (Chainlit) for proven streaming event handling logic — SSE endpoint replicates this, outputting SSE events instead of updating cl.Step
- `_stripToolCallJson` and `_stripThinkingTags` helpers from app.py must be preserved — QwQ-32B outputs these artifacts
- `_summarizeToolOutput` from app.py reused for tool summaries in thinking panel
- chat.html template already has the Stitch layout (two-column: chat + summary, greeting, input area). Phase 7 wires it with real functionality.
- Image quality rejection is NOT a UI concern — the model handles it through the agent system prompt and extractReceiptFields tool

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. All decisions map to existing ROADMAP.md requirements (STRE-01 through STRE-05, MIGR-01/03/04/05/06/07/08, CHAT-01 through CHAT-11).

Note: CHAT-05 (Confirm/Edit quick-reply buttons) is explicitly deferred — user chose text-based confirmations matching v1.0 behavior. The requirement can be revisited in a future enhancement phase if needed.

</deferred>

---

*Phase: 07-sse-streaming-full-chat-page*
*Context gathered: 2026-04-02*
