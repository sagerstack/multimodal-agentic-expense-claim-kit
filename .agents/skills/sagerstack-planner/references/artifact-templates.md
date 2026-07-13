# Artifact Templates

Templates for epic, user story, and implementation plan artifacts. Load when generating artifacts in Steps 3, 5, and 7 of the planning workflow.

## Epic Template

Save to: `docs/phases/epic-{NNN}-{desc}/epic.md`

```markdown
# Epic: {epic-name}

## Metadata
| Field | Value |
|-------|-------|
| ID | EP-{NNN} |
| Title | {Descriptive epic title} |
| Epic Reference | EP-{NNN} |
| Created | {YYYY-MM-DD HH:mm:ss} |
| Status | Draft / Final |
| Status History | {Date: Status - Reason} |
| Last Updated | {YYYY-MM-DD HH:mm:ss} |
| Research Mode | Full / Skipped |

## Epic Overview
**What**: {Clear description of the capability being delivered}
**Why**: {Business value and strategic importance}
**Success**: {High-level definition of epic success}

## Success Metrics
| Metric | Target Value | Measurement Method | Data Source |
|--------|--------------|-------------------|-------------|
| {Primary metric} | {Target} | {Method} | {Source} |
| {Secondary metric} | {Target} | {Method} | {Source} |

## User Stories List

### Story Portfolio Overview
| ID | Title | Status | Priority | AI Complexity Score | Business Value |
|----|-------|--------|----------|---------------------|----------------|
| US-{NNN} | {Story title} | Draft | Must-have | {1-10} | {Value} |
| US-{NNN} | {Story title} | Draft | Should-have | {1-10} | {Value} |
| US-{NNN} | {Story title} | Draft | Could-have | {1-10} | {Value} |

## Epic Sequencing and Dependency Rules

### Dependency Types
- **Blocking**: Story B blocks Story A -> B must finish before A starts
- **Prerequisite**: Story B is prerequisite for A -> A can start when B is 50%+ complete
- **Informational**: Story B informs Story A -> No sequencing impact

### Story Dependency Graph
{Describe dependencies between stories}

## Dependencies & Prerequisites

### Epic Dependencies
| Dependency | Type | Impact | Status | Resolution Timeline |
|------------|------|--------|--------|-------------------|
| {Dependency} | {Blocking/Prerequisite/Informational} | {Impact} | {Status} | {Timeline} |

### External Dependencies
- **System Dependencies**: {Required external systems}
- **Data Dependencies**: {Required data sources}
- **Technology Dependencies**: {Required tech stack}

## Acceptance Criteria (Epic Level)

### Definition of Done
- [ ] All must-have user stories completed and accepted
- [ ] All acceptance criteria validated
- [ ] Epic success criteria from project-context.md met
- [ ] Implementation plans fully executed

## Risk Assessment

### High-Priority Risks
**Risk 1: {Description}**
- **Probability**: {High/Medium/Low}
- **Impact**: {High/Medium/Low}
- **Mitigation**: {Strategy}
- **Contingency**: {Backup plan}

## Changelog
| Date | Author | Summary | Sections Affected | Reason |
|------|--------|---------|------------------|--------|
| {Date} | Business Analyst | Initial epic creation | All | Epic planning |
```

## User Story Template

Save to: `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md`

