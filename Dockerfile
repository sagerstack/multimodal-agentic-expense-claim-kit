FROM python:3.11-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy source code and project definition
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies
RUN pip install --no-cache-dir .

# Expose port (configured via .env, defaults to 8000)
EXPOSE 8000

# Run Chainlit app
CMD ["chainlit", "run", "src/agentic_claims/app.py", "--host", "0.0.0.0", "--port", "8000"]
