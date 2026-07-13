# UAT Patterns Reference

## Purpose

Common User Acceptance Testing patterns for the QA agent. Covers Docker-based UAT, local process UAT, health check strategies, HTTP assertion patterns, and cleanup procedures.

---

## UAT Detection Logic

Before running UAT, determine the execution model:

```
1. Does docker-compose.yml exist in project root?
   YES -> UAT via Docker (preferred)
   NO  -> Continue to step 2

2. Does an application entry point exist?
   (e.g., src/main.py, src/app.py, or FastAPI/Flask app module)
   YES -> UAT via Local Process
   NO  -> Skip UAT, document as SKIPPED in report

3. Does the project have any Functional - End-to-End ACs?
   YES -> UAT is expected. If no execution model found, flag as issue.
   NO  -> UAT may be optional. Skip with note.
```

---

## UAT via Docker

### Prerequisites

- Docker daemon running
- `docker-compose.yml` present in project root
- All required environment files present (`.env.local` for integration services)

### Execution Flow

```bash
# Step 1: Clean previous state
docker-compose down --remove-orphans 2>/dev/null

# Step 2: Build with latest code (CRITICAL: always rebuild)
docker-compose up -d --build

# Step 3: Wait for health check
MAX_WAIT=30
for i in $(seq 1 $MAX_WAIT); do
  if curl -sf http://localhost:{port}/health > /dev/null 2>&1; then
    echo "Health check passed after ${i}s"
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    echo "FAIL: Health check timeout after ${MAX_WAIT}s"
    docker-compose logs
    docker-compose down
    exit 1
  fi
  sleep 1
done

# Step 4: Run E2E test scenarios
# (see HTTP Assertion Patterns below)

# Step 5: Capture logs for evidence
docker-compose logs > /tmp/uat-logs.txt 2>&1

# Step 6: Tear down
docker-compose down
```

### Port Discovery

If the port is not obvious from AC or impl plan, discover it:

```bash
# Check docker-compose.yml for port mappings
grep -A2 "ports:" docker-compose.yml

# Check running containers
docker-compose ps

# Common ports
# FastAPI: 8000
# Flask: 5000
# Django: 8000
# Node: 3000
```

### Multi-Service Docker Compose

When docker-compose defines multiple services (app + database + cache):

```bash
# Wait for all services to be healthy
docker-compose up -d --build

# Check individual service health
docker-compose ps  # All should show "Up" or "healthy"

# If a service has a health check defined:
docker inspect --format='{{.State.Health.Status}}' {container_name}

# Wait for dependent services first
# e.g., Database must be ready before app can start
for i in $(seq 1 30); do
  docker-compose exec -T postgres pg_isready && break
  sleep 1
done

# Then wait for the application
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/health && break
  sleep 1
done
```

---

## UAT via Local Process

### Prerequisites

- Poetry environment set up (`poetry install` completed)
- `.env.local` present if integration services needed
- No port conflicts on the application port

### Execution Flow

```bash
# Step 1: Start application in background
poetry run python -m src.main &
APP_PID=$!

# Step 2: Wait for startup
MAX_WAIT=10
for i in $(seq 1 $MAX_WAIT); do
  if curl -sf http://localhost:{port}/health > /dev/null 2>&1; then
    echo "App started after ${i}s"
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    echo "FAIL: App failed to start after ${MAX_WAIT}s"
    kill $APP_PID 2>/dev/null
    exit 1
  fi
  sleep 1
done

# Step 3: Run E2E test scenarios
# (see HTTP Assertion Patterns below)

# Step 4: Stop application
kill $APP_PID 2>/dev/null
wait $APP_PID 2>/dev/null
```

### Finding the Entry Point

```bash
# Check for common entry points
ls src/main.py src/app.py 2>/dev/null

# Check pyproject.toml for scripts
grep -A5 "\[tool.poetry.scripts\]" pyproject.toml

# Check for FastAPI app
grep -rn "FastAPI()" src/ --include="*.py"

# Check for Flask app
grep -rn "Flask(__name__)" src/ --include="*.py"
```

---

## HTTP Assertion Patterns

### Basic GET Request

```bash
# Test a GET endpoint
response=$(curl -s http://localhost:{port}/{endpoint})
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/{endpoint})

# Assert status code
if [ "$status" != "200" ]; then
  echo "FAIL: GET /{endpoint} expected 200, got $status"
  echo "Response: $response"
fi

# Assert response body contains expected field
echo "$response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert 'expectedField' in data, f'Missing expectedField in response: {data}'
print('PASS: expectedField present')
"
```

### POST Request with JSON Body

```bash
# Test a POST endpoint
response=$(curl -s -X POST http://localhost:{port}/{endpoint} \
  -H "Content-Type: application/json" \
  -d '{"field1": "value1", "field2": "value2"}')
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:{port}/{endpoint} \
  -H "Content-Type: application/json" \
  -d '{"field1": "value1", "field2": "value2"}')

# Assert 201 Created
if [ "$status" != "201" ]; then
  echo "FAIL: POST /{endpoint} expected 201, got $status"
  echo "Response: $response"
fi
```

