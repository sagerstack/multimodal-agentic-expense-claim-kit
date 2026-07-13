# Planning Question Bank

Sequential questions for the planning workflow. Ask ONE at a time with multiple-choice options.

## How to Use

1. Ask questions in the order listed below
2. Each question has suggested options — present as multiple choice
3. The last option is always free text ("Other: describe in your own words")
4. Before asking, check persona files and skills for existing preferences
5. If a preference exists, present as suggested answer for confirmation
6. Adapt follow-ups based on previous answers
7. Stop when you have enough context to synthesize an Objective

## Category Mapping

| Category | Persona File | Skill |
|----------|--------------|-------|
| Values/Quality | persona/values.md | - |
| Constraints | persona/constitution.md | - |
| Architecture | - | software-engineering |
| Testing | - | local-testing |
| Deployment | - | deploy-aws |

---

## Core Questions

### 1. Project Type
**Question**: What are we building?
**Options**:
- CLI tool
- Web API (REST/GraphQL)
- Scheduled job / background worker
- Library / package
- Other (describe)

**Check**: No existing preference — always ask

### 2. Problem
**Question**: What problem does this solve?
**Options**: None — this is qualitative, free-form input
**Follow-up**: What happens if we don't build this?

### 3. End User
**Question**: Who uses this?
**Options**:
- Internal team
- External customers
- Other developers (library/SDK)
- Other (describe)

### 4. Deployment Target
**Question**: Where will this run?
**Options**:
- Local only (development/testing)
- AWS Lambda (serverless)
- AWS EKS (Kubernetes)
- Other (describe)

**Check**: skill:deploy-aws for existing infrastructure patterns

### 5. Architecture
**Question**: How should we structure the code?
**Options**:
- Vertical Slice + DDD (your default)
- Layered architecture
- Other (describe)

**Check**: skill:software-engineering — Vertical Slice + DDD is the default.
If preference exists, present as: "Your default is Vertical Slice + DDD. Use this?"

### 6. Tech Stack
**Question**: Key technology choices (language, framework, package manager)
**Options**: Adapt based on project type:
- For Python: Poetry + pytest + mypy + ruff (your defaults)
- For CLI: Typer, Click, argparse
- For API: FastAPI, Flask
- Other (describe)

**Check**: Existing skills for defaults (Python, Poetry, pytest)

### 7. Configuration
**Question**: What configuration approach do you need?
**Options**:
- .env files (local + test)
- AWS Secrets Manager (production)
- Both .env + Secrets Manager
- Other (describe)

**Check**: persona/values.md — no hardcoded values is a hard constraint

### 8. External Dependencies
**Question**: Does this integrate with external APIs or services?
**Options**:
- No external dependencies
- Yes (describe which services)
- Not sure yet

---

## Adaptive Follow-ups

These are asked based on previous answers, not automatically.

### If Deployment = AWS
- Which AWS services? (Lambda, S3, SNS, SQS, DynamoDB, etc.)
- LocalStack for local development?

### If External Dependencies = Yes
- Authentication method? (API key, OAuth, JWT)
- Rate limits or quotas?
- Sandbox/test environment available?

### If Project Type = Web API
- What is the entry point? (FastAPI app, Flask app)
- Database? (PostgreSQL, DynamoDB, SQLite, none)

### If Existing Project
- What patterns does the current codebase use?
- What should we maintain for consistency?

---

## Domain Modeling (ask when architecture is confirmed)

### Core Entities
**Question**: What are the main domain concepts?
**Follow-up**: How do they relate to each other?

### Domain Events
**Question**: What state changes are worth tracking?
**Follow-up**: Who consumes these events?

---

_This question bank is non-exhaustive. Generate follow-up questions based on responses. Always adapt to context._
