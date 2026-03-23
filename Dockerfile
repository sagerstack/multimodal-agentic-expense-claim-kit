FROM python:3.11-slim

# Install curl for healthcheck and poetry for dependency management
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies only (no root project, no dev deps)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev --no-root

# Copy source code
COPY src/ ./src/

# Install root project
RUN poetry install --no-interaction --no-ansi --without dev

# Expose port
EXPOSE 8000

# Run Chainlit app
CMD ["chainlit", "run", "src/agentic_claims/app.py", "--host", "0.0.0.0", "--port", "8000"]
