# Generate Implementation Plan Workflow

TODO: Detailed implementation plan generation sub-workflow (Steps 6-7 of plan-epic).

## Purpose
Handles the Solution Architect's implementation plan generation, including
technical Q&A with the user and plan creation with 100% FR/TR/AC coverage.

## Step 6: Technical Q&A (Q&A Point 3)

### Architect Receives
- User story file paths (docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md)
- Research findings (docs/phases/epic-{NNN}-{desc}/research/findings.md)
- Technical Guidance sections from user stories (initially [INSERT_USER_INPUT])

### Architect Questions May Include
- Technology stack preferences not in project-context.md
- Cost trade-offs between paid/free alternatives
- Architecture decisions (e.g., sync vs async, monolith vs microservice)
- Infrastructure preferences (Docker, Kubernetes, serverless)
- External API choices when multiple options exist

### Cost Flags (MANDATORY)
For every non-zero cost identified:
```
COST FLAG:
- Item: {name}
- Monthly cost: ${amount}
- Alternative: {zero/low cost option}
- Trade-off: {what is lost}
- Recommendation: {architect's recommendation}
```

### Presentation Format
```
Technical Questions for EP-{NNN}:

Questions:
1. {question about tech choice}
2. {question about architecture}

Cost Considerations:
COST FLAG: {flag 1}
COST FLAG: {flag 2}

Please provide answers so we can generate implementation plans.
```

### User Answers
- Team Lead collects answers
- Relays to Solution Architect
- Architect proceeds with plan generation

## Step 7: Generate Plans

### For Each User Story, Architect:
1. Reads FR/TR/AC from story document
2. Reads research findings
3. If external APIs involved:
   - Generates tech research: docs/phases/epic-{NNN}-{desc}/research/story-{NNN}-{desc}-tech-research.md
   - Documents API endpoints, field mappings, auth methods
4. Generates implementation plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md

### Plan Quality Gates (BLOCKING)
- Requirements Coverage Validation shows 100% FR/TR/AC mapping
- Every AC has 4 test levels (unit, integration, E2E, live)
- All API field extraction tasks reference exact field paths from tech research
- All costs flagged and user-approved
- Subtasks scoped to 15-30 min each

### Project Memory Updates
Architect writes to docs/project_notes/decisions.md:
- Technology choices made during this epic
- Architecture patterns selected
- Trade-offs considered and rationale

## References
- SKILL.md <artifact_templates> for Implementation Plan template
- references/impl-plan-patterns.md for task structure and markers
- references/cost-assessment.md for cost flagging protocol
- references/quality-standards.md for quality constraints plans must satisfy
