<overview>
Configuration management for Python applications. Environment-based secrets with .env files for local development and AWS Secrets Manager for production.
</overview>

<confirm_environment_settings>
## Confirm Environment Settings (Required)

Before proceeding with configuration, confirm the following with the user:

### 1. Local Development Environment
- **Database**: What database will be used locally? (PostgreSQL, SQLite, etc.)
- **Port/Host**: Any specific ports or hosts for local services?
- **Debug mode**: Enable debug logging locally?

### 2. AWS Environment
- **LocalStack for local/tests?**: Will LocalStack simulate AWS services locally?
- **AWS Services used**: Which AWS services? (S3, SNS, SQS, Lambda, Secrets Manager, etc.)
- **AWS Region**: What region for deployment? (e.g., us-east-1)
- **Secrets Manager path**: What naming convention for secrets? (e.g., `myapp/database`, `myapp/api-keys`)

### 3. External Interfaces
- **APIs used**: What external APIs does the application integrate with? (e.g., Binance, Stripe, etc.)
- **Testnet available?**: Does the external API have a testnet/sandbox environment?
- **Testnet for local/tests?**: Should local development and tests use testnet?
- **API credentials scope**: Separate credentials for testnet vs production?

**Example confirmation prompt:**
```
Before setting up configuration, please confirm:

1. Local Development:
   - Database: PostgreSQL on localhost:5432?
   - Debug logging enabled?

2. AWS:
   - Using LocalStack for local/test AWS simulation?
   - Services: S3, SNS, SQS, Lambda, Secrets Manager?
   - Region: us-east-1?

3. External Interfaces (e.g., Binance):
   - Testnet for local development and tests?
   - Production API only in deployed environment?
   - Separate API keys for testnet vs production?
```

**Wait for user confirmation before generating configuration files.**
</confirm_environment_settings>

<environment_files>
## Environment Files

| File | Purpose | Git Status |
|------|---------|------------|
| `.env.example` | Template with placeholder values | Committed |
| `.env.local` | Local development secrets | Gitignored |
| `.env.tests` | Test execution secrets | Gitignored |

**Production:** AWS Secrets Manager (no .env files)

```
# .gitignore
.env.local
.env.tests
.env
```
</environment_files>

<env_example>
## .env.example (Template - Committed)

```bash
# .env.example
# Copy to .env.local and fill in values

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/mydb

# AWS (local uses LocalStack)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

# Application
DEBUG=false
ENVIRONMENT=local
LOG_LEVEL=INFO

# External APIs
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
```
</env_example>

<env_local>
## .env.local (Development - Gitignored)

```bash
# .env.local
# Local development configuration

# Database (local PostgreSQL)
DATABASE_URL=postgresql://devuser:devpass@localhost:5432/mydb_dev

# AWS (LocalStack)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_ENDPOINT_URL=http://localhost:4566

# Application
DEBUG=true
ENVIRONMENT=local
LOG_LEVEL=DEBUG

# External APIs (testnet)
BINANCE_API_KEY=actual_testnet_key
BINANCE_API_SECRET=actual_testnet_secret
BINANCE_ENV=testnet
```
</env_local>

<env_tests>
## .env.tests (Testing - Gitignored)

```bash
# .env.tests
# Test execution configuration
# Tests use ONLY this file, never .env.local

# Database (test database or in-memory)
DATABASE_URL=postgresql://testuser:testpass@localhost:5432/mydb_test

# AWS (LocalStack for integration tests)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_ENDPOINT_URL=http://localhost:4566
USE_LOCALSTACK=true

# Application
DEBUG=false
ENVIRONMENT=local
LOG_LEVEL=WARNING

# External APIs (testnet for integration tests)
BINANCE_API_KEY=testnet_key_for_tests
BINANCE_API_SECRET=testnet_secret_for_tests
BINANCE_ENV=testnet
```
</env_tests>

<pydantic_settings>
## Pydantic Settings Configuration

