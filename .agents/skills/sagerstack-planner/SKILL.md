---
name: sagerstack:planner
description: SDLC planning skill that spawns a 4-member agent team to plan one epic at a time from project-context.md. Produces epics, user stories with FR/TR/AC, implementation plans, and critical analyses. Use when planning an epic for full SDLC execution with agent teams.
---

<essential_principles>

## How Epic Planning Works

These principles ALWAYS apply when planning an epic.

### 1. Epic-at-a-Time

Plan ONE epic from `docs/project-context.md` per invocation. Never plan multiple epics simultaneously. Each epic produces a complete artifact set before moving to the next.

Input: `docs/project-context.md` (from `/sagerstack:code-planning`)
Output: `docs/phases/epic-{NNN}-{desc}/` with epic, stories, plans, research, critical analyses

### 2. Research-First (Default)

Research is the default mode. The Researcher investigates the epic BEFORE the BA creates stories. Research findings inform story creation, complexity scoring, and technical decisions.

When `--skip-research` flag is passed:
- Researcher agent is NOT spawned
- Solution Architect does NOT use WebSearch/WebFetch tools
- Planning proceeds from codebase analysis + project-context.md only
- Use for straightforward epics with well-understood requirements

### 3. User Q&A at Decision Points

Three mandatory Q&A points where the user MUST confirm before proceeding:
- **Q&A 1 (Step 4)**: Confirm epic/story direction from BA proposals
- **Q&A 2 (Step 5)**: Confirm story breakdown with FR/TR/AC details
- **Q&A 3 (Step 6)**: Answer technical questions and approve costs from Solution Architect

### 4. Cost-Conscious Architecture

Solution Architect MUST flag ALL non-zero costs and prefer zero/low-cost solutions. Cost flags require explicit user approval before proceeding.

Cost Flag Format:
```
COST FLAG:
- Item: {service/tool/subscription name}
- Monthly cost: ${amount}
- Alternative: {zero-cost or lower-cost alternative}
- Trade-off: {what is lost with cheaper option}
- Recommendation: {architect's recommendation}
```

### 5. Critical Review After Implementation Plans

Critical Analyst reviews IMPLEMENTATION PLANS (not user stories), AFTER they are generated. Reviews check:
- FR/TR/AC alignment (100% coverage required)
- Industry best practices compliance
- Cost compliance with user-approved budget
- Cross-story integration correctness

Max 2 refinement cycles. After 2nd cycle, proceed with documented risks.

### 6. Project Memory Integration

Agents read and write to project memory files:
- BA reads `docs/project_notes/decisions.md` + `docs/project_notes/issues.md`
- Solution Architect reads/writes `docs/project_notes/decisions.md` + `docs/project_notes/key_facts.md`
- Critical Analyst reads `docs/project_notes/decisions.md` + `docs/project_notes/bugs.md`

### 7. Epic Management

The BA can modify `docs/project-context.md` at user request:
- Insert new epics (renumber subsequent)
- Remove epics (renumber subsequent)
- Reorder epics within milestones
- Split or merge epics

</essential_principles>

<intake>

**Epic Planning Intake**

1. Read `docs/project-context.md` to identify available epics
2. Present the epic list to the user

**Which epic would you like to plan?**

Options:
- Specify an epic (e.g., "epic 001", "epic 002")
- "Next" to plan the next unplanned epic
- "Manage epics" to insert, remove, reorder, split, or merge epics

**Optional flags:**
- `--skip-research` — Skip research phase and architect web research. Use for straightforward epics with well-understood requirements.

**Wait for response before proceeding.**

</intake>

<routing>

| Response | Action |
|----------|--------|
| Epic number (e.g., "001", "epic 002") | Read `workflows/plan-epic.md`, execute planning workflow for specified epic |
| "next", "next epic", "continue" | Identify next unplanned epic from project-context.md, execute planning workflow |
| "manage", "manage epics", "insert", "remove", "reorder", "split", "merge" | Read `workflows/manage-phases.md`, execute epic management |
| "stories", "generate stories" | Read `workflows/generate-stories.md` (story generation sub-workflow) |
| "plans", "impl plans", "implementation plans" | Read `workflows/generate-impl-plan.md` (impl plan sub-workflow) |
| "review", "critical review" | Read `workflows/critical-review.md` (critical review sub-workflow) |
| "hotfix", "bugfix", "bug fix", "fix bug" | Read `workflows/hotfix.md`, execute hotfix workflow |

