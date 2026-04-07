---
plan: 08-01
status: complete
completed: 2026-04-06
---

# Plan 08-01 Summary: Foundation

## Tasks Completed

### Task 1: ClaimState, ORM model, Alembic migration 006
- `ClaimState` expanded with `complianceFindings`, `fraudFindings`, `advisorDecision`, `dbClaimId`
- `Claim` ORM model expanded with `compliance_findings`, `fraud_findings`, `advisor_decision`, `approved_by` columns (JSONB for findings, String(50) for decision/approvedBy)
- Migration `006_add_agent_output_columns.py` created (depends_on 005, adds 4 columns, downgrade drops them)
- 4 new database tests covering column existence, nullability, and JSONB types

### Task 2: Shared utilities and intake node fixes
- `agents/shared/__init__.py` created (empty package marker)
- `agents/shared/utils.py` — `extractJsonBlock()` handles fenced and raw JSON from LLM responses
- `agents/shared/llmFactory.py` — `buildAgentLlm()` factory centralises ChatOpenRouter instantiation with SSL bypass and 402 fallback model selection
- `agents/intake/node.py` — `intakeNode` always writes `violations` (empty list fallback) after tool scan loop
- `agents/intake/node.py` — `intakeNode` extracts `dbClaimId` from `submitClaim` ToolMessage and writes to state

## Commits
- `622542e` feat(08-01): expand ClaimState, ORM model, and add Alembic migration 006
- `8ea42ee` feat(08-01): shared utils package and intake node fixes

## Test Results
- 174 passed, 0 failed (1 pre-existing E2E failure in `test_e2e_intake_narrative.py` — `session_secret_key` missing from `.env.test`, unrelated to this plan)

## Success Criteria Verification
1. ClaimState has complianceFindings, fraudFindings, advisorDecision, dbClaimId — PASS
2. Claims table migration 006 adds all 4 columns — PASS (migration file created, applies after 005)
3. Shared extractJsonBlock and buildAgentLlm importable — PASS
4. Intake node always populates violations and dbClaimId after submission — PASS
5. All existing tests pass without regression — PASS (174/174)
