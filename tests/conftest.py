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


@pytest.fixture(autouse=True)
def _resetGovernanceRuntimes():
    """Reset global content governance runtimes between tests.

    Some tests (e.g. e2e live-stack tests, test_governance_*) call
    buildGraph() which installs module-global runtimes on
    `agentic_claims.core.graph`:

      - contentHookRuntime           (intake / live chat notices)
      - contentHookRuntime_background (background agents)

    Once installed, these runtimes persist for the rest of the pytest
    process. Downstream tests that pass a FakeLlm to buildIntakeGptSubgraph
    assume the runtime is None (so the B1/B2 pre-check is skipped); if a
    prior test installed a real runtime, the pre-check runs and may fail
    on the optional presidio-analyzer PII dependency.

    This autouse fixture restores both globals to None after each test so
    that test ordering does not affect runtime identity. Tests that need
    the runtimes set should install them explicitly.
    """
    yield
    try:
        from agentic_claims.core import graph as _graph
        _graph.contentHookRuntime = None
        _graph.contentHookRuntime_background = None
    except Exception:
        # If the module is not importable for any reason, swallow — the
        # test should still be allowed to proceed; this fixture is purely
        # defensive isolation.
        pass