### Error Response Validation

```bash
# Test invalid input returns proper error
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:{port}/{endpoint} \
  -H "Content-Type: application/json" \
  -d '{"invalid": "data"}')

# Assert 400 Bad Request (not 500)
if [ "$status" != "400" ]; then
  echo "FAIL: Invalid input expected 400, got $status"
fi

# Assert error response has proper structure
response=$(curl -s -X POST http://localhost:{port}/{endpoint} \
  -H "Content-Type: application/json" \
  -d '{"invalid": "data"}')

echo "$response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert 'error' in data or 'detail' in data, 'Error response missing error/detail field'
print('PASS: Error response properly structured')
"
```

### Authentication Testing

```bash
# Test unauthenticated access
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/protected)
if [ "$status" != "401" ]; then
  echo "FAIL: Unauthenticated access expected 401, got $status"
fi

# Test authenticated access
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/protected \
  -H "Authorization: Bearer {test_token}")
if [ "$status" != "200" ]; then
  echo "FAIL: Authenticated access expected 200, got $status"
fi
```

### Workflow Testing (Create -> Read -> Update -> Delete)

```bash
# Step 1: Create
createResponse=$(curl -s -X POST http://localhost:{port}/items \
  -H "Content-Type: application/json" \
  -d '{"name": "test-item"}')
itemId=$(echo "$createResponse" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Step 2: Read
readResponse=$(curl -s http://localhost:{port}/items/$itemId)
readStatus=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/items/$itemId)
test "$readStatus" = "200" || echo "FAIL: Read expected 200, got $readStatus"

# Step 3: Update
updateStatus=$(curl -s -o /dev/null -w "%{http_code}" -X PUT http://localhost:{port}/items/$itemId \
  -H "Content-Type: application/json" \
  -d '{"name": "updated-item"}')
test "$updateStatus" = "200" || echo "FAIL: Update expected 200, got $updateStatus"

# Step 4: Delete
deleteStatus=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE http://localhost:{port}/items/$itemId)
test "$deleteStatus" = "204" || echo "FAIL: Delete expected 204, got $deleteStatus"

# Step 5: Verify deleted
verifyStatus=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/items/$itemId)
test "$verifyStatus" = "404" || echo "FAIL: Verify deleted expected 404, got $verifyStatus"
```

---

## Health Check Patterns

### Simple Health Endpoint

```bash
curl -sf http://localhost:{port}/health
```

Expected response: `200 OK` with body like `{"status": "healthy"}` or `{"status": "ok"}`

### Health Check with Dependencies

Some apps expose dependency health:

```json
{
  "status": "healthy",
  "dependencies": {
    "database": "connected",
    "cache": "connected",
    "externalApi": "reachable"
  }
}
```

QA should verify all dependencies show healthy status.

### Custom Health Check (No /health Endpoint)

If the app does not have a `/health` endpoint, use the root or any known endpoint:

```bash
# Try common health paths
curl -sf http://localhost:{port}/health ||
curl -sf http://localhost:{port}/api/health ||
curl -sf http://localhost:{port}/status ||
curl -sf http://localhost:{port}/
```

---

## UAT Result Recording

### Per-Scenario Format

```markdown
| Scenario | Method | Endpoint | Expected | Actual | Status |
|----------|--------|----------|----------|--------|--------|
| Health check | GET | /health | 200 | 200 | PASS |
| Create order | POST | /orders | 201 | 201 | PASS |
| Invalid input | POST | /orders | 400 | 500 | FAIL |
| Get order | GET | /orders/{id} | 200 | 200 | PASS |
```

### Evidence Capture

For each FAIL scenario, capture:
- Full curl command used
- HTTP status code received
- Response body (truncated to 500 chars if long)
- docker-compose logs relevant to the failure (if Docker UAT)

---

## Cleanup Procedures

### Docker Cleanup

```bash
# Standard cleanup
docker-compose down

# Deep cleanup (if container state is corrupt)
docker-compose down --volumes --remove-orphans
docker system prune -f  # Only if needed
```

### Local Process Cleanup

```bash
# Kill the application process
kill $APP_PID 2>/dev/null
wait $APP_PID 2>/dev/null

# Verify port is freed
lsof -i :{port} | grep LISTEN
```

### Post-UAT State

After UAT completes:
- Docker containers should be stopped and removed
- Local processes should be terminated
- Ports should be freed
- Temporary test data should be cleaned
- docker-compose logs should be saved as evidence (if failures occurred)

---

## UAT Skip Conditions

UAT is skipped (and documented as SKIPPED in report) when:

1. No `docker-compose.yml` AND no application entry point found
2. Project is a library (no runnable application)
3. No ACs of type "Functional - End-to-End" exist in the story
4. Infrastructure dependency not available (e.g., external DB required but not dockerized)

When skipping, always document the reason in the QA report.
