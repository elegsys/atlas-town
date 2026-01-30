#!/bin/bash
#
# Run Atlas API, Frontend, and Simulation together
# Usage: ./scripts/run-all.sh [OPTIONS]
#
# Options:
#   --reset     Reset database and reseed data before starting
#   --fast      Run simulation in fast mode (no LLM calls)
#   --days=N    Number of simulation days (default: 1)
#   --no-sim    Don't start the simulation (just API + frontend)
#
# Press Ctrl+C to stop all processes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Parse arguments
SIM_MODE=""
SIM_DAYS="1"
DO_RESET=false
NO_SIM=false

for arg in "$@"; do
  case $arg in
    --reset)
      DO_RESET=true
      ;;
    --fast)
      SIM_MODE="--mode=fast"
      ;;
    --days=*)
      SIM_DAYS="${arg#*=}"
      ;;
    --no-sim)
      NO_SIM=true
      ;;
    --help|-h)
      echo "Usage: ./scripts/run-all.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --reset     Reset database and reseed data before starting"
      echo "  --fast      Run simulation in fast mode (no LLM calls)"
      echo "  --days=N    Number of simulation days (default: 1)"
      echo "  --no-sim    Don't start the simulation (just API + frontend)"
      echo "  --help      Show this help message"
      exit 0
      ;;
  esac
done

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ATLAS_ROOT="$(dirname "$PROJECT_ROOT")/atlas"

# Verify Atlas repo exists
if [ ! -d "$ATLAS_ROOT/backend" ]; then
  echo -e "${RED}Error: Atlas backend not found at $ATLAS_ROOT/backend${NC}"
  echo "Expected directory structure:"
  echo "  ../atlas/backend  (Atlas API)"
  echo "  ./                (atlas-town)"
  exit 1
fi

# Check if Docker PostgreSQL is running
check_docker_services() {
  if ! docker ps 2>/dev/null | grep -q "atlas-postgres"; then
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}PostgreSQL Docker container not running!${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "Starting Docker services (postgres + redis)..."
    (cd "$ATLAS_ROOT" && docker-compose up -d postgres redis)
    echo -e "Waiting for PostgreSQL to be ready..."
    sleep 5
    # Wait for postgres to be healthy
    for i in {1..30}; do
      if docker exec atlas-postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo -e "${GREEN}PostgreSQL is ready!${NC}"
        break
      fi
      sleep 1
      if [ $i -eq 30 ]; then
        echo -e "${RED}PostgreSQL failed to start after 30s${NC}"
        exit 1
      fi
    done
    echo ""
  fi
}

# PIDs for cleanup
ATLAS_PID=""
FRONTEND_PID=""
SIM_PID=""

cleanup() {
  echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}Shutting down all processes...${NC}"

  [ -n "$SIM_PID" ] && kill $SIM_PID 2>/dev/null && echo -e "${BLUE}[SIM]${NC}  Stopped simulation"
  [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null && echo -e "${GREEN}[FE]${NC}   Stopped frontend"
  [ -n "$ATLAS_PID" ] && kill $ATLAS_PID 2>/dev/null && echo -e "${RED}[API]${NC}  Stopped Atlas API"

  # Kill any child processes
  jobs -p | xargs -r kill 2>/dev/null

  echo -e "${YELLOW}All processes stopped.${NC}"
  exit 0
}

trap cleanup SIGINT SIGTERM

# Header
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}${BOLD}  🏘️  Atlas Town Development Environment${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Ensure Docker services are running
check_docker_services

# Step 0: Reset database if requested
if [ "$DO_RESET" = true ]; then
  echo -e "${MAGENTA}${BOLD}[RESET] Resetting database and reseeding data...${NC}"
  echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

  # Run Atlas DB setup
  echo -e "${MAGENTA}[RESET]${NC} Running Atlas database setup..."
  (
    cd "$ATLAS_ROOT"
    ./scripts/setup-db.sh --skip-seed 2>&1 | sed "s/^/${MAGENTA}[RESET]${NC} /"
  )

  echo -e "${MAGENTA}[RESET]${NC} Database reset complete."
  echo ""
fi

# Generate encryption key using Atlas backend's venv (has cryptography installed)
export TAX_ID_ENCRYPTION_KEY="$("$ATLAS_ROOT/backend/venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Step 1: Start Atlas API
echo -e "${RED}${BOLD}[1/3] Starting Atlas API on port 8000...${NC}"
(
  cd "$ATLAS_ROOT/backend"
  source venv/bin/activate 2>/dev/null || true
  uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | while IFS= read -r line; do
    echo -e "${RED}[API]${NC}  $line"
  done
) &
ATLAS_PID=$!

# Wait for API to be ready
echo -e "${RED}[API]${NC}  Waiting for API to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo -e "${RED}[API]${NC}  ${GREEN}Ready!${NC}"
    break
  fi
  sleep 1
  if [ $i -eq 30 ]; then
    echo -e "${RED}[API]${NC}  Failed to start after 30s"
    cleanup
  fi
done

# Step 1b: Reseed simulation data if reset was requested
if [ "$DO_RESET" = true ]; then
  echo -e "${MAGENTA}[RESET]${NC} Seeding simulation data..."
  (
    cd "$PROJECT_ROOT/packages/simulation"
    ATLAS_API_URL=http://localhost:8000 uv run python scripts/seed_data.py 2>&1 | sed "s/^/${MAGENTA}[SEED]${NC} /"
  )
  echo -e "${MAGENTA}[RESET]${NC} ${GREEN}Simulation data seeded!${NC}"
  echo ""
fi

# Step 2: Start Frontend
echo -e "${GREEN}${BOLD}[2/3] Starting Frontend on port 3000...${NC}"
(
  cd "$PROJECT_ROOT/packages/frontend"
  pnpm dev 2>&1 | while IFS= read -r line; do
    echo -e "${GREEN}[FE]${NC}   $line"
  done
) &
FRONTEND_PID=$!

# Wait for frontend to compile
sleep 3

# Step 3: Start Simulation (unless --no-sim)
if [ "$NO_SIM" = false ]; then
  echo -e "${BLUE}${BOLD}[3/3] Starting Simulation (mode=${SIM_MODE:-llm}, days=$SIM_DAYS)...${NC}"
  sleep 2
  (
    cd "$PROJECT_ROOT/packages/simulation"
    ATLAS_API_URL=http://localhost:8000 uv run python -m atlas_town.orchestrator $SIM_MODE --days=$SIM_DAYS 2>&1 | while IFS= read -r line; do
      echo -e "${BLUE}[SIM]${NC}  $line"
    done
  ) &
  SIM_PID=$!
else
  echo -e "${YELLOW}[3/3] Skipping simulation (--no-sim)${NC}"
fi

# Summary
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}${BOLD}  All services running!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${RED}[API]${NC}  Atlas API:    ${BOLD}http://localhost:8000/docs${NC}"
echo -e "  ${GREEN}[FE]${NC}   Frontend:     ${BOLD}http://localhost:3000${NC}"
if [ "$NO_SIM" = false ]; then
  echo -e "  ${BLUE}[SIM]${NC}  Simulation:   Running ${SIM_MODE:-with LLMs} for $SIM_DAYS day(s)"
  echo -e "  ${BLUE}[SIM]${NC}  WebSocket:    ${BOLD}ws://localhost:8765${NC}"
fi
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all processes${NC}"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Wait for any process to exit
wait
