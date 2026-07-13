# Critical Analysis Methodology

Reference for the Critical Analyst when reviewing implementation plans. Extracted and adapted from the critical-analysis artifact template.

---

## Purpose

The Critical Analysis serves as a comprehensive review document that identifies production issues, gaps, dangerous assumptions, and challenges in implementation plans BEFORE development begins. It acts as a quality gate to prevent costly mistakes.

### Key Objectives
- **Risk Identification**: Uncover hidden assumptions and potential failure points
- **Guidance Compliance**: Verify adherence to user-specified technical constraints
- **Cost Validation**: Confirm budget constraints are respected
- **Production Readiness**: Identify gaps preventing successful deployment
- **FR/TR/AC Alignment**: Ensure 100% coverage between user story and impl plan

---

## What You Review

**Input**: Implementation plans at `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md`
**Cross-reference**: User stories at `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md`
**Cross-reference**: Research at `docs/phases/epic-{NNN}-{desc}/research/` (if applicable)
**Cross-reference**: Project memory at `docs/project_notes/decisions.md` and `docs/project_notes/bugs.md`

You review IMPLEMENTATION PLANS, not user stories. The user stories are your cross-reference for validation.

---

## Review Checklist

### 1. FR/TR/AC Alignment (MANDATORY)
- [ ] Every FR in the user story has a corresponding `[{X}.0][FR-N]` parent task
- [ ] Every TR has a corresponding `[{X}.0][TR-N]` parent task
- [ ] Every AC has a corresponding `[{X}.0][AC-N]` parent task
- [ ] Every AC task includes all 4 test levels (unit, integration, E2E, live)
- [ ] Requirements Coverage Validation section shows 100% mapping
- [ ] No FR/TR/AC is missing from the plan

### 2. Industry Best Practices
- [ ] Architecture patterns appropriate for the problem domain
- [ ] Security considerations addressed (auth, input validation, secrets)
- [ ] Error handling is comprehensive (not just happy path)
- [ ] Performance requirements achievable with proposed approach
- [ ] No anti-patterns (hardcoded values, tight coupling, missing validation)
- [ ] Testing strategy covers edge cases and failure modes

### 3. Cost Compliance
- [ ] Budget constraints from Technical Guidance respected
- [ ] No unexpected cost escalation beyond what user approved
- [ ] Zero/low-cost alternatives considered where applicable

### 4. Cross-Story Integration
- [ ] Dependencies between stories properly handled
- [ ] No contract mismatches between story outputs/inputs
- [ ] Integration points clearly defined

### 5. API Field Extraction (if applicable)
- [ ] If tech research has API Research section, plan has field-specific tasks
- [ ] Field paths match tech research exactly
- [ ] Validation subtasks exist for extracted fields

### 6. Project Memory Consistency
- [ ] Plan respects existing architectural decisions from `docs/project_notes/decisions.md`
- [ ] Plan accounts for known bugs from `docs/project_notes/bugs.md`
- [ ] No contradictions with established project patterns

---

## Severity Levels

| Severity | Definition | Action Required |
|----------|-----------|-----------------|
| **CRITICAL** | Must fix before development. Blocks implementation. | Solution Architect MUST revise |
| **HIGH** | Should fix during refinement. Causes significant risk. | Strongly recommend revision |
| **MEDIUM** | Recommend addressing. Causes moderate risk. | Document for developer awareness |
| **LOW** | Nice to have. Minimal risk. | Optional improvement |

---

## Full Template (Issues Found)

Use when ANY Critical Issues, High-Risk Assumptions, or gaps are identified.

