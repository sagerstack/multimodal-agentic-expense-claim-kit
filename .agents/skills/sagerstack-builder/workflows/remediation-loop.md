# Workflow: Remediation Loop

TODO: Detailed step-by-step workflow for handling QA failures with targeted remediation.

## Scope

This workflow covers the QA failure remediation cycle:

1. **QA Report Analysis**: Team Lead reads the QA report, extracts Failure-to-Task Mapping section
2. **Remediation Task Creation**: For each failure cluster, create a targeted remediation task in TaskList with:
   - Specific file and line reference
   - Related impl plan task ID
   - Expected behavior after fix
   - Test that must pass after fix
3. **Developer Assignment**: Assign remediation tasks to Developer with precise fix instructions
4. **Developer Fixes**: Developer implements targeted fixes following TDD (write/update failing test, then fix code)
5. **Re-validation**: After all remediation tasks complete, re-assign QA for FULL story re-validation (not just fixed areas)
6. **Retry Tracking**: Track retry count per story. Maximum 2 retries.
7. **Escalation**: If QA still fails after 2 retries, escalate to user with full context

## Remediation Task Format

```
TaskCreate(
  subject="[US-{NNN}] Remediation: {failure description}",
  description="Fix: {specific issue}
    Source: {file}:{line}
    Related task: [X.0][CATEGORY]
    Expected: {correct behavior}
    Test: {test that must pass after fix}
    QA Report: docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md"
)
```

## Failure Categories and Fix Strategies

- **Test failure**: Developer fixes code or test logic
- **Coverage gap**: Developer adds tests for uncovered lines (identified in QA report)
- **Type error**: Developer adds/fixes type annotations
- **Lint violation**: Developer fixes code style
- **Security issue**: Developer addresses Bandit findings
- **UAT failure**: Developer fixes endpoint behavior
- **AC failure**: Developer traces AC to FR/TR and fixes implementation

## Key Rules

- Remediation is TARGETED, not broad rework
- QA re-validates the FULL story, not just fixed areas
- Each retry creates NEW remediation tasks (not re-using old ones)
- Retry count resets per story (not cumulative across stories)

## References

- SKILL.md workflow_steps Step 4d (Handle QA results)
- references/escalation-protocol.md (Category 1: QA Failure)
- Architecture doc Section 6.3 (Remediation Protocol)