```markdown
# User Story: {story-title}

## Metadata
| Field | Value |
|-------|-------|
| ID | US-{NNN} |
| Title | {Descriptive story title} |
| Epic Reference | EP-{NNN} |
| Created | {YYYY-MM-DD HH:mm:ss} |
| Status | Draft / Final |
| Status History | {Date: Status - Reason} |
| Last Updated | {YYYY-MM-DD HH:mm:ss} |

## Story Overview
- **Story Purpose**: {Clear statement of user value and business outcome}
- **Epic Context**: {Connection to parent epic}
- **User Impact**: {How this improves user workflow}
- **Business Value**: {Expected business impact}

## User Story

| Field | Value |
|-------|-------|
| **As a** | {specific user persona or role} |
| **I want** | {specific capability or functionality} |
| **So that** | {specific outcome, benefit, or value} |

## Functional Requirements

| Status | ID | Category | Requirement | Description | Priority | AI Complexity Score |
|--------|----|----|-------------|-------------|----------|--------------------:|
| [ ] | FR-1 | {Category} | {Name} | {What the system must do} | P1 | {1-10} |
| [ ] | FR-2 | {Category} | {Name} | {Description} | P1 | {1-10} |

**Category Values**: Capability, Workflow, Data Validation, UI/UX
**Priority Values**: P1 (Highest) to P5 (Lowest)

## Technical Requirements

| Status | ID | Category | Requirement | Description | Target/Threshold | AI Complexity Score |
|--------|-----|----------|-------------|-------------|------------------|--------------------:|
| [ ] | TR-1 | {Category} | {Name} | {Description} | {Target} | {1-10} |
| [ ] | TR-2 | {Category} | {Name} | {Description} | {Target} | {1-10} |

**Category Values**: Performance, Security, Reliability, Data Processing, Data Storage, Privacy, Compliance

## Acceptance Criteria

| Status | ID | Given | When | Then | Type | Validates | Priority |
|--------|-----|-------|------|------|------|-----------|----------|
| [ ] | AC-1 | {Context} | {Action} | {Outcome} | Functional - Happy Path | FR-1 | P1 |
| [ ] | AC-2 | {Context} | {Action} | {Outcome} | Functional - Failure Scenario | FR-2 | P1 |
| [ ] | AC-3 | {Context} | {Action} | {Outcome} | Functional - Edge Case | FR-3 | P2 |
| [ ] | AC-4 | {Context} | {Action} | {Outcome} | Technical - Performance | TR-1 | P2 |
| [ ] | AC-5 | {Context} | {Action} | {Outcome} | Functional - End-to-End | FR-1-3, TR-1 | P1 |

**Functional Types**: Happy Path, Failure Scenario, Edge Case, Error Handling, Integration, End-to-End
**Technical Types**: Performance, Security, Reliability

**Coverage Rules**:
- Every FR must be validated by at least one AC
- Every TR must be validated by at least one AC
- The "Validates" column must reference specific FR/TR IDs

## Dependencies & Prerequisites

### Story Dependencies
| Dependency | Type | Impact | Status |
|------------|------|--------|--------|
| {Dependency} | {Blocking/Prerequisite} | {Impact} | {Status} |

### Technical Dependencies
- **Infrastructure**: {Required infrastructure}
- **Technology**: {Required tech stack}
- **Testing**: {Required test tools}

## Risk Assessment

### Implementation Risks
**Risk 1: {Description}**
- **Probability**: {High/Medium/Low}
- **Impact**: {High/Medium/Low}
- **Mitigation**: {Strategy}
- **Contingency**: {Backup}

## AI Complexity Assessment

### Complexity Factors
| Factor | Score | Justification |
|--------|-------|---------------|
| **Research Depth** | {0-3} | {Justification} |
| **Code Complexity** | {0-3} | {Justification} |
| **Integration Complexity** | {0-2} | {Justification} |
| **Testing Scope** | {0-2} | {Justification} |

### Overall AI Complexity Score: **{1-10}**

**Complexity Level**: {Trivial / Low / Medium / High / Very High}
**Expected Iterations**: {1 / 1-2 / 2-3 / 3-4 / 4+}
**Architect-Critic Review**: {Not needed / Helpful / Recommended / Required / Essential}

## Requirements Clarifications

**Functional Clarifications**:
- **{Question 1}**:
  [INSERT_USER_INPUT]
- **{Question 2}**:
  [INSERT_USER_INPUT]

## Technical Guidance for Solution Architect

**Technical Stack**:
- [INSERT_USER_INPUT]

**Architecture**:
- [INSERT_USER_INPUT]

**Integration**:
- [INSERT_USER_INPUT]

**Data**:
- [INSERT_USER_INPUT]

**Infrastructure**:
- [INSERT_USER_INPUT]

**Cost**:
- [INSERT_USER_INPUT]

**Security**:
- [INSERT_USER_INPUT]

## Changelog
| Date | Author | Summary | Sections Affected | Reason |
|------|--------|---------|------------------|--------|
| {Date} | Business Analyst | Initial story creation | All | Epic planning |
```

## Implementation Plan Template

Save to: `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md`