</routing>

<team_configuration>

## Agent Team Setup

### Team Identity
- **Team name**: `planner-epic-{NNN}` (e.g., `planner-epic-001`)
- **Description**: "Planning epic EP-{NNN}: {epic name from project-context.md}"

### Team Members

#### 1. Researcher
- **Subagent type**: `planner-researcher`
- **Model**: sonnet
- **Permission mode**: acceptEdits
- **Tools**: Read, Glob, Grep, WebSearch, WebFetch, SendMessage, TaskUpdate, TaskList, Write
- **Skills**: (none)
- **Max turns**: 50
- **Purpose**: Investigates epic requirements by searching codebase and researching external APIs/services
- **Skip-Research Note**: NOT spawned when `--skip-research` flag is active. All research-related tasks are skipped.

#### 2. Business Analyst
- **Subagent type**: `planner-ba`
- **Model**: opus
- **Permission mode**: acceptEdits
- **Tools**: Read, Write, Edit, Glob, Grep, SendMessage, TaskUpdate, TaskList
- **Skills**: sagerstack:code-planning, project-memory
- **Max turns**: 80
- **Purpose**: Creates epics and user stories with FR/TR/AC, manages epic lifecycle

#### 3. Solution Architect
- **Subagent type**: `planner-architect`
- **Model**: opus
- **Permission mode**: acceptEdits
- **Tools**: Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, SendMessage, TaskUpdate, TaskList
- **Skills**: project-memory
- **Max turns**: 80
- **Purpose**: Generates implementation plans with 100% FR/TR/AC coverage, flags costs
- **Skip-Research Note**: Do NOT use WebSearch/WebFetch when `--skip-research` flag is active. Work from codebase analysis, project-context.md, and user story artifacts only.

#### 4. Critical Analyst
- **Subagent type**: `planner-critic`
- **Model**: opus
- **Permission mode**: acceptEdits
- **Tools**: Read, Glob, Grep, WebSearch, WebFetch, SendMessage, TaskUpdate, TaskList, Write
- **Skills**: project-memory
- **Max turns**: 50
- **Purpose**: Reviews implementation plans for alignment with user stories and best practices

</team_configuration>

<workflow_steps>

## Planning Workflow (9 Steps)

### Step 1: Read Epic and Create Team

**Actor**: Team Lead (you)

1. Read `docs/project-context.md`
2. Extract the target epic:
   - Epic name and description
   - Definition of Done criteria
   - Success Criteria
   - Milestone context (what this epic contributes to)
   - Any relevant E2E test definitions
3. Create the team: `TeamCreate(team_name="planner-epic-{NNN}")`
4. Spawn all 4 teammates with full epic context in their spawn prompts

### Step 2: Research Epic

**Actor**: Team Lead delegates to Researcher

**If `--skip-research` is active:** Skip this step entirely. Do not spawn the Researcher agent. Proceed directly to Step 3. Note in epic metadata that research was skipped.

**Default (research enabled):**

1. Create task: "Research epic EP-{NNN} requirements"
2. Send message to Researcher with:
   - Full epic context from project-context.md
   - What to investigate (technologies, APIs, services, patterns)
   - Specific research questions derived from epic scope
3. Researcher investigates using read-only tools (Glob, Grep, Read, WebSearch, WebFetch)
4. Researcher saves findings to `docs/phases/epic-{NNN}-{desc}/research/findings.md`
5. Researcher reports back to Team Lead

**Research Output Format** (saved to `docs/phases/epic-{NNN}-{desc}/research/findings.md`):
```markdown
# Research Findings: EP-{NNN} - {Epic Name}

## Date
{YYYY-MM-DD}

## Research Scope
{What was investigated and why}

## Codebase Analysis
### Existing Patterns
{Relevant code patterns found in the project}

### Reusable Components
{Existing code that can be leveraged}

### Technical Debt
{Relevant tech debt that may impact this epic}

## External Technology Research
### {Technology/API/Service Name}
- **Purpose**: {Why this is relevant}
- **Documentation**: {URLs}
- **Key Capabilities**: {What it provides}
- **Limitations**: {Constraints, rate limits}
- **Cost**: {Free / $X per month / usage-based}
- **Alternatives**: {Other options considered}

## Integration Requirements
{How components need to connect}

## Technical Risks
{Identified risks and concerns}

## Recommendations
{Suggested approaches based on research}
```

