"""Pytest configuration and fixtures."""

import pytest
from agentic_claims.core.config import Settings


@pytest.fixture
def testSettings() -> Settings:
    """Load test settings from .env.test file."""
    return Settings(_env_file="tests/.env.test")
