# Epic Template Patterns

Reference for the Business Analyst when creating epics. Extracted and adapted from the epic-artifact template.

---

## Purpose

Epics define outcome-focused capabilities that group related user stories and establish clear business value delivery. They bridge strategic planning (project-context.md epics) and implementable user stories.

### Key Objectives
- **Capability Definition**: Define outcome-focused capabilities with measurable value
- **Story Grouping**: Organize related user stories around common outcomes
- **Strategic Alignment**: Ensure development advances epic objectives
- **Value Framework**: Establish clear success criteria and measurement

---

## Epic ID Convention

Format: `EP-{NNN}` where NNN is a zero-padded three-digit number.
- Epic 1 -> `EP-001`
- Epic 2 -> `EP-002`
- Epic 12 -> `EP-012`

Each epic maps to exactly one epic document.

---

## Epic Overview Section

Three mandatory fields:

| Field | Purpose | Good Example | Bad Example |
|-------|---------|--------------|-------------|
| **What** | Clear capability description | "REST API for order management with CRUD operations and validation" | "Order stuff" |
| **Why** | Business value and strategic importance | "Enables programmatic access to order system, required for epic EP-002 integration" | "Because we need it" |
| **Success** | Measurable completion criteria | "All CRUD endpoints respond < 200ms, 90%+ test coverage, Docker deployment works" | "It works" |

---

## Story Portfolio Overview

Table format for all stories in the epic:

| Column | Values | Purpose |
|--------|--------|---------|
| ID | US-{NNN} | Story identifier |
| Title | Descriptive 3-5 words | Quick reference |
| Status | Draft / Final | Lifecycle tracking |
| Priority | Must-have / Should-have / Could-have | Prioritization |
| AI Complexity Score | 1-10 | Effort estimation |
| Business Value | Brief description | Value justification |

### Priority Definitions

| Priority | Meaning | Rule |
|----------|---------|------|
| **Must-have** | Epic fails without this story | Always include in epic |
| **Should-have** | Significant value but epic can ship without | Include if capacity allows |
| **Could-have** | Improves experience but not critical | Defer if time-constrained |

---

## Dependency Types and Sequencing

### Three Dependency Types

| Type | Definition | Sequencing Impact | Example |
|------|-----------|-------------------|---------|
| **Blocking** | Story B blocks Story A completion | B must finish before A starts | "Data model" blocks "API endpoints" |
| **Prerequisite** | Story B is prerequisite for A | A can start when B is 50%+ complete | "Auth service" prerequisite for "Protected routes" |
| **Informational** | Story B informs Story A design | No sequencing impact | "Caching strategy" informs "Query optimization" |

### Sequencing Priority Calculation

| Priority | Rule | Start Condition |
|----------|------|-----------------|
| **P1 (Foundation)** | No blocking dependencies | Immediately |
| **P2 (Mid-Layer)** | Depends on 1-2 P1 stories | When dependencies 50%+ complete |
| **P3 (High-Layer)** | Depends on 3+ stories or P2 stories | When dependencies 75%+ complete |

### Data Flow Dependency Patterns

| Pattern | Rule | Example |
|---------|------|---------|
| **Data Foundation** | Mapping/normalization MUST precede consumption | Token Mapping -> Cross-Chain Arbitrage |
| **Integration** | Network/API connections precede data processing | Network Integration -> DEX Integration |
| **Business Logic** | Core algorithms precede optimization | Price Discovery -> Route Optimization |

### Dependency Validation Checklist
- [ ] All blocking dependencies identified with "Blocking" type
- [ ] Dependent stories documented with impact explanation
- [ ] Sequencing justification provided
- [ ] Cross-story integration points defined
- [ ] No circular dependencies (A -> B -> A is deadlock)
- [ ] Dependency resolution timeline estimated

---

## External Dependencies

Document for each category:

| Category | What to Document |
|----------|-----------------|
| **System Dependencies** | Third-party APIs, external services, infrastructure |
| **Data Dependencies** | Data sources, reference data, authoritative systems |
| **Technology Dependencies** | Required frameworks, libraries, tools |

---

## Epic-Level Acceptance Criteria

Four acceptance areas:

| Area | Focus |
|------|-------|
| **Functional** | All must-have stories complete with ACs passing |
| **User Experience** | UX quality meets expectations |
| **Performance** | Response times, throughput within targets |
| **Business** | Business value delivered, stakeholder satisfied |

### Definition of Done (Epic Level)
- [ ] All must-have user stories completed and accepted
- [ ] Epic success criteria validated
- [ ] Epic success criteria from project-context.md met
- [ ] All implementation plans fully executed

---

## Risk Assessment

### Risk Documentation Format

For each identified risk:

```markdown
**Risk: {Description}**
- **Probability**: High / Medium / Low
- **Impact**: High / Medium / Low
- **Mitigation**: {Proactive strategy to reduce probability}
- **Contingency**: {Reactive plan if risk materializes}
```

### Common Epic Risks

| Risk Category | Common Risks |
|--------------|-------------|
| **Technical** | API changes, library incompatibilities, performance constraints |
| **Integration** | External service unavailability, rate limits, cost overruns |
| **Scope** | Requirements creep, underestimated complexity |
| **Dependencies** | Blocked by other stories, external team delays |

---

## Open Questions

Track questions that need user/stakeholder input:

| Column | Purpose |
|--------|---------|
| Question | Specific, answerable question |
| Priority | High / Medium / Low |
| User Response | `[INSERT_USER_RESPONSE_HERE]` placeholder |
| Owner | Who needs to answer |
| Timeline | When answer is needed |

### Good Open Questions
- "Should webhooks retry on 5xx errors or only on timeouts?"
- "Is the $30/month API subscription within budget for this epic?"
- "Should rate limiting apply per-user or per-API-key?"

### Bad Open Questions
- "What should we build?" (too broad)
- "Is this good?" (not specific)