### Step 3: Generate Proposals

**Actor**: Team Lead delegates to BA

1. Send BA the epic context + research findings
2. BA generates proposals containing:
   - Proposed epic theme and scope
   - Proposed user story titles with brief descriptions
   - Estimated complexity per story (using AI Complexity Scoring - see `references/complexity-scoring.md`)
   - Cost implications flagged
3. BA sends proposals to Team Lead

### Step 4: User Confirms Direction (Q&A Point 1)

**Actor**: Team Lead presents to user

Present the BA's proposals to the user:
- Epic theme and scope
- Story titles with brief descriptions
- Complexity estimates
- Any cost implications

Ask: "Does this direction look right? Any adjustments to scope, stories, or priorities?"

**Loop**: If user requests adjustments, send feedback to BA, who revises. Repeat until user confirms.

### Step 5: Generate Epic and Stories, User Confirms (Q&A Point 2)

**Actor**: Team Lead delegates to BA, then presents to user

1. After direction confirmed, instruct BA to generate full artifacts:
   - Epic document (saved to `docs/phases/epic-{NNN}-{desc}/epic.md`)
   - User story documents (saved to `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md`)
2. BA generates using templates below (Epic Template, User Story Template)
3. Team Lead presents to user:
   - Story count and titles
   - Story dependency graph
   - FR/TR/AC summary per story
   - Any Requirements Clarifications with `[INSERT_USER_INPUT]` placeholders
4. User confirms or requests changes

Ask: "Here is the story breakdown. Are the FR/TR/AC complete? Any clarifications needed?"

**Loop**: If user requests changes, send to BA for revision. Repeat until confirmed. BA updates status from Draft to Final.

### Step 6: Technical Q&A with User (Q&A Point 3)

**Actor**: Team Lead delegates to Solution Architect, then presents to user

1. Assign impl plan generation to Solution Architect with:
   - User story file paths
   - Research findings file path
   - Technical Guidance section from user stories
2. Before generating plans, Solution Architect may have questions about:
   - Technology choices
   - Cost trade-offs
   - Architecture decisions not in project-context.md
   - Infrastructure preferences
3. Solution Architect sends questions to Team Lead
4. Team Lead presents questions AND cost flags to user
5. User provides answers, Team Lead relays back

Ask: "The Solution Architect has the following technical questions and cost considerations before generating implementation plans:"

### Step 7: Generate Implementation Plans

**Actor**: Solution Architect

After receiving user answers:

**If `--skip-research` is active:**
- Solution Architect works from codebase analysis + project-context.md + user story artifacts only
- Do NOT use WebSearch or WebFetch tools
- Do NOT generate tech research documents (no `story-{NNN}-{desc}-tech-research.md`)
- Skip reading research/findings.md (does not exist)

**Default (research enabled):**

1. For each user story, Solution Architect:
   - Reads FR/TR/AC from the story
   - Reads research findings
   - Generates tech research document if external APIs involved (saved to `docs/phases/epic-{NNN}-{desc}/research/story-{NNN}-{desc}-tech-research.md`)
   - Generates implementation plan (saved to `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md`)
   - Ensures 100% FR/TR/AC mapping in Requirements Coverage Validation
   - Includes API Field Extraction tasks where applicable
   - Flags all costs
2. Solution Architect writes ADR entries to `docs/project_notes/decisions.md` for architectural choices
3. Solution Architect reports completion to Team Lead

### Step 8: Critical Review and Refinement

**Actor**: Team Lead delegates to Critical Analyst

1. Assign review to Critical Analyst with:
   - All impl plan file paths
   - All user story file paths (for cross-reference)
2. Critical Analyst reviews EACH implementation plan against:
   - FR/TR/AC alignment (100% coverage required)
   - Industry best practices
   - Cost compliance
   - Cross-story integration
   - Consistency with project memory decisions
