---
name: sagerstack:local-testing
description: Testing infrastructure, local environment simulation, and deployment scripts. Use when setting up pytest fixtures, Docker Compose, LocalStack, mocking external services, or creating local deployment scripts. Focuses on HOW to test and run locally, not coding principles (TDD is in software-engineering).
---

<essential_principles>

## How Local Testing Infrastructure Works

These principles ALWAYS apply when setting up testing and local execution environments.

### 1. Docker-First Local Execution

The app MUST be able to completely execute locally using Docker and container images that simulate third-party services and production infrastructure.

- All external dependencies (databases, message queues, AWS services) run in containers
- LocalStack for AWS services (S3, SNS, SQS, Lambda, Secrets Manager)
- No reliance on actual cloud services for local development

```yaml
# docker-compose.yml - Everything runs locally
services:
  localstack:
    image: localstack/localstack:3.7.2
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,sns,sqs,secretsmanager,lambda

  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### 2. Third-Party Integration Clarity

When third-party integrations are involved, ALWAYS clarify with the user:
- Should this use real integration (actual API calls)?
- Or should it be mocked (container simulation)?

**Never assume.** Ask explicitly before implementing.

### 3. Environment Configuration Files

| File | Purpose | Source Control |
|------|---------|----------------|
| `.env.example` | Template with all required vars (no secrets) | Committed |
| `.env.local` | Local development configuration | Gitignored |
| `tests/.env.test` | Test configuration | Gitignored |

**Critical rules:**
- Tests ALWAYS load from `tests/.env.test`
- Local execution ALWAYS loads from `.env.local`
- All three files MUST stay in sync (same variables, different values)
- Only `.env.example` is checked into source control

```python
# tests/conftest.py
from pathlib import Path
from dotenv import load_dotenv

# Load test environment at the START of test collection
testEnvPath = Path(__file__).parent / ".env.test"
load_dotenv(testEnvPath)
```

### 4. Local Deployment Scripts

All local deployment scripts live under `scripts/local/`:

| Script | Purpose |
|--------|---------|
| `deploy-infrastructure.sh` | Spin up Docker containers (LocalStack, DBs, etc.) |
| `deploy-config.sh` | Load configuration, create secrets in LocalStack |
| `deploy-app.sh` | Build and deploy the application locally |

**Production-grade requirement:** These scripts should be written so that creating production versions requires MINIMAL changes. Same structure, same approach - just different targets.

```bash
scripts/
├── local/
│   ├── deploy-infrastructure.sh    # Start containers
│   ├── deploy-config.sh            # Load secrets/configs
│   └── deploy-app.sh               # Deploy application
└── aws/
    ├── deploy-infrastructure.sh    # Terraform apply
    ├── deploy-config.sh            # Load secrets to AWS
    └── deploy-app.sh               # Deploy to AWS
```

### 5. Horizontal Test Structure

```
tests/
├── .env.test              # Test configuration
├── conftest.py            # Shared fixtures
├── unit/                  # Fast, isolated tests
│   └── {slice}/
│       ├── testOrder.py
│       └── testPlaceOrder.py
├── integration/           # Tests with real dependencies
│   └── {slice}/
│       └── testSqlalchemyRepo.py
└── e2e/                   # Full workflow tests
    └── testOrderWorkflow.py
```

### 6. Tooling Stack

```toml
[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^4.0"
pytest-asyncio = "^0.23"
pytest-mock = "^3.12"
ruff = "^0.1"
mypy = "^1.8"
docker = "^7.0"
localstack = "^3.0"
python-dotenv = "^1.0"
```

**Commands:**
```bash
poetry run pytest                    # Run tests
poetry run pytest --cov             # With coverage
poetry run pytest -m "not slow"     # Skip slow tests
poetry run pytest tests/unit/       # Only unit tests
```

### 7. CamelCase in Tests

```python
# Test files
tests/unit/orders/testOrder.py

# Test functions
def testPlaceOrderWithEmptyCart():
    pass

def testCannotPlaceEmptyOrder():
    pass

# Test classes
class TestOrderService:
    def testCalculateTotal(self):
        pass
```

</essential_principles>

<intake>
**What would you like to do?**

1. Set up Docker Compose / LocalStack environment
2. Create local deployment scripts (scripts/local/)
3. Set up test fixtures and conftest
4. Configure environment files (.env.*)
5. Mock external APIs and third-party services
6. Debug test or local environment issues
7. Something else

**Wait for response, then read the matching workflow.**
</intake>

<routing>
| Response | Workflow |
|----------|----------|
| 1, "docker", "localstack", "compose", "containers" | `workflows/setup-localstack.md` |
| 2, "scripts", "deploy", "local scripts" | `workflows/create-deployment-scripts.md` |
| 3, "fixtures", "conftest", "setup" | `workflows/setup-test-fixtures.md` |
| 4, "env", ".env", "environment", "config" | `workflows/configure-env-files.md` |
| 5, "mock", "external", "api", "third-party" | `workflows/mock-external-services.md` |
| 6, "debug", "failing", "issue", "problem" | `workflows/debug-local-environment.md` |
| 7, other | Clarify, then select workflow or references |
</routing>

<reference_index>
## Domain Knowledge

All in `references/`:

**Testing Infrastructure:**
- pytest-patterns.md - Fixtures, parametrize, markers
- mocking-strategies.md - When and how to mock
- testing-pyramid.md - Unit/integration/e2e strategy

**Local Execution:**
- localstack.md - AWS local development
- docker-compose.md - Multi-container setup
- minikube.md - Local Kubernetes

**Configuration:**
- env-file-management.md - .env file conventions and sync
- secrets-local.md - LocalStack Secrets Manager setup

**Deployment Scripts:**
- script-conventions.md - Production-grade shell scripts
</reference_index>

<workflows_index>
## Workflows

All in `workflows/`:

| File | Purpose |
|------|---------|
| setup-localstack.md | Docker Compose + LocalStack setup |
| create-deployment-scripts.md | Create scripts/local/ structure |
| setup-test-fixtures.md | Configure conftest and fixtures |
| configure-env-files.md | Set up .env.* file structure |
| mock-external-services.md | Mock third-party APIs |
| debug-local-environment.md | Troubleshoot local dev issues |
</workflows_index>

<verification>
## After Local Environment Setup

```bash
# 1. Docker containers running
docker-compose ps

# 2. LocalStack healthy
curl http://localhost:4566/_localstack/health

# 3. Environment files in sync
diff <(grep -v '^#' .env.example | sort) <(grep -v '^#' .env.local | cut -d= -f1 | sort)

# 4. Tests use correct environment
poetry run pytest tests/ -v --collect-only | head -20

# 5. All scripts executable and pass shellcheck
shellcheck scripts/local/*.sh
```

Checklist:
- [ ] Docker Compose file includes all required services
- [ ] LocalStack configured with needed AWS services
- [ ] .env.example, .env.local, and tests/.env.test are in sync
- [ ] conftest.py loads tests/.env.test at startup
- [ ] Local deployment scripts are idempotent (safe to run multiple times)
- [ ] Scripts have proper error handling (set -euo pipefail)
</verification>
