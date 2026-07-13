# User Story Patterns

Reference for the Business Analyst when creating user stories. Extracted and adapted from the user-story-artifact template.

---

## Story Purpose

User stories specify implementable user value slices with comprehensive acceptance criteria and complexity estimation. They translate epic capabilities into specific, testable, and deliverable functionality.

### Key Objectives
- **Value Definition**: Define specific user value and business outcome
- **Implementation Clarity**: Provide clear, testable requirements for development
- **Acceptance Framework**: Establish comprehensive acceptance criteria
- **Traceability**: Maintain connection to epic goals
- **Requirements Focus**: Define WHAT must be built, not HOW to implement

---

## Functional Requirement Categories

| Category | Description | Examples |
|----------|-------------|---------|
| **Capability** | Core features and functionality the system must provide | API endpoint, data processing, calculation engine |
| **Workflow** | Business processes or workflows the system must support | Order placement flow, approval chain, data pipeline |
| **Data Validation** | Input validation, format checks, data constraints | Email format validation, range checks, required fields |
| **UI/UX** | User interface and experience requirements | Response format, error messages, interactive elements |

### FR Naming Convention
- Use imperative verbs: "Process", "Validate", "Calculate", "Store"
- Be specific: "Validate email format" not "Handle email"
- Embed constraints in Description: "within rate limits", "using only free tier"

---

## Technical Requirement Categories

| Category | Description | Target Format |
|----------|-------------|---------------|
| **Performance** | Response time, throughput, scalability | "< 200ms p95", "100 req/sec" |
| **Security** | Authentication, authorization, encryption | "TLS 1.3", "OAuth2 PKCE" |
| **Reliability** | Availability, fault tolerance, recovery | "99.9% uptime", "< 5min RTO" |
| **Data Processing** | Transformation, calculation, processing rules | "Real-time within 500ms" |
| **Data Storage** | Persistence, retention, storage requirements | "30-day retention", "encrypted at rest" |
| **Privacy** | Data privacy and protection | "GDPR compliant", "PII anonymized" |
| **Compliance** | Regulatory requirements | "SOC2 Type II", "PCI DSS" |

---

## Acceptance Criteria Types

### Functional Types

| Type | Purpose | When to Use |
|------|---------|-------------|
| **Happy Path** | Verify primary success scenario | Every FR must have at least one |
| **Failure Scenario** | Verify graceful failure handling | External dependencies, network failures |
| **Edge Case** | Verify boundary behavior | Limits, empty inputs, max values |
| **Error Handling** | Verify error responses | Invalid inputs, unauthorized access |
| **Integration** | Verify real service integration | External APIs, databases |
| **End-to-End** | Verify full workflow completion | Complete user journey |

### Technical Types

| Type | Purpose | When to Use |
|------|---------|-------------|
| **Performance** | Verify speed/throughput targets | When TR has performance targets |
| **Security** | Verify security controls | When TR has security requirements |
| **Reliability** | Verify availability/recovery | When TR has reliability SLAs |

### AC Given/When/Then Pattern

```
Given: [Initial context or system state]
When: [Specific user action or system trigger]
Then: [Expected system response or observable outcome]
```

**Good Examples**:
- Given: User has valid API key in .env.local
  When: User calls /health/auth endpoint
  Then: System returns 200 OK with "Authentication successful"

- Given: External API is unavailable
  When: System attempts to fetch price data
  Then: System returns cached data with "stale" flag and logs warning

**Bad Examples**:
- Given: System is set up (too vague)
  When: User does something (not specific)
  Then: It works (not measurable)

---

## Coverage Rules (MANDATORY)

### FR Coverage
- Every Functional Requirement (FR) MUST be validated by at least one Acceptance Criterion
- Use AC "Then" statements to directly validate FR requirements
- Review "Validates" column to ensure complete FR coverage

### TR Coverage
- Every Technical Requirement (TR) MUST be validated by at least one Acceptance Criterion
- Performance TRs need Performance-type ACs
- Security TRs need Security-type ACs

### Validates Column
- Must reference specific FR/TR IDs (e.g., "FR-1", "TR-3")
- Can reference ranges (e.g., "FR-1-6" for FR-1 through FR-6)
- Each AC should validate 1-3 requirements (not more for clarity)

---

## Requirements Clarifications Section

### Purpose
Identify incomplete or ambiguous functional requirements that need user clarification.

### Rules
- Generate specific clarification questions (not generic)
- Focus on: functional scope, business logic, workflows, error handling, feature boundaries
- Use `[INSERT_USER_INPUT]` placeholder for each question
- If no clarifications needed: "No further clarifications needed"
- After user provides answers: refine FR/TR/AC accordingly, update status Draft -> Final

### Good Clarification Questions
- "Should the retry mechanism use exponential backoff or fixed intervals?"
- "When the external API returns partial data, should we store the partial result or reject entirely?"
- "What is the maximum acceptable latency for the price feed before switching to cache?"

### Bad Clarification Questions
- "How should we implement this?" (too broad, asks HOW not WHAT)
- "Is this important?" (not actionable)

---

## Technical Guidance Section

### Purpose
Provide technical constraints to guide Solution Architect's implementation planning.

### Rules
- Copy ONLY category labels from the template
- Each category has exactly ONE bullet with `[INSERT_USER_INPUT]`
- DO NOT fill in content -- user provides technical guidance later
- Categories: Technical Stack, Architecture, Integration, Data, Infrastructure, Cost, Security

### Solution Architect MUST
- Follow this guidance as hard constraints during implementation planning
- Flag conflicts between guidance and best practices
- Request clarification through Team Lead if guidance is ambiguous

---

## Priority System

| Priority | Label | Meaning |
|----------|-------|---------|
| P1 | Highest | Must have for the phase to succeed |
| P2 | High | Should have, significant value |
| P3 | Medium | Could have, improves experience |
| P4 | Low | Nice to have |
| P5 | Lowest | Defer unless trivial |

---

## Story Sizing Guidelines

### Too Large (Split It)
- More than 5 FRs
- More than 10 ACs
- AI Complexity Score > 8
- Multiple external integrations

### Too Small (Merge It)
- Single FR with trivial implementation
- AI Complexity Score < 2
- Can be completed in under 30 minutes

### Right Size
- 2-5 FRs
- 4-8 ACs
- AI Complexity Score 3-7
- Clear single user value delivery
