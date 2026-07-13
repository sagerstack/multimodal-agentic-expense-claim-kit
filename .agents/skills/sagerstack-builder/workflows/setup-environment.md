# Workflow: Setup Environment

TODO: Detailed step-by-step workflow for pre-implementation local environment setup.

## Scope

This workflow prepares the local development environment before any implementation tasks are assigned. Run when:
- Starting a new phase build
- Environment issues detected during implementation
- User explicitly requests environment setup

## Steps

1. **Verify Git State**:
   - Check current branch (`git branch --show-current`)
   - Verify clean working tree (`git status`)
   - If on main, prepare for branch creation
   - If on feature branch, verify it is up to date with main

2. **Check Python Environment**:
   - Verify Python version (`python --version`, should be 3.11+)
   - Verify Poetry installed (`poetry --version`)
   - Install dependencies (`poetry install`)
   - Verify virtual environment active

3. **Check Docker Environment**:
   - Verify Docker running (`docker info`)
   - Verify Docker Compose available (`docker-compose version`)
   - If docker-compose.yml exists, build images (`docker-compose build`)
   - If LocalStack needed, verify it starts (`docker-compose up -d localstack`)

4. **Verify Environment Files**:
   - Check `.env.example` exists (should be committed)
   - Check `.env.local` exists (create from `.env.example` if missing)
   - Check `tests/.env.test` exists (create from `.env.example` if missing)
   - Verify all three files have the same variables (different values)

5. **Verify Test Infrastructure**:
   - Check `tests/conftest.py` loads `tests/.env.test`
   - Run a quick test smoke test (`poetry run pytest tests/ --collect-only`)
   - Verify test directories exist (`tests/unit/`, `tests/integration/`, `tests/e2e/`)

6. **Verify Quality Tools**:
   - Check mypy installed (`poetry run mypy --version`)
   - Check ruff installed (`poetry run ruff --version`)
   - Check bandit installed (`poetry run bandit --version`)
   - Check pytest-cov installed (`poetry run pytest --co -q | head -1`)

7. **Report Environment Status**:
   ```
   ENVIRONMENT STATUS:
   - Python: {version} OK / MISSING
   - Poetry: {version} OK / MISSING
   - Docker: OK / NOT RUNNING
   - Docker Compose: OK / MISSING
   - .env.example: OK / MISSING
   - .env.local: OK / MISSING (created from template)
   - tests/.env.test: OK / MISSING (created from template)
   - Test infrastructure: OK / ISSUES
   - Quality tools: OK / MISSING ({list})

   Ready to build: YES / NO (issues: {list})
   ```

## Escalation

If environment cannot be prepared (Docker not installed, Python version wrong, etc.):
- Use escalation protocol Category 2 (Infrastructure Failure)
- Inform user of specific missing components
- Provide installation instructions if possible

## References

- /sagerstack:local-testing skill (Docker-first, env file management)
- references/escalation-protocol.md (Category 2: Infrastructure Failure)
