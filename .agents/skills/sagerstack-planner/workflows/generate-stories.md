# Generate Stories Workflow

TODO: Detailed story generation sub-workflow (Steps 3-5 of plan-epic).

## Purpose
Handles the BA's story creation process in detail, from proposals through
user-confirmed final stories with complete FR/TR/AC.

## Step 3: Generate Proposals

### BA Inputs
- Epic context from project-context.md
- Research findings from docs/phases/epic-{NNN}-{desc}/research/findings.md

### BA Outputs (Proposals)
- Epic theme and scope (1-2 sentences)
- Story titles with brief descriptions (1-2 sentences each)
- Estimated AI Complexity Score per story (see references/complexity-scoring.md)
- Story dependency overview
- Cost implications identified

## Step 4: User Confirms Direction (Q&A Point 1)

### Presentation Format
```
EP-{NNN} - {Epic Name}

Proposed Epic: {theme}
{1-2 sentence description}

Proposed Stories:
1. {title} - {description} [Complexity: {score}]
2. {title} - {description} [Complexity: {score}]
...

Dependencies: {dependency summary}
Cost Implications: {any costs identified}

Does this direction look right? Any adjustments?
```

### Revision Loop
- User provides feedback
- Team Lead relays to BA
- BA revises proposals
- Team Lead presents revised version
- Repeat until user confirms

## Step 5: Generate Full Artifacts (Q&A Point 2)

### BA Generates
- Epic document using artifact template (saved to epic.md)
- User story documents with full FR/TR/AC (saved to stories/)
- AI Complexity Assessment for each story
- Requirements Clarifications with [INSERT_USER_INPUT] placeholders

### Presentation Format
```
Story Count: {N}
Stories:
1. {title} (FRs: {count}, TRs: {count}, ACs: {count})
2. {title} (FRs: {count}, TRs: {count}, ACs: {count})

Dependency Graph:
{story-001-{desc}} -> {story-002-{desc}} (blocking)
{story-001-{desc}} -> {story-003-{desc}} (prerequisite)

Clarifications Needed:
- Story 001: {question} [INSERT_USER_INPUT]
- Story 003: {question} [INSERT_USER_INPUT]
```

### Revision Loop
- User reviews FR/TR/AC, answers clarifications
- Team Lead relays answers to BA
- BA refines stories, updates status Draft -> Final
- Repeat until user confirms

## References
- SKILL.md <artifact_templates> for Epic and User Story templates
- references/story-patterns.md for FR/TR/AC patterns
- references/epic-template.md for epic creation patterns
- references/complexity-scoring.md for scoring methodology
