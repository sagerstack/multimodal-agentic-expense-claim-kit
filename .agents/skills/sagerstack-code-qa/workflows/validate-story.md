# Workflow: Validate Story

## Purpose

Full story validation workflow: AC parsing, test execution, quality pipeline, code quality inspection, UAT, and report generation.

## TODO: Implementation Details

This workflow will contain the step-by-step execution guide for full story validation:

1. **Preparation Phase**
   - Read user story and extract AC table
   - Read impl plan for task-to-code mapping
   - Read project memory (bugs.md, decisions.md)
   - Scan codebase to identify test structure and source layout

2. **AC Validation Phase**
   - Parse each AC from the table (see references/ac-parsing.md)
   - Locate corresponding tests via Grep/Glob
   - Run each test independently and record results
   - Generate AC Results table

3. **Quality Pipeline Phase**
   - Execute 9-check pipeline sequentially (see references/quality-checklist.md)
   - Record all results regardless of pass/fail
   - Capture evidence for failed checks

4. **Code Quality Inspection Phase**
   - CamelCase naming verification
   - Domain purity check
   - No hardcoded values check
   - Vertical slice structure verification
   - Data quality policy compliance

5. **UAT Phase**
   - Detect execution model (Docker vs local vs skip)
   - Execute UAT scenarios from E2E ACs (see references/uat-patterns.md)
   - Record HTTP assertion results

6. **Report Generation Phase**
   - Compile all results into QA report (PASS or FAIL format)
   - Generate Failure-to-Task Mapping if failures exist
   - Write report to docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md
   - Update project memory (bugs.md, issues.md)
   - Send results to Team Lead via SendMessage

7. **Cross-Agent Validation Phase**
   - Apply cross-agent validation rules (see references/cross-agent-validation.md)
   - Verify developer output meets Solution Architect's intent
   - Flag suspicious results and anti-patterns
