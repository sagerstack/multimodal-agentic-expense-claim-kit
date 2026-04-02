#!/bin/bash
# Local Development Startup Script
# Builds and starts all Docker services, runs migrations, verifies health
#
# Usage:
#   ./scripts/local/startup.sh          # Normal startup (preserves volumes)
#   ./scripts/local/startup.sh --reset  # Clean restart (wipes volumes and re-ingests)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TIMEOUT=120
CHECK_INTERVAL=5
RESET_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --reset)
            RESET_MODE=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--reset]"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Agentic Claims — Local Startup${NC}"
echo -e "${GREEN}========================================${NC}"

# Load .env.local for Docker Compose variable interpolation
if [ -f .env.local ]; then
    set -a
    source .env.local
    set +a
    echo -e "${GREEN}Loaded .env.local${NC}"
else
    echo -e "${RED}.env.local not found — Docker Compose variable interpolation may fail${NC}"
    exit 1
fi

# Step 1: Stop existing containers
echo -e "\n${YELLOW}[1/6] Stopping existing containers...${NC}"
if [ "$RESET_MODE" = true ]; then
    docker compose down -v
    echo -e "${GREEN}Containers stopped, volumes wiped${NC}"
else
    docker compose down
    echo -e "${GREEN}Containers stopped, volumes preserved${NC}"
fi

# Step 2: Build and start services
echo -e "\n${YELLOW}[2/6] Building and starting services...${NC}"
docker compose up -d --build
echo -e "${GREEN}Services starting${NC}"

# Step 3: Health checks
echo -e "\n${YELLOW}[3/6] Waiting for services to be healthy (timeout: ${TIMEOUT}s)...${NC}"

waitForHealthy() {
    local service=$1
    local elapsed=0

    while [ $elapsed -lt $TIMEOUT ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' $(docker compose ps -q $service) 2>/dev/null || echo "starting")

        if [ "$status" = "healthy" ]; then
            echo -e "  ${GREEN}$service: healthy${NC}"
            return 0
        fi

        echo -ne "\r  $service: $status (${elapsed}s)...          "
        sleep $CHECK_INTERVAL
        elapsed=$((elapsed + CHECK_INTERVAL))
    done

    echo -e "\n  ${RED}$service: timeout after ${TIMEOUT}s${NC}"
    echo -e "  ${YELLOW}Check logs: docker compose logs $service${NC}"
    return 1
}

SERVICES=(postgres qdrant mcp-rag mcp-db mcp-currency mcp-email app)
FAILED=false

for service in "${SERVICES[@]}"; do
    if ! waitForHealthy "$service"; then
        FAILED=true
        break
    fi
done

if [ "$FAILED" = true ]; then
    echo -e "\n${RED}Health check failed. Aborting.${NC}"
    exit 1
fi

# Step 4: Run database migrations
echo -e "\n${YELLOW}[4/6] Running database migrations...${NC}"

MIGRATION_OK=false
for attempt in 1 2 3; do
    if docker compose exec -T app alembic upgrade head 2>/dev/null; then
        MIGRATION_OK=true
        break
    fi
    if [ $attempt -lt 3 ]; then
        echo -e "  ${YELLOW}Attempt $attempt failed, retrying in 2s...${NC}"
        sleep 2
    fi
done

if [ "$MIGRATION_OK" = true ]; then
    echo -e "${GREEN}Migrations complete${NC}"
else
    echo -e "${RED}Migrations failed after 3 attempts${NC}"
    echo -e "${YELLOW}Check logs: docker compose logs app${NC}"
    exit 1
fi

# Step 5: Ingest policies (idempotent — safe to run every time)
echo -e "\n${YELLOW}[5/6] Ingesting policies...${NC}"
docker compose exec -T -e POLICY_DIR=/app/policy mcp-rag python /app/scripts/ingest_policies.py
echo -e "${GREEN}Policies ingested${NC}"

# Step 6: Final verification
echo -e "\n${YELLOW}[6/6] Verifying all components...${NC}"

VERIFY_FAILED=false

# Verify app responds on all 4 page routes
for path in "/" "/dashboard" "/audit" "/review/test-claim"; do
    httpCode=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000${path}" 2>/dev/null || echo "000")
    if [ "$httpCode" = "200" ]; then
        echo -e "  ${GREEN}GET ${path} -> ${httpCode}${NC}"
    else
        echo -e "  ${RED}GET ${path} -> ${httpCode}${NC}"
        VERIFY_FAILED=true
    fi
done

# Verify MCP servers respond (406 = healthy for Streamable HTTP)
for port in 8001 8002 8003 8004; do
    httpCode=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/mcp" 2>/dev/null || echo "000")
    if [[ "$httpCode" =~ ^[0-9]+$ ]] && [ "$httpCode" != "000" ]; then
        echo -e "  ${GREEN}MCP :${port} -> ${httpCode}${NC}"
    else
        echo -e "  ${RED}MCP :${port} -> ${httpCode}${NC}"
        VERIFY_FAILED=true
    fi
done

if [ "$VERIFY_FAILED" = true ]; then
    echo -e "\n${RED}Some verifications failed — check logs above${NC}"
    exit 1
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}System ready${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Service URLs:"
echo -e "  FastAPI App:  ${GREEN}http://localhost:8000${NC}"
echo -e "  Postgres:     ${GREEN}localhost:5432${NC}"
echo -e "  Qdrant:       ${GREEN}http://localhost:6333${NC}"
echo ""
