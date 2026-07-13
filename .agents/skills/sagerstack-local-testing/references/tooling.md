<overview>
Python tooling configuration: Poetry for package management, pytest for testing, ruff for linting/formatting, mypy for type checking. All are mandatory.
</overview>

<poetry>
## Poetry (Package Management)

**Initialize project:**
```bash
poetry init
```

**Add dependencies:**
```bash
poetry add fastapi uvicorn sqlalchemy
poetry add --group dev pytest pytest-cov ruff mypy
```

**Run commands:**
```bash
poetry run pytest          # Run tests
poetry run python src/main.py  # Run application
poetry run ruff check .    # Lint
poetry run mypy src/       # Type check
```

**pyproject.toml structure:**
```toml
[tool.poetry]
name = "my-project"
version = "0.1.0"
description = "My Python project"
authors = ["Your Name <you@example.com>"]
readme = "README.md"

[tool.poetry.dependencies]
python = "^3.13"
fastapi = "^0.109"
uvicorn = "^0.27"
sqlalchemy = "^2.0"
pydantic-settings = "^2.1"
structlog = "^24.1"
boto3 = "^1.34"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^4.1"
pytest-asyncio = "^0.23"
ruff = "^0.1"
mypy = "^1.8"
boto3-stubs = "^1.34"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```
</poetry>

<pytest_config>
## pytest Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test*.py"]
python_classes = ["Test*"]
python_functions = ["test*"]
addopts = [
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-report=html:coverage_html",
    "--cov-fail-under=90",
    "-v",
    "--tb=short"
]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "e2e: marks tests as end-to-end tests",
    "localstack: marks tests requiring LocalStack",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/__init__.py",
    "*/migrations/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

**Running tests:**
```bash
# All tests with coverage
poetry run pytest

# Specific test file
poetry run pytest tests/unit/orders/testOrder.py

# Specific test function
poetry run pytest tests/unit/orders/testOrder.py::TestOrder::testPlaceOrder

# Only unit tests
poetry run pytest tests/unit/

# Exclude slow tests
poetry run pytest -m "not slow"

# With verbose output
poetry run pytest -v

# Stop on first failure
poetry run pytest -x

# Run in parallel (requires pytest-xdist)
poetry run pytest -n auto
```
</pytest_config>

<ruff_config>
## ruff Configuration (Linting + Formatting)

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py313"
exclude = [
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming (disabled for CamelCase)
    "W",   # pycodestyle warnings
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "DTZ", # flake8-datetimez
    "T10", # flake8-debugger
    "SIM", # flake8-simplify
    "TCH", # flake8-type-checking
]
ignore = [
    "N802",  # function name should be lowercase (we use camelCase)
    "N803",  # argument name should be lowercase (we use camelCase)
    "N806",  # variable name should be lowercase (we use camelCase)
    "N815",  # mixedCase variable in class scope (we use camelCase)
    "N816",  # mixedCase variable in global scope (we use camelCase)
]

[tool.ruff.lint.isort]
known-first-party = ["src"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"
```

**Running ruff:**
```bash
# Check for issues
poetry run ruff check .

# Auto-fix issues
poetry run ruff check --fix .

# Format code
poetry run ruff format .

# Check formatting without changes
poetry run ruff format --check .
```
</ruff_config>

<mypy_config>
## mypy Configuration (Type Checking)

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_configs = true

# Per-module overrides
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[[tool.mypy.overrides]]
module = [
    "boto3.*",
    "botocore.*",
]
ignore_missing_imports = true
```

**Running mypy:**
```bash
# Check all source code
poetry run mypy src/

# Check specific module
poetry run mypy src/orders/

# With verbose output
poetry run mypy src/ --verbose
```
</mypy_config>

<pre_commit>
## Pre-commit Hooks (Optional)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic
          - pydantic-settings
          - types-boto3

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

**Install hooks:**
```bash
poetry add --group dev pre-commit
poetry run pre-commit install
```

**Run manually:**
```bash
poetry run pre-commit run --all-files
```
</pre_commit>

<verification_checklist>
## Verification Checklist

Run before every commit:

```bash
#!/bin/bash
# verify.sh

echo "Running tests..."
poetry run pytest
if [ $? -ne 0 ]; then
    echo "❌ Tests failed"
    exit 1
fi
echo "✅ Tests passed"

echo "Checking coverage..."
poetry run pytest --cov --cov-fail-under=90
if [ $? -ne 0 ]; then
    echo "❌ Coverage below 90%"
    exit 1
fi
echo "✅ Coverage OK"

echo "Running linter..."
poetry run ruff check .
if [ $? -ne 0 ]; then
    echo "❌ Lint errors"
    exit 1
fi
echo "✅ Lint OK"

echo "Running type checker..."
poetry run mypy src/
if [ $? -ne 0 ]; then
    echo "❌ Type errors"
    exit 1
fi
echo "✅ Types OK"

echo "✅ All checks passed!"
```
</verification_checklist>
