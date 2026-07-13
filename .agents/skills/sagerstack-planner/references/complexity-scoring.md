# AI Complexity Scoring Framework

Reference for Business Analyst (story sizing) and Solution Architect (plan estimation). Provides standardized 1-10 metric for AI-assisted implementation complexity.

---

## Core Formula

```
AI Complexity Score = Research Depth + Code Complexity + Integration Complexity + Testing Scope

Factor Ranges:
- Research Depth:         0-3 points
- Code Complexity:        0-3 points
- Integration Complexity: 0-2 points
- Testing Scope:          0-2 points

Total Range: 0-10 points
```

---

## Factor 1: Research Depth (0-3)

Measures web research effort required for Solution Architect to generate implementation plans.

| Score | Level | Research Cycles | Characteristics | Examples |
|-------|-------|----------------|-----------------|----------|
| **0** | None | 0 | Well-known patterns, standard library, no external research | Basic CRUD, simple data models, standard REST |
| **1** | Standard | 1-2 | Single documentation source, well-documented APIs | FastAPI setup, PostgreSQL connection, Redis caching |
| **2** | Deep | 4-6 | Multiple sources, architect-critic refinement, some ambiguity | Third-party API, rate limiting, OAuth2 |
| **3** | Extensive | 8+ | Novel patterns, incomplete docs, competing approaches | Custom ML pipeline, distributed systems, WebSocket with fallbacks |

### Scoring Indicators (+1 each)

**Documentation Quality**:
- No official SDK (manual HTTP client needed)
- API docs incomplete, outdated, or contradictory
- No official examples or integration guides

**Pattern Novelty**:
- Novel integration pattern not commonly documented
- Multiple competing approaches requiring trade-off analysis
- Custom algorithm design (not library-based)

**Research Breadth**:
- Requires 4+ different technologies/services
- Performance benchmarking across options
- Security research for compliance

### Research Cycle Definition
1 cycle = WebSearch + read 2-3 docs + analyze + document integration patterns

---

## Factor 2: Code Complexity (0-3)

Measures structural complexity based on file count, LOC, and architectural patterns.

| Score | Level | Files | LOC | Architecture | Examples |
|-------|-------|-------|-----|--------------|----------|
| **0** | Trivial | 1-2 | <100 | Single function | Config file, utility |
| **1** | Low | 3-5 | 100-500 | Simple layered | REST endpoint + service |
| **2** | Medium | 6-15 | 500-2000 | Clean architecture | Feature with repository pattern |
| **3** | High | 16+ | >2000 | Event-driven/distributed | Real-time pipeline, multi-service |

### Scoring Indicators (+1 each)

**Code Patterns**:
- Async/concurrent programming (asyncio, threading)
- State management across components
- Multiple design patterns in single story

**Cross-Cutting Concerns**:
- Structured logging with context propagation
- Security layer (auth, authorization, encryption)
- Monitoring/observability instrumentation

**Data Flow**:
- Complex multi-stage data transformations
- Multiple database interactions with transactions
- Stream processing with backpressure

---

## Factor 3: Integration Complexity (0-2)

Measures external system integration complexity.

| Score | Level | APIs | Types | Examples |
|-------|-------|------|-------|----------|
| **0** | None | 0 | Self-contained | Pure business logic |
| **1** | Simple | 1-2 | REST, API key | Single third-party API |
| **2** | Complex | 3+ OR complex | WebSocket, OAuth2, custom | Multi-API correlation, real-time streams |

### Scoring Indicators (+1 each)

**Authentication**: OAuth2/OIDC, token refresh, multiple auth mechanisms
**Communication**: Real-time streams, webhooks with signature verification, bidirectional sync
**Error Handling**: Retry with backoff, circuit breaker, message queuing
**Data Coordination**: Multi-service transformation, request correlation, rate limiting coordination

---

## Factor 4: Testing Scope (0-2)

Measures automated testing breadth and depth.

| Score | Level | Test Types | Coverage | Examples |
|-------|-------|-----------|----------|----------|
| **0** | None | No tests | N/A | Prototype/spike |
| **1** | Basic | Unit only | >80% | Business logic tests with mocks |
| **2** | Comprehensive | Unit + Integration + E2E | >90% | Full pyramid, performance tests |

### Scoring Indicators (+1 each)

**Test Complexity**: Complex mock behaviors, state setup/teardown, async testing
**Test Types**: Real service integration, E2E workflows, performance/load, contract tests

