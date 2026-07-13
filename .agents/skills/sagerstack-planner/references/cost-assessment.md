# Cost Assessment Reference

Guide for the Solution Architect when evaluating, flagging, and managing costs during implementation planning.

---

## Core Principle

**Always prefer zero-cost or low-cost approaches** unless there is a compelling technical reason for a paid solution. Every non-zero cost requires explicit user approval.

---

## Cost Flagging Protocol (MANDATORY)

For EVERY non-zero cost element identified during planning, the Solution Architect MUST flag it to the Team Lead using this format:

```
COST FLAG:
- Item: {service/tool/subscription name}
- Monthly cost: ${amount}
- Alternative: {zero-cost or lower-cost alternative, if any}
- Trade-off: {what is lost by choosing the cheaper option}
- Recommendation: {architect's recommendation with reasoning}
```

### Examples

**External API Subscription**:
```
COST FLAG:
- Item: LunarCrush Individual Plan
- Monthly cost: $30
- Alternative: Free tier (limited to 100 requests/day)
- Trade-off: Free tier insufficient for real-time data needs (requires 10,000+ daily)
- Recommendation: Paid plan required for production use case
```

**Infrastructure Service**:
```
COST FLAG:
- Item: AWS RDS PostgreSQL (db.t3.micro)
- Monthly cost: $15
- Alternative: SQLite for local development, PostgreSQL in Docker for testing
- Trade-off: No alternative for production persistence
- Recommendation: Use Docker PostgreSQL for local/test, defer AWS cost to deploy phase
```

**Zero-Cost Alternative Found**:
```
COST FLAG:
- Item: Algolia Search
- Monthly cost: $29
- Alternative: PostgreSQL full-text search (free, already in stack)
- Trade-off: Algolia has better relevance ranking and typo tolerance
- Recommendation: Use PostgreSQL FTS. Sufficient for current scale. Revisit at 10K+ records.
```

---

## Cost Categories

### Direct Costs (Flag Immediately)

| Category | Examples | Typical Range |
|----------|---------|---------------|
| **API Subscriptions** | LunarCrush, Algolia, Twilio | $10-100/month |
| **Cloud Services** | AWS RDS, S3, Lambda | $5-500/month |
| **SaaS Tools** | Monitoring, error tracking, analytics | $10-200/month |
| **Domain/SSL** | Custom domains, certificates | $10-50/year |

### Indirect Costs (Flag if Significant)

| Category | Examples | When to Flag |
|----------|---------|-------------|
| **Compute** | Docker containers, build minutes | When exceeding free tier |
| **Storage** | Database size, file storage | When growth projections exceed free tier |
| **Bandwidth** | API calls, data transfer | When rate limits or transfer costs apply |

### Hidden Costs (Always Investigate)

| Category | Red Flags |
|----------|-----------|
| **Usage-based pricing** | "Free up to X, then $Y per unit" |
| **Rate limit tiers** | "100 req/min free, 10K req/min at $X" |
| **Data retention** | "30 days free, extended retention at $X" |
| **Support tiers** | "Community support free, priority at $X" |

---

## Cost Evaluation Process

### Step 1: Identify All Cost Elements

During implementation plan generation, identify:
- External APIs mentioned in user stories or tech research
- Infrastructure requirements (databases, queues, storage)
- Third-party libraries with commercial licenses
- Services requiring subscriptions

### Step 2: Research Alternatives

For each paid element, investigate:
1. **Free/open-source alternative**: Does one exist?
2. **Free tier**: Does the service have a free tier that meets requirements?
3. **Self-hosted alternative**: Can we host our own version?
4. **Deferred cost**: Can the cost be pushed to the deploy phase?

### Step 3: Flag to Team Lead

Use the COST FLAG format above. Include:
- All identified costs
- All alternatives found
- Clear recommendation

### Step 4: User Approval

Team Lead presents cost flags to user. Proceed ONLY after explicit approval for each non-zero cost.

---

## Cost Documentation in Implementation Plan

### Plan Metadata
Include cost summary in the implementation plan:

```markdown
## Cost Summary
| Item | Monthly Cost | Approved | Alternative | Notes |
|------|-------------|----------|-------------|-------|
| {Service A} | ${amount} | Yes | {Alt} | Approved in Q&A 3 |
| {Service B} | $0 (free tier) | N/A | N/A | Within free tier limits |
| **Total** | **${total}** | | | |
```

### Task-Level Cost Annotations

When a task involves a paid service, annotate it:

```markdown
- [ ] **[5.0][FR-1] {Description}**
  - [ ] [5.1] Set up {service} integration (**COST: ${amount}/month, approved**)
  - [ ] [5.2] Configure API authentication
```

---

## Zero-Cost Patterns (Prefer These)

| Need | Zero-Cost Approach |
|------|-------------------|
| Database (dev/test) | SQLite, Docker PostgreSQL |
| Search | PostgreSQL full-text search |
| Caching | In-memory dict, Redis in Docker |
| File storage | Local filesystem, Docker volumes |
| Monitoring (dev) | Structured logging to stdout |
| CI/CD | GitHub Actions (free for public repos) |
| API mocking | WireMock, json-server, local fixtures |
| Load testing | Locust (open source) |
| Email (dev) | MailHog in Docker |

---

## Cost Escalation Rules

### When to Escalate to User

1. Any cost > $0/month for the first time
2. Cost increase > 20% from previous phase
3. New recurring cost discovered mid-planning
4. Alternative found that reduces existing cost

### When to Proceed Without Escalation

1. Cost was already approved for this project
2. Cost is within a previously approved budget envelope
3. Free tier usage within documented limits

---

## Budget Tracking

### Phase-Level Budget

If user specifies a budget for the phase:

```markdown
## Phase Budget
- **Total Budget**: ${amount}/month
- **Allocated**: ${allocated}/month
- **Remaining**: ${remaining}/month

### Budget Allocation
| Item | Cost | % of Budget |
|------|------|-------------|
| {Service} | ${cost} | {%} |
```

### Critical Analyst Budget Review

The Critical Analyst verifies:
- [ ] All costs flagged and approved
- [ ] No hidden costs in implementation tasks
- [ ] Budget constraints respected
- [ ] Zero-cost alternatives considered where applicable
- [ ] No unexpected cost escalation