```markdown
# Critical Analysis

## Metadata
| Field | Value |
|-------|-------|
| ID | US-{NNN}-CRITICAL-ANALYSIS |
| User Story ID | US-{NNN} |
| Implementation Plan ID | US-{NNN}-IMPL-PLAN |
| Created | {YYYY-MM-DD HH:mm:ss} |
| Last Updated | {YYYY-MM-DD HH:mm:ss} |
| Analysis Iteration | {1st Analysis / 2nd Analysis} |
| Confidence Level | {High / Medium / Low} |

## Executive Summary
{2-3 paragraphs highlighting most critical findings. Focus on blockers and high-risk items.}

## Technical Solution Guidance Compliance

### Technology Stack Alignment
| Specified in Story | Used in Plan | Compliance | Impact if Changed |
|--------------------|--------------|------------|-------------------|
| {Tech} | {What plan uses} | {pass/warn/fail} | {Risk} |

### Architecture Pattern Compliance
| Pattern Type | Story Guidance | Plan Implementation | Compliance |
|--------------|---------------|-------------------|------------|
| Patterns to Use | {Specified} | {How plan implements} | {pass/warn/fail} |
| Patterns to Avoid | {Anti-patterns} | {Any violations} | {pass/warn/fail} |

### Budget Compliance
| Cost Category | Budget Constraint | Projected Cost | Within Budget | Risk |
|---------------|------------------|----------------|---------------|------|
| {Category} | {$X/month} | {$Y/month} | {Yes/No} | {Level} |

## Critical Issues (Blockers)

### Issue 1: {Title}
- **Severity**: CRITICAL
- **Description**: {Detailed explanation}
- **Evidence**: {Specific examples from the plan}
- **Impact**: {What fails in production}
- **Recommendation**: {Specific fix required}
- **Addressed in Refinement**: {Yes/No}

## High-Risk Assumptions

### Assumption 1: {Description}
- **Risk Level**: HIGH
- **Current Assumption**: {What the plan assumes}
- **Reality Check**: {What actually happens}
- **Validation Method**: {How to verify}
- **Fallback Plan**: {What to do if false}
- **Addressed in Refinement**: {Yes/No}

## Scalability Analysis

### Data Volume Projections
| Metric | Plan Assumption | Realistic Estimate | Gap | Risk |
|--------|----------------|-------------------|-----|------|
| {Metric} | {Assumed} | {Realistic} | {Delta} | {Level} |

### Performance Bottlenecks
| Component | Expected | Likely Reality | Impact |
|-----------|----------|----------------|--------|
| {Component} | {Expected} | {Likely} | {Impact} |

## Third-Party Integration Risks

### {Service Name}
- **Integration Method**: {REST/WebSocket/Webhook}
- **Rate Limits**: {Plan assumption vs documented limits}
- **Cost Model**: {Per request/monthly/tiered}
- **Reliability Concerns**: {SLA gaps, downtime history}
- **Fallback Strategy**: {Exists: Yes/No}

## Missing Production Requirements

### Operational Readiness Gaps
- [ ] **Monitoring**: {What's missing}
- [ ] **Alerting**: {Missing alert scenarios}
- [ ] **Disaster Recovery**: {Missing DR components}

### Security Gaps
- [ ] **Authentication**: {Concerns}
- [ ] **Data Protection**: {Issues}

## Recommendations Priority Matrix

### Must Fix Before Development
1. **{Issue}**: {Why blocker + specific fix}

### Should Address During Refinement
1. **{Issue}**: {Impact + recommended approach}

### Can Defer (Document for Future)
1. **{Issue}**: {Why deferrable + when to address}

## Research & Validation

### Sources Consulted
- {Production system examples}
- {Official documentation}
- {Industry benchmarks}

## Refinement Tracking

### First Refinement Cycle
- **Issues Addressed**: {List}
- **Issues Remaining**: {List}
- **New Issues Found**: {List}

### Second Refinement Cycle
- **Issues Addressed**: {List}
- **Issues Remaining**: {List}
- **Assessment**: {Overall improvement}

## Changelog
| Date | Author | Change Summary | Analysis Type |
|------|--------|----------------|---------------|
| {Date} | Critical Analyst | Initial analysis | 1st Analysis |
| {Date} | Critical Analyst | Updated after refinement | 2nd Analysis |
```

---

## No Issues Template (Plan is Comprehensive)

Use when plan fully addresses all requirements with no gaps.

```markdown
# Critical Analysis

## Metadata
| Field | Value |
|-------|-------|
| ID | US-{NNN}-CRITICAL-ANALYSIS |
| User Story ID | US-{NNN} |
| Implementation Plan ID | US-{NNN}-IMPL-PLAN |
| Created | {YYYY-MM-DD HH:mm:ss} |
| Last Updated | {YYYY-MM-DD HH:mm:ss} |
| Analysis Iteration | 1st Analysis |
| Confidence Level | High |

## Executive Summary
Implementation plan comprehensively addresses all user story requirements, acceptance criteria, and functional requirements. No critical issues, high-risk assumptions, or missing production requirements identified. Plan is ready for development.

## Technical Solution Guidance Compliance
Full compliance with user story technical guidance:

| Specified in Story | Used in Plan | Compliance | Notes |
|--------------------|--------------|------------|-------|
| {Tech Stack} | {As specified} | pass | Matches requirements |
| {Architecture} | {As specified} | pass | Correctly applied |
| {Budget} | {Within limits} | pass | Budget respected |

## Recommendations Priority Matrix

### Should Address During Development
*Optional enhancements (non-blocking):*
1. **{Enhancement}**: {Brief description if any}

*If none: "No recommendations. Implementation plan is ready for development."*

## Refinement Tracking
No refinement required -- plan comprehensively addresses all requirements on first iteration.

## Changelog
| Date | Author | Change Summary | Analysis Type |
|------|--------|----------------|---------------|
| {Date} | Critical Analyst | Comprehensive validation, no gaps | 1st Analysis |
```

### When to Use No Issues Template
- All acceptance criteria fully addressed
- All FR/TR mapped to parent tasks
- No critical issues or high-risk assumptions
- No missing production requirements
- Budget compliance confirmed

### When NOT to Use No Issues Template
- Any AC missing or incomplete coverage
- Any critical issues identified
- Any high-risk assumptions present
- Budget violations detected

---

## Refinement Protocol

### Cycle 1
1. Critical Analyst completes initial review (1st Analysis)
2. If issues found: sends findings to Team Lead
3. Team Lead routes to Solution Architect
4. Solution Architect revises impl plan in-place (never creates new version)
5. Team Lead sends revised plan back to Critical Analyst
6. Critical Analyst re-reviews, updates Refinement Tracking (2nd Analysis)

### Cycle 2
1. Same flow as Cycle 1
2. After Cycle 2, proceed regardless with documented risks
3. Update Refinement Tracking with remaining concerns

### Max 2 Cycles
After 2 refinement cycles, the plan proceeds to development. Any remaining risks are documented in the Refinement Tracking section for developer awareness.

---

## Common Critical Issues

| Category | Common Issues |
|----------|--------------|
| **Coverage Gaps** | FR without parent task, AC missing test levels, TR not addressed |
| **Anti-patterns** | Hardcoded values, missing error handling, tight coupling |
| **Cost Violations** | Exceeding approved budget, using paid service without approval |
| **Integration Risks** | Missing fallback for external APIs, rate limit assumptions |
| **Security Gaps** | Missing auth, secrets in code, unvalidated input |
| **Performance** | Unrealistic latency targets, missing caching strategy |
