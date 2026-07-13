# Epic & Milestone Patterns

Guidance for structuring milestones and epics. Read this during planning to inform the breakdown.

---

## Core Philosophy

### Local-First Development
The objective for initial milestones is to set up minimal foundation to run the app locally. Deliver one capability at a time with complete E2E running successfully on local machine first.

### Value-Driven Prioritization
Epics should target core capability and value add FIRST, before bells and whistles (authentication, access control, observability, etc.).

### Cloud-Ready from Day One
Develop with a view of eventual cloud deployment. Local deployment strategy should mimic eventual cloud deployment 100%. This means:
- Same containerization approach
- Same service boundaries
- Same configuration patterns
- LocalStack for AWS services

### Cloud Deployment After Core Works
Plan for AWS deployment only AFTER core capability works locally E2E. Don't deploy half-baked features to cloud.

---

## OKR-Driven Hierarchy

### Objective (Project Level)
The qualitative "what" and "why". Gathered from user during discovery.

### Milestones
Groupings of related epics toward the Objective. Each milestone has its own Key Results.

```
Milestone [N]: [Name]
- Delivers: [Major capability or outcome]
- Why Now: [Why this milestone before others]

Key Results:
- KR-1: [Measurable outcome]
- KR-2: [Measurable outcome]
```

### Epics (within Milestones)
Actionable work units mapped to Key Results. Each epic = one folder under `docs/phases/`.

```
Epics for Milestone [N]:

| Epic | Task | Key Result |
|------|------|------------|
| E1 | [Concise task description] | [KR mapping or — (enabling)] |
| E2 | [Concise task description] | [KR-1, KR-2] |
```

Folder naming: `docs/phases/epic-NNN-three-word-desc/`
Numbering: Global sequential (epic-001, epic-002, epic-003... across all milestones)

---

## Epic Ordering Principles

### 1. Minimal Runnable First
First epics should produce something that runs locally, even if minimal.

**Good**: "E1: CLI skeleton that prints hello world"
**Bad**: "E1: Complete domain model for all entities"

### 2. Vertical Slices Over Horizontal Layers
Each epic delivers a complete vertical slice (domain → application → infrastructure → API) for ONE capability.

**Good**: "E2: Create order flow (domain + repo + handler + endpoint)"
**Bad**: "E2: All domain models for the entire system"

### 3. Core Value Before Infrastructure
Defer non-core requirements until core capability works.

**Defer until later:**
- Authentication / Authorization
- Access control
- Logging infrastructure
- Monitoring / Alerting
- Rate limiting
- Caching optimization

**Do early:**
- Core business logic
- Primary user journey
- Data persistence (minimal)
- Local execution

### 4. One Capability at a Time
Don't parallelize capabilities in early epics. Complete one E2E before starting next.

### 5. Cloud Deployment as Separate Milestone
AWS deployment is its own milestone AFTER local E2E works.

---

## Typical Milestone Patterns

### New Project from Scratch

```
Milestone 1: Local Foundation
Delivers: Minimal app running locally with one core capability E2E

Key Results:
- KR-1: [Core capability works end-to-end locally]
- KR-2: [Test coverage >= 90%]

Epics:
| Epic | Task | Key Result |
|------|------|------------|
| E1 | Project Skeleton | — (enabling) |
| E2 | Core Domain Model | KR-1 |
| E3 | Repository + Handler | KR-1 |
| E4 | Entry Point + Local Run | KR-1, KR-2 |
| E5 | Docker + LocalStack Setup | — (enabling) |

Milestone 2: Core Capability Complete
Delivers: Full core capability working locally

Key Results:
- KR-1: [All core user journeys work]

Epics:
| Epic | Task | Key Result |
|------|------|------------|
| E6-N | Additional vertical slices | KR-1 |

Milestone 3: Secondary Capabilities
Delivers: Supporting features

Milestone 4: Production Readiness
Delivers: Non-functional requirements (auth, logging, health checks)

Milestone 5: AWS Deployment
Delivers: Running in AWS
```

### New Feature for Existing Project

```
Milestone 1: Feature Foundation
Delivers: New capability working locally E2E

Key Results:
- KR-1: [Feature works end-to-end]

Epics:
| Epic | Task | Key Result |
|------|------|------------|
| E1 | Domain Model (new slice) | KR-1 |
| E2 | Repository + Handler | KR-1 |
| E3 | API Endpoint | KR-1 |
| E4 | Integration with Existing | KR-1 |

Milestone 2: Feature Complete + Deploy
Delivers: All feature requirements live

Key Results:
- KR-1: [Feature deployed and verified]
```

### Refactor/Restructure

```
Milestone 1: Safety Net
Delivers: Tests covering existing behavior

Key Results:
- KR-1: [Existing behavior fully covered by tests]

Epics:
| Epic | Task | Key Result |
|------|------|------------|
| E1 | Characterization Tests | KR-1 |
| E2 | Identify Boundaries | — (enabling) |

Milestone 2: Incremental Migration
Delivers: Code migrated to new structure

Key Results:
- KR-1: [All slices migrated, tests pass]

Epics:
| Epic | Task | Key Result |
|------|------|------------|
| E3 | New Structure Alongside | — (enabling) |
| E4 | Migrate Slice by Slice | KR-1 |
| E5 | Remove Old Code | KR-1 |
```

### Integration with External System

```
Milestone 1: Interface Definition
Delivers: Contract with external system

Key Results:
- KR-1: [Mock integration works locally]

Epics:
| Epic | Task | Key Result |
|------|------|------------|
| E1 | Research External API | — (enabling) |
| E2 | Domain Interface (abstraction) | KR-1 |
| E3 | Mock Implementation | KR-1 |

Milestone 2: Real Implementation + Deploy
Delivers: Working integration live

Key Results:
- KR-1: [Real API calls succeed]
```

---

## Anti-Patterns to Avoid

### Big Bang Epics
**Bad**: "E1: Implement entire domain model"
**Good**: "E1: Implement Order aggregate only"

### Horizontal Layer Epics
**Bad**: "E1: All repositories, E2: All handlers"
**Good**: "E1: Order slice (domain + repo + handler)"

### Infrastructure Before Value
**Bad**: "E1: Set up Terraform and CI/CD"
**Good**: "E1: Core capability running locally"

### Premature Cloud Deployment
**Bad**: "E3: Deploy to AWS" (before local E2E works)
**Good**: "Milestone 5: AWS Deployment" (after local is solid)

---

## Checklist Before Finalizing

- [ ] First milestone produces something runnable locally
- [ ] Each epic is a vertical slice (not horizontal layer)
- [ ] Core value delivered before infrastructure concerns
- [ ] Local deployment mimics cloud deployment
- [ ] AWS deployment is a separate, later milestone
- [ ] Every epic maps to a Key Result or is marked as enabling
- [ ] Key Results are measurable and observable
- [ ] Objective is clear and confirmed by user
