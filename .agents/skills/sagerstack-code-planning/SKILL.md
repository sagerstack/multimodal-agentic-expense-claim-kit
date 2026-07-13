---
name: sagerstack:code-planning
description: Mandatory planning workflow before writing any code. Use when starting new features, projects, or any implementation work. Ensures alignment on requirements, architecture, and approach before coding begins.
---

<essential_principles>

## How Code Planning Works

This workflow is MANDATORY before writing ANY code. No exceptions.

### 1. Plan Before Code

Every implementation starts with planning:
1. Understand the objective (what and why)
2. Clarify requirements (full lifecycle: pilot → testing → deployment)
3. Confirm architecture decisions
4. Define success criteria (Key Results)
5. THEN write code

### 2. Sequential Discovery

Ask ONE question at a time. Each question offers multiple-choice options with a free-text alternative as the last option. Adapt follow-up questions based on previous answers. Never batch questions.

### 3. OKR-Driven Planning

Planning follows the OKR framework:
- **Objective**: Qualitative goal — the "what" and "why" (gathered from user)
- **Milestones**: Groupings of related work toward the objective
- **Key Results**: Measurable outcomes per milestone (how we know it's working)
- **Epics**: Actionable work units mapped to Key Results

Epics fulfill Key Results. Key Results measure progress toward the Objective.

### 4. Preference Lookup

For each question:
1. Check if a preference exists in `@persona/` files
2. If yes → present as suggested answer
3. If no → ask user directly
4. Record new preferences via detect+confirm protocol

### 5. Output: project-context.md

Planning produces `docs/project-context.md` in the current project:
- Objective statement
- Architecture decisions
- Milestones with Key Results
- Epic breakdown mapped to KRs

</essential_principles>

<intake>
**What would you like to plan?**

1. New project from scratch
2. New feature for existing project
3. Refactor existing code
4. Continue previous planning session

**Wait for response before proceeding.**
</intake>

<routing>
| Response | Workflow |
|----------|----------|
| 1, "new project", "start fresh" | `workflows/plan-new-project.md` |
| 2, "feature", "add", "implement" | `workflows/plan-feature.md` |
| 3, "refactor", "restructure" | `workflows/plan-refactor.md` |
| 4, "continue", "resume" | `workflows/continue-planning.md` |
</routing>

<workflow_steps>

## Planning Process

### Step 1: Load Context
Read `references/questions.md` for the question bank and `references/phase-patterns.md` for milestone/epic patterns.

### Step 2: Sequential Discovery

Ask ONE question at a time. Each question has 2-4 multiple-choice options. The last option is always a free-text alternative.

**Question flow:**

Before asking each question, check `@persona/` files and loaded skills for existing preferences. If a preference exists, present it as a suggested answer the user can confirm or override.

**Core questions (ask in this order, adapt based on answers):**

1. **Project type** — What are we building?
   - Options: CLI tool, Web API, Scheduled job, Library, Other (describe)

2. **Problem** — What problem does this solve?
   - Free-form answer (no multiple choice — this is qualitative input)

3. **End user** — Who uses this?
   - Options: Internal team, External customers, Other developers, Other (describe)

4. **Deployment target** — Where will this run?
   - Options: Local only, AWS Lambda, AWS EKS, Other (describe)
   - Check: skill:deploy-aws for existing patterns

5. **Architecture** — How should we structure the code?
   - Check: skill:software-engineering (Vertical Slice + DDD is the default)
   - If preference exists, confirm: "Your default is Vertical Slice + DDD. Use this?"
   - Options: Vertical Slice + DDD (default), Layered architecture, Other (describe)

6. **Tech stack** — Key technology choices
   - Ask about language, framework, package manager based on project type
   - Check existing skills for defaults (Python, Poetry, pytest, etc.)

7. **Configuration** — What config/secrets are needed?
   - Check: persona/values.md (no hardcoded values)
   - Options: Environment variables only, .env files, AWS Secrets Manager, Other

8. **External dependencies** — Does this integrate with external APIs/services?
   - Options: No external dependencies, Yes (describe which), Not sure yet

**Adaptive follow-ups:**
- If deployment target is AWS → ask about specific services (Lambda, S3, SNS, etc.)
- If external dependencies → ask about authentication, rate limits
- If existing project → ask about current codebase patterns to maintain

**Stop asking when** you have enough context to synthesize an Objective. Don't ask questions whose answers are already known from persona files or skills.

### Step 3: Confirm Objective

Synthesize the user's answers into a clear Objective statement.

**Objective format:**
```
Objective: [Qualitative statement of what we're building and why]
```

**Example:**
```
Objective: Build a Python CLI tool that accepts a name and prints it reversed,
following clean architecture principles, as a test project for the SDLC framework.
```

Present for user confirmation:
```
Based on our discussion, here is the project Objective:

Objective: [statement]

Does this capture what we're building and why? Confirm or refine.
```

Loop until user confirms.

### Step 4: Propose Milestones with Key Results

Based on the confirmed Objective, propose Milestones. Read `references/phase-patterns.md` to select and adapt a template.

**For each Milestone:**
1. Propose the milestone name and what it delivers
2. Define measurable Key Results for this milestone
3. Present for user confirmation

**Key Results are:**
- Measurable, observable outcomes
- How the app behaves or what it delivers after this milestone
- NOT implementation details or task lists

**Format:**
```
Milestone 1: [Name]
Delivers: [What capability becomes available]

Key Results:
- KR-1: [Measurable outcome — what the user can observe]
- KR-2: [Measurable outcome]
- KR-3: [Measurable outcome]

Confirm or adjust?
```

**Example:**
```
Milestone 1: Working CLI
Delivers: A locally-running CLI tool with core functionality

Key Results:
- KR-1: CLI correctly reverses any name input (e.g., "Sagar" → "ragaS")
- KR-2: CLI shows helpful error message when no argument provided
- KR-3: Test coverage >= 90%

Confirm or adjust?
```

Present ONE milestone at a time. After user confirms, proceed to Epic breakdown (Step 5) before proposing the next milestone.

### Step 5: Epic Breakdown per Milestone

After a milestone's Key Results are confirmed, propose the Epic breakdown.

**Read `references/phase-patterns.md` before proposing epics.**

**Key Principles:**
- First milestone produces something runnable locally
- Each epic is a vertical slice (not horizontal layer)
- Core value delivered before infrastructure concerns (auth, logging, etc.)
- Epics map to Key Results — some epics are enabling (no direct KR)

**Format — 3-column table:**
```
Epics for Milestone 1:

| Epic | Task | Key Result |
|------|------|------------|
| E1 | Project Skeleton | — (enabling) |
| E2 | Name Reversal Domain + CLI | KR-1, KR-2 |

Confirm, reorder, or redefine?
```

- **Epic**: Identifier (E1, E2, E3...)
- **Task**: Concise description (3-7 words)
- **Key Result**: Which KR(s) this epic fulfills, or "— (enabling)" for setup work

User can:
- Confirm as-is
- Reorder epics
- Add or remove epics
- Redefine scope

After confirmation, repeat Steps 4-5 for the next milestone.

**Continue until user says:** "All milestones defined" or similar confirmation.

### Step 6: Generate project-context.md

Create `docs/project-context.md` with:

```markdown
# Code Context: [Project Name]
Date: [date]

## Objective
[Qualitative goal statement — the "what" and "why"]

## Architecture
[Text diagram and key decisions]

## Implementation Plan

### Milestone 1: [Name]
- **Delivers**: [Major capability]
- **Why Now**: [Why this milestone before others]

**Key Results:**
- KR-1: [Measurable outcome]
- KR-2: [Measurable outcome]

**Epics:**
| Epic | Task | Key Result |
|------|------|------------|
| E1 | [Task description] | [KR mapping or — (enabling)] |
| E2 | [Task description] | [KR mapping] |

### Milestone 2: [Name]
- **Delivers**: [Major capability]
- **Why Now**: [Ordering rationale]

**Key Results:**
- KR-1: [Measurable outcome]

**Epics:**
| Epic | Task | Key Result |
|------|------|------------|
| E3 | [Task description] | [KR mapping] |

[Continue for all confirmed milestones]

## Decisions Made
[Key choices and rationale from the planning session]
```

### Step 7: Proceed to Implementation

After planning is complete:
1. Run `/sagerstack:planner` to plan one epic at a time
2. Run `/sagerstack:builder` to implement the planned epic
3. Repeat for each epic in milestone order

</workflow_steps>

<reference_index>
## References

All in `references/`:

| File | Purpose |
|------|---------|
| questions.md | Question bank with multiple-choice options by category |
| phase-patterns.md | Milestone/epic structuring patterns, ordering principles, templates |
</reference_index>

<success_criteria>

Planning is complete when:
- [ ] All project-specific questions answered (sequential, one at a time)
- [ ] Technical preferences confirmed or captured
- [ ] Objective statement confirmed by user
- [ ] Milestones defined with measurable Key Results
- [ ] Epic breakdown per milestone confirmed (table with KR mapping)
- [ ] Phase patterns applied (local-first, vertical slices, core value before infrastructure)
- [ ] `docs/project-context.md` created with Objective, Milestones, KRs, and Epics
- [ ] Ready to proceed with `/sagerstack:planner`

</success_criteria>
