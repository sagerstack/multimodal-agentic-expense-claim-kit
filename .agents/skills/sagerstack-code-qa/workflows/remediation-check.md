# Workflow: Remediation Check

## Purpose

Re-validation workflow after the Developer has fixed issues identified in a previous QA report. Focuses on the specific failures that were remediated while still running the full validation to catch regressions.

## TODO: Implementation Details

This workflow will contain the step-by-step execution guide for post-remediation re-validation:

1. **Read Previous QA Report**
   - Load the previous QA report from docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md
   - Extract the Failure-to-Task Mapping section
   - Identify which failures were targeted for remediation

2. **Targeted Validation**
   - For each previously failed AC: Re-run the specific test
   - For coverage gaps: Re-run coverage report, check specific files
   - For quality check failures: Re-run the specific failed check
   - For UAT failures: Re-run the specific failed scenario

3. **Full Regression Check**
   - Re-run full test suite (ensure fixes did not break other tests)
   - Re-run full coverage report (ensure overall coverage still >= 90%)
   - Re-run all 9 quality checks

4. **Comparison**
   - Compare new results against previous QA report
   - Identify: Fixed issues, remaining issues, new regressions
   - Track remediation iteration count (max 2 before escalation)

5. **Updated Report Generation**
   - Generate new QA report (replaces or supplements previous)
   - If all pass: PASS report with note "Passed after remediation (iteration N)"
   - If still failing: FAIL report with updated Failure-to-Task Mapping
   - Include diff: what changed between iterations

6. **Escalation Check**
   - If this is remediation iteration 2 and still failing:
     - Include escalation recommendation in report
     - Suggest manual intervention for remaining issues
   - Send results to Team Lead with clear pass/fail and iteration count

7. **Project Memory Update**
   - Update bugs.md with resolved bugs (mark as fixed)
   - Update bugs.md with any new bugs discovered during regression
   - Update issues.md with remediation status
