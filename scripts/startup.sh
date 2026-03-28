#!/bin/bash
# Agentic Claims Startup Script
# Brings the entire system from zero to ready state in a single command
#
# Usage:
#   ./scripts/startup.sh          # Normal startup (preserves volumes)
#   ./scripts/startup.sh --reset  # Clean restart (wipes volumes and re-ingests)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No color

# Configuration
TIMEOUT=120
CHECK_INTERVAL=5
RESET_MODE=false

# Parse arguments
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

# Header
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Agentic Claims Startup Script${NC}"
echo -e "${GREEN}========================================${NC}"

# Load environment variables for Docker Compose ${VAR} interpolation
# Docker Compose reads .env automatically, but .env.local is the canonical config
# (contains SEQ_PASSWORD, LOG_LEVEL, and other vars not in .env)
if [ -f .env.local ]; then
    set -a
    source .env.local
    set +a
    echo -e "${GREEN}✓ Loaded .env.local${NC}"
else
    echo -e "${RED}✗ .env.local not found — Docker Compose variable interpolation may fail${NC}"
    exit 1
fi

# Step 1: Stop existing containers
echo -e "\n${YELLOW}[1/7] Stopping existing containers...${NC}"
docker compose down
echo -e "${GREEN}✓ Containers stopped${NC}"

# Step 2: Handle reset mode
if [ "$RESET_MODE" = true ]; then
    echo -e "\n${YELLOW}[2/7] Resetting volumes...${NC}"
    docker compose down -v
    echo -e "${GREEN}✓ Volumes wiped (clean restart)${NC}"
else
    echo -e "\n${YELLOW}[2/7] Keeping existing volumes${NC}"
    echo -e "${GREEN}✓ Volumes preserved${NC}"
fi

# Step 3: Start Docker Compose
echo -e "\n${YELLOW}[3/7] Starting Docker Compose services...${NC}"
docker compose up -d --build
echo -e "${GREEN}✓ Services starting${NC}"

# Step 4: Wait for health checks
echo -e "\n${YELLOW}[4/7] Waiting for services to be healthy (timeout: ${TIMEOUT}s)...${NC}"

waitForHealthy() {
    local service=$1
    local timeout=${2:-$TIMEOUT}
    local interval=${3:-$CHECK_INTERVAL}
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        # Get health status from Docker inspect
        status=$(docker inspect --format='{{.State.Health.Status}}' $(docker compose ps -q $service) 2>/dev/null || echo "starting")

        case $status in
            healthy)
                echo -e "${GREEN}  ✓ $service is healthy${NC}"
                return 0
                ;;
            unhealthy)
                echo -ne "\r  ⏳ $service: unhealthy, retrying (${elapsed}s elapsed)...          "
                ;;
            starting)
                echo -ne "\r  ⏳ $service: starting (${elapsed}s elapsed)...          "
                ;;
            *)
                echo -ne "\r  ⏳ $service: $status (${elapsed}s elapsed)...          "
                ;;
        esac

        sleep $interval
        elapsed=$((elapsed + interval))
    done

    echo -e "\n${RED}  ✗ $service health check timeout (${timeout}s)${NC}"
    echo -e "${YELLOW}Check logs with: docker compose logs $service${NC}"
    return 1
}

# Wait for each service in dependency order
for service in postgres qdrant mcp-rag mcp-db mcp-currency mcp-email seq app; do
    if ! waitForHealthy $service; then
        echo -e "\n${RED}Startup failed at $service health check${NC}"
        echo -e "${YELLOW}Troubleshooting:${NC}"
        echo -e "  1. Check logs: docker compose logs $service"
        echo -e "  2. Check status: docker compose ps"
        echo -e "  3. Try clean restart: $0 --reset"
        exit 1
    fi
done

# Step 5: Run Alembic migrations with retry logic
echo -e "\n${YELLOW}[5/7] Running database migrations...${NC}"

MIGRATION_SUCCESS=false
for attempt in {1..3}; do
    if docker compose exec -T app alembic upgrade head 2>/dev/null; then
        MIGRATION_SUCCESS=true
        break
    else
        if [ $attempt -lt 3 ]; then
            echo -e "${YELLOW}  ⏳ Migration attempt $attempt failed, retrying in 2s...${NC}"
            sleep 2
        fi
    fi
done

if [ "$MIGRATION_SUCCESS" = true ]; then
    echo -e "${GREEN}✓ Migrations complete${NC}"
else
    echo -e "\n${RED}✗ Migrations failed after 3 attempts${NC}"
    echo -e "${YELLOW}Check logs with: docker compose logs app${NC}"
    exit 1
fi

# Step 6: Truncate tables in reset mode (clean dev state)
if [ "$RESET_MODE" = true ]; then
    echo -e "\n${YELLOW}[6/7] Truncating claims, receipts, audit_log tables for clean dev state...${NC}"
    docker compose exec -T postgres psql -U agentic -d agentic_claims -c "
        TRUNCATE claims, receipts, audit_log CASCADE;
        -- Reset claim number sequence if it exists (created by migration 004)
        DO \$\$ BEGIN
            PERFORM setval('claim_number_seq', 1, false);
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END \$\$;
    " 2>/dev/null
    echo -e "${GREEN}✓ Tables truncated${NC}"
else
    echo -e "\n${YELLOW}[6/7] Keeping existing claim data${NC}"
    echo -e "${GREEN}✓ Data preserved${NC}"
fi

# Step 7: Ingest policies (always run - script is idempotent)
# Run via mcp-rag container (has sentence-transformers + qdrant-client deps)
echo -e "\n${YELLOW}[7/7] Ingesting policies...${NC}"
docker compose exec -T -e POLICY_DIR=/app/policy mcp-rag python /app/scripts/ingest_policies.py
echo -e "${GREEN}✓ Policies ingested${NC}"

# Success banner
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}✓ System ready${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Service URLs:"
echo -e "  Chainlit UI:      ${GREEN}http://localhost:8000${NC}"
echo -e "  Seq Logs:         ${GREEN}http://localhost:5341${NC}"
echo -e "  Postgres:         ${GREEN}localhost:5432${NC}"
echo -e "  Qdrant:           ${GREEN}http://localhost:6333${NC}"
echo ""
echo -e "Following app logs (Ctrl+C to stop)..."
echo -e "${YELLOW}========================================${NC}"
echo ""

# Follow logs
docker compose logs -f app
