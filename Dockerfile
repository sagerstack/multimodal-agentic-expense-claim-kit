FROM python:3.11-slim

# Install curl for healthcheck, ca-certificates for SSL, and poetry for dependency management
RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies only (no root project, no dev deps)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev --no-root

# Upgrade certifi to latest CA bundle
RUN pip install --no-cache-dir --upgrade certifi

# Copy source code, config, and Alembic migrations
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY .chainlit/ ./.chainlit/
COPY public/ ./public/

# Install root project
RUN poetry install --no-interaction --no-ansi --without dev

# Set environment variable to use system CA certificates
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Expose port
EXPOSE 8000

# Run Chainlit app
CMD ["chainlit", "run", "src/agentic_claims/app.py", "--host", "0.0.0.0", "--port", "8000"]
