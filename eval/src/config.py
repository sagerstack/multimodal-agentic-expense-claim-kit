"""Eval suite configuration -- loads judge model and credentials from environment.

Decoupled from the app (no imports from agentic_claims).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from deepeval.models import LiteLLMModel

_EVAL_DIR = Path(__file__).resolve().parent.parent


@dataclass
class EvalConfig:
    judgeModel: LiteLLMModel
    appUrl: str
    dbUrl: str
    resultsDir: Path
    invoicesDir: Path
    evalUsername: str
    evalPassword: str


def getEvalConfig() -> EvalConfig:
    """Read environment variables, validate required keys, return EvalConfig.

    Required env vars:
      OPENROUTER_API_KEY   -- judge LLM authentication

    Deliberately NOT required: ANTHROPIC_API_KEY. The capture subagent runs via
    the `claude` CLI, which authenticates with the local subscription login. If
    ANTHROPIC_API_KEY is present in the environment the CLI switches to API-key
    auth and fails with "Invalid API key" unless the key is a real, valid one --
    so requiring a placeholder here actively broke capture. runner.py clears the
    variable before spawning the subprocess.

    Optional env vars (have defaults):
      EVAL_APP_URL         -- default http://localhost:8000
      DATABASE_URL         -- default postgresql://agentic:agentic_password@localhost:5432/agentic_claims
      EVAL_USERNAME        -- default employee1
      EVAL_PASSWORD        -- default password123
    """
    openrouterApiKey = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouterApiKey:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required for the judge model"
        )

    judgeModel = LiteLLMModel(
        model="openrouter/openai/gpt-4o",
        api_key=openrouterApiKey,
        base_url="https://openrouter.ai/api/v1",
    )

    appUrl = os.environ.get("EVAL_APP_URL", "http://localhost:8000")
    dbUrl = os.environ.get(
        "DATABASE_URL",
        "postgresql://agentic:agentic_password@localhost:5432/agentic_claims",
    )
    # Defaults match a seeded "user"-role account from migration 005 (password
    # convention is "<username>123"). The previous employee1/password123
    # defaults matched no real account, so capture failed at login.
    evalUsername = os.environ.get("EVAL_USERNAME", "sagar")
    evalPassword = os.environ.get("EVAL_PASSWORD", "sagar123")

    return EvalConfig(
        judgeModel=judgeModel,
        appUrl=appUrl,
        dbUrl=dbUrl,
        resultsDir=_EVAL_DIR / os.environ.get("EVAL_RESULTS_DIR", "results"),
        invoicesDir=_EVAL_DIR / "invoices",
        evalUsername=evalUsername,
        evalPassword=evalPassword,
    )
