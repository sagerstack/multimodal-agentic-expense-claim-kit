FROM python:3.11-slim

# Install system packages: curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Build-time pip trusted hosts (workaround for SSL cert interception in Docker build)
ENV PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org pypi.python.org"

# Install poetry + export plugin for lock file conversion
RUN pip install --no-cache-dir poetry poetry-plugin-export

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# --- Governance layer (Option 2: parent additional build context) ---
# Bring the agentic-governance package in from the sibling repo and place it where
# the pyproject path-dep expects it (../agentic-governance == /agentic-governance,
# sibling of WORKDIR /app). Requires `additional_contexts: {governance: ../agentic-governance}`
# on the app build in docker-compose.yml.
COPY --from=governance . /agentic-governance

# Export app deps via poetry. startup.sh runs `poetry lock` first, so the copied
# poetry.lock is consistent with pyproject.toml (which includes the governance
# path-dep) and `poetry export` will NOT fail on a freshness check. We strip any
# governance line out of the exported requirements (poetry may emit an unusable
# host path for a directory dep) and install governance explicitly from the copied
# context instead — /agentic-governance is the sibling of /app that the path-dep
# `../agentic-governance` resolves to.
RUN poetry export --without dev -f requirements.txt -o requirements.txt \
    && grep -vi 'agentic-governance' requirements.txt > requirements.clean.txt || true \
    && pip install --no-cache-dir -r requirements.clean.txt \
    && rm -f requirements.txt requirements.clean.txt \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu --trusted-host download.pytorch.org \
    && pip install --no-cache-dir "/agentic-governance[content]" \
    && python -m spacy download en_core_web_lg \
    && (python -c "from transformers import pipeline; pipeline('text-classification', model='protectai/deberta-v3-base-prompt-injection-v2')" || echo 'WARN: DeBERTa pre-pull failed at build; will lazy-load at runtime')

# Copy source code, config, Alembic migrations, and web assets
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY templates/ ./templates/
COPY static/ ./static/

# Install root project (no deps — already installed above)
RUN pip install --no-cache-dir --no-deps .

# Clear build-time trusted hosts for runtime
ENV PIP_TRUSTED_HOST=""

# Expose port
EXPOSE 8000

# Run FastAPI app via uvicorn
CMD ["uvicorn", "agentic_claims.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