```python
# src/shared/infrastructure/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    databaseUrl: str

    # AWS
    awsRegion: str = "us-east-1"
    awsAccessKeyId: str | None = None
    awsSecretAccessKey: str | None = None
    awsEndpointUrl: str | None = None  # For LocalStack

    # Application
    debug: bool = False
    environment: str = "local"  # local | prod
    logLevel: str = "INFO"

    # Feature flags
    useLocalstack: bool = False

    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"
        # Convert UPPER_SNAKE_CASE env vars to camelCase fields
        # DATABASE_URL -> databaseUrl
        env_prefix = ""

        @classmethod
        def customise_sources(cls, initSettings, envSettings, fileSettings):
            # Priority: env vars > .env file > defaults
            return (envSettings, fileSettings, initSettings)

@lru_cache
def getSettings() -> Settings:
    return Settings()

settings = getSettings()
```
</pydantic_settings>

<test_settings>
## Test Settings

```python
# src/shared/infrastructure/testConfig.py
from pydantic_settings import BaseSettings

class TestSettings(BaseSettings):
    """Settings for test execution - uses .env.tests ONLY"""

    # Database
    databaseUrl: str = "sqlite:///:memory:"

    # AWS (LocalStack)
    awsRegion: str = "us-east-1"
    awsAccessKeyId: str = "test"
    awsSecretAccessKey: str = "test"
    awsEndpointUrl: str = "http://localhost:4566"
    useLocalstack: bool = True

    # Application
    debug: bool = False
    environment: str = "local"
    logLevel: str = "WARNING"

    class Config:
        env_file = ".env.tests"  # Tests use ONLY this file
        env_file_encoding = "utf-8"

def getTestSettings() -> TestSettings:
    return TestSettings()
```

```python
# tests/conftest.py
import pytest
from src.shared.infrastructure.testConfig import getTestSettings

@pytest.fixture(scope="session")
def settings():
    return getTestSettings()

@pytest.fixture(scope="session")
def dbSession(settings):
    # Create test database session
    engine = createEngine(settings.databaseUrl)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
```
</test_settings>

<aws_secrets_manager>
## AWS Secrets Manager (Production)

```python
# src/shared/infrastructure/secrets.py
import boto3
import json
from functools import lru_cache

class SecretsManager:
    def __init__(self, region: str = "us-east-1"):
        self._client = boto3.client("secretsmanager", region_name=region)

    def getSecret(self, secretName: str) -> dict:
        response = self._client.get_secret_value(SecretId=secretName)
        return json.loads(response["SecretString"])

@lru_cache
def getSecretsManager() -> SecretsManager:
    return SecretsManager()

# Usage in production config
class ProductionSettings(BaseSettings):
    environment: str = "prod"

    @property
    def databaseUrl(self) -> str:
        secrets = getSecretsManager().getSecret("myapp/database")
        return secrets["url"]

    @property
    def binanceApiKey(self) -> str:
        secrets = getSecretsManager().getSecret("myapp/binance")
        return secrets["apiKey"]
```
</aws_secrets_manager>

<environment_switching>
## Environment Switching Pattern

```python
# src/shared/infrastructure/config.py
import os
from functools import lru_cache

def getSettings():
    """Return appropriate settings based on environment."""
    environment = os.environ.get("ENVIRONMENT", "local")

    if environment == "prod":
        return ProductionSettings()
    else:
        return Settings()  # Uses .env.local

# In tests
def getTestSettings():
    """Always return test settings using .env.tests"""
    return TestSettings()
```

```python
# Lambda handler
def lambdaHandler(event, context):
    environment = os.environ.get("ENVIRONMENT", "local")

    if environment == "prod":
        # Production: use AWS Secrets Manager
        secrets = getSecretsManager().getSecret("myapp/config")
        apiKey = secrets["binanceApiKey"]
    else:
        # Local: use environment variables
        apiKey = os.environ["BINANCE_API_KEY"]
```
</environment_switching>

<best_practices>
## Best Practices

1. **Never commit secrets** - .env.local and .env.tests are always gitignored
2. **Tests use .env.tests only** - Never mix test and development configs
3. **Production uses Secrets Manager** - No .env files in production
4. **Template is committed** - .env.example shows required variables
5. **Fail fast on missing config** - Don't provide defaults for secrets
6. **Separate secrets from config** - Secrets are credentials, config is settings

```python
# ❌ WRONG: Default for secret
class Settings(BaseSettings):
    apiKey: str = "default-key"  # Never default secrets!

# ✅ CORRECT: Required secret
class Settings(BaseSettings):
    apiKey: str  # Will fail if not provided

# ✅ CORRECT: Default for non-secret config
class Settings(BaseSettings):
    logLevel: str = "INFO"  # OK to default
    debug: bool = False     # OK to default
```
</best_practices>
