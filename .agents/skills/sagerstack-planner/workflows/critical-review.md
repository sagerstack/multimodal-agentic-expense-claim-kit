# Critical Review Workflow

TODO: Detailed critical review sub-workflow (Step 8 of plan-epic).

## Purpose
Handles the Critical Analyst's review of implementation plans, including
refinement cycles with the Solution Architect. Max 2 cycles.

## Step 8: Critical Review

### Critic Receives
- All implementation plan file paths
- All user story file paths (cross-reference)
- Research findings (if applicable)
- Project memory: docs/project_notes/decisions.md, docs/project_notes/bugs.md

### Review Checklist (Per Plan)
1. **FR/TR/AC Alignment** (MANDATORY)
   - Every FR has [FR-N] parent task
   - Every TR has [TR-N] parent task
   - Every AC has [AC-N] parent task with 4 test levels
   - Coverage = 100%

2. **Industry Best Practices**
   - Architecture appropriate for problem
   - Security addressed (auth, validation, secrets)
   - Error handling comprehensive
   - Performance achievable
   - No anti-patterns

3. **Cost Compliance**
   - Budget from Technical Guidance respected
   - No unapproved costs
   - Zero-cost alternatives considered

4. **Cross-Story Integration**
   - Dependencies handled correctly
   - No contract mismatches
   - Integration points defined

5. **API Field Extraction** (if applicable)
   - Field-specific tasks match tech research
   - Validation subtasks exist

6. **Project Memory Consistency**
   - Respects existing decisions
   - Accounts for known bugs
   - No contradictions

### Output
- Critical analysis document per plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-critical-analysis.md
- Use full template if issues found, no-issues template if comprehensive

## Refinement Cycle 1

### If Issues Found
1. Critic sends findings to Team Lead
2. Team Lead routes to Solution Architect with specific issues
3. Architect revises plans IN-PLACE (never creates new file versions)
4. Team Lead sends revised plans back to Critic
5. Critic re-reviews, updates analysis as "2nd Analysis"

### Severity-Based Actions
- **CRITICAL**: Must fix. Architect revises plan.
- **HIGH**: Should fix. Architect revises plan.
- **MEDIUM**: Document for developer. No revision needed.
- **LOW**: Optional. No revision needed.

## Refinement Cycle 2

### If Issues Persist
1. Same flow as Cycle 1
2. After Cycle 2, proceed regardless
3. Document remaining risks in Refinement Tracking

### After Max 2 Cycles
- All remaining issues documented in critical analysis
- Plans proceed to development with documented risks
- Team Lead notifies user of any unresolved concerns

## References
- SKILL.md <workflow_steps> Step 8 for flow details
- references/critical-analysis.md for full template and methodology
- references/quality-standards.md for what constitutes best practices
- references/cost-assessment.md for budget compliance checks