---

## Score Interpretation

| Score | Level | Iterations | Research | Architect-Critic |
|-------|-------|-----------|----------|------------------|
| **1-2** | Trivial | 1 | Skip/minimal | Not needed |
| **3-4** | Low | 1-2 | Standard (1-2 cycles) | Helpful |
| **5-6** | Medium | 2-3 | Deep (4-6 cycles) | Recommended |
| **7-8** | High | 3-4 | Extensive (8+ cycles) | Required |
| **9-10** | Very High | 4+ | Novel patterns | Essential |

### Generation Strategy by Score

**1-2 (Trivial)**: Single-pass, skip research, direct implementation, >95% success rate
**3-4 (Low)**: Standard research, single-pass with adjustments, 85-95% success rate
**5-6 (Medium)**: Deep research, multi-pass, architect-critic recommended, 70-85% success
**7-8 (High)**: Extensive research, iterative with critic, 2+ refinement cycles, 50-70% success
**9-10 (Very High)**: Novel research, highly iterative, 3+ cycles, <50% success. Consider splitting.

---

## Documentation Template

Use in User Story and Implementation Plan artifacts:

```markdown
## AI Complexity Assessment

### Complexity Factors
| Factor | Score | Justification |
|--------|-------|---------------|
| **Research Depth** | {0-3} | {Research needs, doc gaps, pattern novelty} |
| **Code Complexity** | {0-3} | {File count, LOC, architecture, async} |
| **Integration Complexity** | {0-2} | {API count, patterns, auth complexity} |
| **Testing Scope** | {0-2} | {Test types, coverage, mocking complexity} |

### Overall AI Complexity Score: **{1-10}**

**Complexity Level**: {Trivial / Low / Medium / High / Very High}

**AI Generation Strategy**:
- **Expected Iterations**: {1 / 1-2 / 2-3 / 3-4 / 4+}
- **Research Phase**: {Skip / Standard (1-2) / Deep (4-6) / Extensive (8+)} cycles
- **Architect-Critic Review**: {Not needed / Helpful / Recommended / Required / Essential}

**Complexity Drivers**: {Specific factors increasing score}
**Risk Factors**: {Dependencies or unknowns that could increase complexity}
**Mitigation Strategies**: {How to reduce complexity or manage risks}
```

---

## Calibration Anchors

### Score 2 (Trivial): Basic Database Model
```
Research: 0 (standard patterns)
Code: 1 (3 files, ~200 LOC)
Integration: 0 (database only)
Testing: 1 (unit tests)
```

### Score 6 (Medium): API Client with Rate Limiting
```
Research: 2 (no SDK, docs research, rate limiting)
Code: 2 (8 files, ~800 LOC, async)
Integration: 1 (1 API, REST + key)
Testing: 1 (unit + integration)
```

### Score 9 (Very High): Real-time ML Pipeline
```
Research: 3 (ML integration, stream processing, inference optimization)
Code: 3 (25+ files, ~3500 LOC, event-driven, async streams)
Integration: 2 (4 APIs, WebSocket, message queue, multi-source)
Testing: 2 (full pyramid, performance, contract)
```

---

## Calibration Rules

1. **Baseline with anchors**: Use the 3 examples above as reference points
2. **Score independently**: BA and Architect score separately; if diff > 2, discuss and converge
3. **Start conservative**: Begin at 0 for each factor, add only when indicators clearly present
4. **Document edge cases**: When story does not fit matrix, explain reasoning
5. **Retrospective calibration**: Compare predicted vs actual after completion

---

## Common Scoring Mistakes

| Mistake | Wrong | Right |
|---------|-------|-------|
| Business vs AI complexity | "Important = high score" | Score generation factors only |
| Uncertainty vs complexity | "Unknown = complex" | Document unknowns separately |
| Unfamiliar technology | "New to team = complex" | If well-documented, score stays low |
| Documentation quality | "Just one API = 1" | No SDK + poor docs = Research +2 |
| Static scoring | Keep original score | Architect adjusts after research |

---

## Architect-Critic Trigger Rules

| Complexity Score | Architect-Critic Behavior |
|-----------------|--------------------------|
| 1-4 | Optional. Critic reviews if time allows. |
| 5-6 | Recommended. Critic should review for quality. |
| 7+ | Mandatory. Critic MUST review. Min 2 refinement cycles. |
| 9-10 | Essential. Consider splitting story before proceeding. |
