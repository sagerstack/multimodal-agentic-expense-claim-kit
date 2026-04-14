---
phase: 14
plan: "04"
subsystem: intake-gpt-web
tags:
  - interrupt
  - sse
  - htmx
  - jinja2
  - button-ui
  - fastapi

dependency-graph:
  requires:
    - "14-01: intake-gpt subgraph foundation"
    - "14-02: interrupt classifier (deterministic yes/no handling)"
  provides:
    - uiKind annotation on all requestHumanInput interrupt payloads
    - interrupt_buttons.html partial for Yes/No button rendering
    - SSE interrupt renderer that dispatches on uiKind (buttons vs text)
    - POST /chat/message accepts button_value form field with logging
  affects:
    - "14-05: frontend Alpine.js wiring that consumes the INTERRUPT SSE event"
    - "14-06: E2E tests that verify button click flow end-to-end"

tech-stack:
  added: []
  patterns:
    - "uiKind dispatch: single source of truth in requestHumanInput, consumed by SSE renderer"
    - "template path resolution: Path(__file__).resolve() relative to test file for cwd-independence"
    - "dual hidden fields: message (canonical reply) + button_value (analytics metadata)"

file-tracking:
  created:
    - templates/partials/interrupt_buttons.html
    - tests/test_intake_gpt_web.py
  modified:
    - src/agentic_claims/agents/intake_gpt/tools/requestHumanInput.py
    - src/agentic_claims/web/sseHelpers.py
    - src/agentic_claims/web/routers/chat.py

decisions:
  - "uiKind is derived in requestHumanInput (not in SSE renderer) — single source of truth at the tool layer"
  - "button label rendered inline (no surrounding whitespace) so test assertions can use simple string matching"
  - "button_value does not replace message — both are sent so POST handler has zero downstream changes"
  - "SSE renderer fallback: if Jinja2 template fails, yield plain question string (no crash)"

metrics:
  duration: "4 min"
  completed: "2026-04-14"
  tasks: 3
  tests-added: 7
  tests-total: 41
---

# Phase 14 Plan 04: Button Interrupt Backend Summary

Backend machinery for Yes/No button interrupts. Annotates interrupt payloads with a `uiKind` hint, renders a Jinja2 button HTML partial in the SSE INTERRUPT event, and accepts structured `button_value` replies in `POST /chat/message`.

## What Was Built

### uiKind Contract

The interrupt payload now always includes two new fields:

- `uiKind`: `"buttons"` for `field_confirmation` and `submit_confirmation`; `"text"` for all other kinds.
- `options`: `[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]` for button kinds; `[]` for text kinds.

This is the single source of truth — derived in `requestHumanInput` by `_deriveUiKind()` and `_deriveButtonOptions()`, consumed by the SSE renderer without duplication.

### Button Kinds

Two interrupt kinds produce button UI:

| Kind | uiKind | Rationale |
|------|--------|-----------|
| `field_confirmation` | buttons | Binary: user confirms or rejects extracted fields |
| `submit_confirmation` | buttons | Binary: user confirms or rejects submission |
| `policy_justification` | text | Free-text: user explains a policy exception |
| `manual_fx_rate` | text | Free-text: user provides a numeric exchange rate |

### SSE Dispatch Flow

When the SSE stream hits a `pendingInterrupt`:

1. Read `uiKind` from `payload.get("uiKind", "text")`.
2. Emit `sse.interrupt_render` log event with `kind`, `uiKind`, `blockingStep`.
3. If `uiKind == "buttons"`: render `partials/interrupt_buttons.html` via Jinja2, yield as `SseEvent.INTERRUPT`.
4. Else: yield raw `question` string as `SseEvent.INTERRUPT` (prior behaviour preserved).
5. Fallback: if Jinja2 template render raises, yield `str(question)`.

### Template Path Resolution Strategy

`test_interruptButtonsPartialRendersYesNoButtons` uses:

```python
_REPO_ROOT = Path(__file__).resolve().parent.parent  # tests/ -> repo root
_TEMPLATE_PATH = _REPO_ROOT / "templates" / "partials" / "interrupt_buttons.html"
```

This resolves relative to `__file__` (not cwd), so the test is robust when pytest is invoked from any working directory. An explicit `assert _TEMPLATE_PATH.exists()` fires before the Jinja2 lookup to produce a meaningful error message if the template is missing.

### Button Partial Form Structure

```html
<form hx-post="/chat/message" hx-swap="none" hx-encoding="multipart/form-data">
  <input type="hidden" name="button_value" value="yes">
  <input type="hidden" name="message" value="yes">
  <button type="submit">Yes</button>
</form>
```

Both hidden fields carry the same option value. `message` preserves the existing POST contract (canonical reply text). `button_value` is additive metadata for analytics and future disambiguation of typed vs clicked replies.

## Test Count

| Module | Tests | Status |
|--------|-------|--------|
| tests/test_intake_gpt.py | 34 | All pass |
| tests/test_intake_gpt_web.py | 7 | All pass (new) |
| **Total** | **41** | **All pass** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Button label whitespace caused test assertion mismatch**

- **Found during:** Task 3b test run
- **Issue:** The Jinja2 template rendered `\n        Yes\n      ` between `<button>` tags due to multiline indentation. The test asserted `">Yes</button>"` (inline), causing a failure.
- **Fix:** Collapsed button label to inline: `>{{ opt.label }}</button>` — removes surrounding whitespace, preserves identical visual output.
- **Files modified:** `templates/partials/interrupt_buttons.html`
- **Commit:** b16054c

## Commits

| Hash | Message |
|------|---------|
| ad38bee | feat(14-04): annotate interrupt payload with uiKind and add button partial template |
| a867a97 | feat(14-04): SSE interrupt renderer dispatches on uiKind for button vs text |
| f055c43 | feat(14-04): POST /chat/message accepts button_value form field |
| b16054c | test(14-04): backend tests for button interrupt machinery |
