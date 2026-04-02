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

# Export lock file to requirements.txt and install via pip
RUN poetry export --without dev -f requirements.txt -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && rm requirements.txt

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