3. Critical Analyst generates analysis documents:
   - `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-critical-analysis.md`
4. If issues found (max 2 refinement cycles):
   - Team Lead sends findings to Solution Architect
   - Solution Architect revises impl plans in-place
   - Team Lead sends revised plans back to Critical Analyst
   - Critical Analyst updates analysis (iteration tracking)
5. After 2 cycles, proceed with documented risks

### Step 9: Complete Epic Planning

**Actor**: Team Lead

1. Verify all artifacts exist:
   ```
   docs/phases/epic-{NNN}-{desc}/
     epic.md
     stories/
       story-001-{desc}.md
       story-002-{desc}.md
       ...
     plans/
       story-001-{desc}-plan.md
       story-001-{desc}-critical-analysis.md
       story-002-{desc}-plan.md
       story-002-{desc}-critical-analysis.md
       ...
     research/
       findings.md
       story-001-{desc}-tech-research.md (if applicable)
       ...
   ```
2. Present completion summary to user
3. Shut down all teammates via `shutdown_request`
4. Delete team via `TeamDelete`

</workflow_steps>

<artifact_templates>

Templates for epic, user story, and implementation plan artifacts are in
`references/artifact-templates.md`. Load when generating artifacts in Steps 3, 5, and 7.

</artifact_templates>

<reference_index>

## References

All in `references/`:

| File | Purpose |
|------|---------|
| story-patterns.md | User story creation patterns, FR/TR/AC category definitions, coverage rules |
| impl-plan-patterns.md | Implementation plan structure, task markers, API field extraction requirements |
| epic-template.md | Epic creation patterns, dependency types, sequencing rules |
| critical-analysis.md | Critical analysis methodology, review checklist, severity levels |
| complexity-scoring.md | AI Complexity Scoring Framework (4-factor scoring, calibration) |
| quality-standards.md | Code quality standards, data policies, configuration management |
| cost-assessment.md | Cost evaluation methodology, flagging protocol, approval process |
| artifact-templates.md | Epic, User Story, and Implementation Plan templates |

</reference_index>

<workflows_index>

## Workflows

All in `workflows/`:

| File | Purpose |
|------|---------|
| plan-epic.md | Full 9-step planning workflow for a single epic |
| manage-phases.md | Insert, remove, reorder, split, merge epics in project-context.md |
| generate-stories.md | Story generation sub-workflow (Steps 3-5 detail) |
| generate-impl-plan.md | Implementation plan generation sub-workflow (Steps 6-7 detail) |
| critical-review.md | Critical review and refinement sub-workflow (Step 8 detail) |
| hotfix.md | Abbreviated 5-step workflow for bug fixes (always --skip-research) |

</workflows_index>

<verification>

## Post-Planning Checklist

After completing epic planning, verify:

### Artifacts Exist
- [ ] `docs/phases/epic-{NNN}-{desc}/epic.md` created
- [ ] `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md` for each story
- [ ] `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md` for each story
- [ ] `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-critical-analysis.md` for each story
- [ ] `docs/phases/epic-{NNN}-{desc}/research/findings.md` created (skip if `--skip-research`)

### Quality Gates
- [ ] All user stories have complete FR/TR/AC tables
- [ ] Every FR validated by at least one AC
- [ ] Every TR validated by at least one AC
- [ ] Every AC has 4 test levels in impl plan (unit, integration, E2E, live)
- [ ] Requirements Coverage Validation shows 100% mapping in every impl plan
- [ ] All `[INSERT_USER_INPUT]` placeholders resolved
- [ ] Critical analysis confidence level is High (or documented exceptions)

### User Confirmations
- [ ] User confirmed epic/story direction (Q&A 1)
- [ ] User confirmed story breakdown with FR/TR/AC (Q&A 2)
- [ ] User answered technical questions and approved costs (Q&A 3)

### Project Memory
- [ ] Architectural decisions written to `docs/project_notes/decisions.md`
- [ ] Epic planning logged in `docs/project_notes/issues.md`
- [ ] Key facts updated in `docs/project_notes/key_facts.md`

### Cost Compliance
- [ ] All non-zero costs flagged and user-approved
- [ ] Zero/low-cost alternatives documented where applicable

</verification>