```markdown
# Implementation Plan: {story-title}

## Metadata
| Field | Value |
|-------|-------|
| ID | US-{NNN}-IMPL-PLAN |
| User Story ID | US-{NNN} |
| Tech Research ID | US-{NNN}-TECH-RESEARCH (if applicable) |
| Created | {YYYY-MM-DD HH:mm:ss} |
| Status | Draft / Final |
| Last Updated | {YYYY-MM-DD HH:mm:ss} |
| AI Complexity Score | {1-10} |

## Quick Reference
- **Tech Stack**: {Technologies used}
- **Architectural Pattern**: {Pattern applied}
- **Tech Research**: {Link to tech research doc if applicable}

## Requirements Coverage Validation

### Functional Requirements
| Requirement ID | Description | Parent Task | Status |
|----------------|-------------|-------------|--------|
| FR-1 | {Description} | [{X}.0][FR-1] ({N} subtasks) | [ ] |
| FR-2 | {Description} | [{X}.0][FR-2] ({N} subtasks) | [ ] |

### Technical Requirements
| Requirement ID | Description | Parent Task | Status |
|----------------|-------------|-------------|--------|
| TR-1 | {Description} | [{X}.0][TR-1] ({N} subtasks) | [ ] |

### Acceptance Criteria
| Criteria ID | Description | Parent Task | Unit Tests | Integration Tests | E2E Test | Live Verification |
|-------------|-------------|-------------|------------|-------------------|----------|-------------------|
| AC-1 | {Description} | [{X}.0][AC-1] | [{X}.4] | [{X}.5] | [{X}.6] | [{X}.7] |
| AC-2 | {Description} | [{X}.0][AC-2] | [{X}.4] | [{X}.5] | [{X}.6] | [{X}.7] |

**Coverage Summary**:
- Functional Requirements: X/X mapped (100%)
- Technical Requirements: Y/Y mapped (100%)
- Acceptance Criteria: Z/Z mapped with complete test coverage (100%)

## Task-Based Implementation Plan

### Execution Instructions
Complete tasks in order: Manual Prerequisites -> Environment & Setup -> Functional Requirements -> Technical Requirements -> Acceptance Criteria -> Documentation

---

### 1. Manual Prerequisites

- [ ] **[1.0][MANUAL] {Description}**
  - [ ] [1.1][MANUAL] {Human action required}
  - [ ] [1.2][MANUAL] {Human action required}

---

### 2. Environment & Setup

- [ ] **[{X}.0][SETUP] {Description}**
  - [ ] [{X}.1] {Subtask}
  - [ ] [{X}.2] {Subtask}

---

### 3. Functional Requirements

- [ ] **[{X}.0][FR-1] {FR-1 Description}**
  - [ ] [{X}.1] {Implement capability}
  - [ ] [{X}.2] {Implement capability}
  - [ ] [{X}.N-1] Write unit tests
  - [ ] [{X}.N] Live environment test

- [ ] **[{X}.0][FR-2] {FR-2 Description}**
  - [ ] [{X}.1] {Implement capability}
  - [ ] [{X}.N] Write unit tests

---

### 4. Technical Requirements

- [ ] **[{X}.0][TR-1] {TR-1 Description}**
  - [ ] [{X}.1] {Implement requirement}
  - [ ] [{X}.N] Write tests

---

### 5. Acceptance Criteria

- [ ] **[{X}.0][AC-1] {AC-1 Description}**
  - [ ] [{X}.1-{X}.3] Implementation subtasks
  - [ ] [{X}.4] Write unit tests (mocked dependencies)
  - [ ] [{X}.5] Write integration tests (component integration)
  - [ ] [{X}.6] **E2E Test**:
    ```bash
    docker-compose build
    docker-compose up -d
    response=$(curl -s http://localhost:{port}/{endpoint})
    status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/{endpoint})
    test "$status" = "200" || exit 1
    echo "AC-1 E2E test passed"
    ```
  - [ ] [{X}.7] **Live Environment Verification**:
    - Deploy to test environment
    - Verify with real external APIs
    - Document evidence

---

### 6. Documentation & Deployment

- [ ] **[{X}.0][DOC] {Description}**
  - [ ] [{X}.1] {Documentation task}
  - [ ] [{X}.2] {Version control task}

## Changelog
| Date | Author | Change Summary | Sections Affected | Reason |
|------|--------|----------------|------------------|--------|
| {Date} | Solution Architect | Initial plan | All | Epic planning |
```
