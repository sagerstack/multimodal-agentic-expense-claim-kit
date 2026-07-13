<overview>
Docker Compose setup for local multi-container development environments. Orchestrates LocalStack, databases, and application services.
</overview>

<basic_setup>
## Basic docker-compose.yml

```yaml
# docker-compose.yml
version: "3.8"

services:
  # LocalStack for AWS services
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,sns,sqs,secretsmanager,events,lambda
      - DEBUG=1
      - DATA_DIR=/var/lib/localstack/data
    volumes:
      - "./localstack-data:/var/lib/localstack"
      - "/var/run/docker.sock:/var/run/docker.sock"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  # PostgreSQL database
  postgres:
    image: postgres:15
    container_name: postgres
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=devuser
      - POSTGRES_PASSWORD=devpass
      - POSTGRES_DB=mydb_dev
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devuser -d mydb_dev"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis for caching
  redis:
    image: redis:7-alpine
    container_name: redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres-data:
```
</basic_setup>

<commands>
## Docker Compose Commands

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d postgres

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f localstack

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Rebuild containers
docker-compose up -d --build

# Check status
docker-compose ps

# Execute command in container
docker-compose exec postgres psql -U devuser -d mydb_dev
```
</commands>

<wait_scripts>
## Wait-for-Ready Scripts

```bash
#!/bin/bash
# scripts/wait-for-localstack.sh

echo "Waiting for LocalStack..."
until curl -s http://localhost:4566/_localstack/health | grep -q '"s3": "available"'; do
  echo "  LocalStack not ready..."
  sleep 2
done
echo "LocalStack ready!"
```

```bash
#!/bin/bash
# scripts/wait-for-postgres.sh

echo "Waiting for PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U devuser -d mydb_dev > /dev/null 2>&1; do
  echo "  PostgreSQL not ready..."
  sleep 2
done
echo "PostgreSQL ready!"
```

```bash
#!/bin/bash
# scripts/start-dev.sh

# Start services
docker-compose up -d

# Wait for services
./scripts/wait-for-postgres.sh
./scripts/wait-for-localstack.sh

# Initialize LocalStack resources
./scripts/init-localstack.sh

echo "Development environment ready!"
```
</wait_scripts>

<init_scripts>
## LocalStack Initialization

```bash
#!/bin/bash
# scripts/init-localstack.sh

ENDPOINT="http://localhost:4566"

echo "Initializing LocalStack resources..."

# Create S3 bucket
aws --endpoint-url=$ENDPOINT s3 mb s3://my-bucket 2>/dev/null || true

# Create SNS topic
aws --endpoint-url=$ENDPOINT sns create-topic --name order-events 2>/dev/null || true

# Create SQS queue
aws --endpoint-url=$ENDPOINT sqs create-queue --queue-name order-queue 2>/dev/null || true

# Subscribe queue to topic
TOPIC_ARN="arn:aws:sns:us-east-1:000000000000:order-events"
QUEUE_ARN="arn:aws:sqs:us-east-1:000000000000:order-queue"
aws --endpoint-url=$ENDPOINT sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol sqs \
  --notification-endpoint $QUEUE_ARN 2>/dev/null || true

# Create secret
aws --endpoint-url=$ENDPOINT secretsmanager create-secret \
  --name myapp/config \
  --secret-string '{"apiKey":"test-key"}' 2>/dev/null || true

echo "LocalStack initialization complete!"
```
</init_scripts>

<test_compose>
## Test-Specific Compose

```yaml
# docker-compose.test.yml
version: "3.8"

services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack-test
    ports:
      - "4567:4566"  # Different port for tests
    environment:
      - SERVICES=s3,sns,sqs,secretsmanager
      - DEBUG=0

  postgres-test:
    image: postgres:15
    container_name: postgres-test
    ports:
      - "5433:5432"  # Different port for tests
    environment:
      - POSTGRES_USER=testuser
      - POSTGRES_PASSWORD=testpass
      - POSTGRES_DB=mydb_test
    tmpfs:
      - /var/lib/postgresql/data  # In-memory for speed
```

```bash
# Run tests with test compose
docker-compose -f docker-compose.test.yml up -d
poetry run pytest tests/integration/
docker-compose -f docker-compose.test.yml down
```
</test_compose>

<multi_service>
## Multi-Service Application

```yaml
# docker-compose.yml
version: "3.8"

services:
  # Infrastructure
  localstack:
    image: localstack/localstack:latest
    # ... config

  postgres:
    image: postgres:15
    # ... config

  redis:
    image: redis:7-alpine
    # ... config

  # Application services
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://devuser:devpass@postgres:5432/mydb_dev
      - REDIS_URL=redis://redis:6379
      - AWS_ENDPOINT_URL=http://localstack:4566
      - USE_LOCALSTACK=true
    depends_on:
      postgres:
        condition: service_healthy
      localstack:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./src:/app/src:ro
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: worker
    environment:
      - DATABASE_URL=postgresql://devuser:devpass@postgres:5432/mydb_dev
      - AWS_ENDPOINT_URL=http://localstack:4566
    depends_on:
      - api
    command: python -m src.worker
```

```dockerfile
# Dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy source
COPY src/ ./src/

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
</multi_service>

<env_file>
## Environment File Integration

```yaml
# docker-compose.yml
services:
  api:
    env_file:
      - .env.local
    environment:
      # Override specific values
      - DATABASE_URL=postgresql://devuser:devpass@postgres:5432/mydb_dev
```

**.env.local:**
```bash
DEBUG=true
LOG_LEVEL=DEBUG
AWS_REGION=us-east-1
```
</env_file>

<troubleshooting>
## Troubleshooting

**Container won't start:**
```bash
# Check logs
docker-compose logs localstack

# Check health status
docker inspect localstack --format='{{.State.Health.Status}}'

# Restart specific container
docker-compose restart localstack
```

**Port conflicts:**
```bash
# Find what's using a port
lsof -i :4566

# Use different ports in compose
ports:
  - "4567:4566"  # host:container
```

**Volume issues:**
```bash
# Remove all volumes and start fresh
docker-compose down -v
docker volume prune
docker-compose up -d
```

**Network issues:**
```bash
# Inspect network
docker network inspect crypto-momentum-trading_default

# Containers communicate via service names
# api -> http://localstack:4566 (not localhost)
```
</troubleshooting>
