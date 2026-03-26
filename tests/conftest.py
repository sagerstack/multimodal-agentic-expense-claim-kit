"""Pytest configuration and fixtures."""

import pytest
from agentic_claims.core.config import Settings


@pytest.fixture
def testSettings() -> Settings:
    """Load test settings from .env.test file."""
    return Settings(_env_file="tests/.env.test")


@pytest.fixture
def e2eSettings() -> Settings:
    """Load E2E settings from .env.e2e file.

    Requires running Docker services (docker compose up) and valid OpenRouter API key.
    """
    return Settings(_env_file=".env.e2e")
