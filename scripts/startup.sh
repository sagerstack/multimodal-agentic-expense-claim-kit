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

# Step 1: Stop existing containers
echo -e "\n${YELLOW}[1/6] Stopping existing containers...${NC}"
docker compose down
echo -e "${GREEN}✓ Containers stopped${NC}"

# Step 2: Handle reset mode
if [ "$RESET_MODE" = true ]; then
    echo -e "\n${YELLOW}[2/6] Resetting volumes...${NC}"
    docker compose down -v
    echo -e "${GREEN}✓ Volumes wiped (clean restart)${NC}"
else
    echo -e "\n${YELLOW}[2/6] Keeping existing volumes${NC}"
    echo -e "${GREEN}✓ Volumes preserved${NC}"
fi

# Step 3: Start Docker Compose
echo -e "\n${YELLOW}[3/6] Starting Docker Compose services...${NC}"
docker compose up -d --build
echo -e "${GREEN}✓ Services starting${NC}"

# Step 4: Wait for health checks
echo -e "\n${YELLOW}[4/6] Waiting for services to be healthy (timeout: ${TIMEOUT}s)...${NC}"

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
                echo -e "\n${RED}  ✗ $service is unhealthy${NC}"
                echo -e "${YELLOW}Last 20 log lines:${NC}"
                docker compose logs --tail=20 $service
                return 1
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
echo -e "\n${YELLOW}[5/6] Running database migrations...${NC}"

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

# Step 6: Ingest policies (always run - script is idempotent)
echo -e "\n${YELLOW}[6/6] Ingesting policies...${NC}"
docker compose exec -T app python scripts/ingest_policies.py
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
