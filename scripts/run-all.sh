#!/bin/bash
#
# Run Atlas API, Frontend, and Simulation together
# Usage: ./scripts/run-all.sh [--fast] [--days=N]
#
# Options:
#   --fast      Run simulation in fast mode (no LLM calls)
#   --days=N    Number of simulation days (default: 1)
#
# Press Ctrl+C to stop all processes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Parse arguments
SIM_MODE=""
SIM_DAYS="1"
for arg in "$@"; do
  case $arg in
    --fast)
      SIM_MODE="--mode=fast"
      ;;
    --days=*)
      SIM_DAYS="${arg#*=}"
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

# PIDs for cleanup
ATLAS_PID=""
FRONTEND_PID=""
SIM_PID=""

cleanup() {
  echo -e "\n${YELLOW}Shutting down all processes...${NC}"

  [ -n "$SIM_PID" ] && kill $SIM_PID 2>/dev/null && echo -e "${BLUE}Stopped simulation${NC}"
  [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null && echo -e "${GREEN}Stopped frontend${NC}"
  [ -n "$ATLAS_PID" ] && kill $ATLAS_PID 2>/dev/null && echo -e "${RED}Stopped Atlas API${NC}"

  # Kill any child processes
  jobs -p | xargs -r kill 2>/dev/null

  echo -e "${YELLOW}All processes stopped.${NC}"
  exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  Starting Atlas Town Development      ${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# Generate encryption key once
export TAX_ID_ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Start Atlas API
echo -e "${RED}[1/3] Starting Atlas API on port 8000...${NC}"
(
  cd "$ATLAS_ROOT/backend"
  source venv/bin/activate 2>/dev/null || true
  uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | sed "s/^/[API] /"
) &
ATLAS_PID=$!

# Wait for API to be ready
echo -e "${RED}[API] Waiting for API to be ready...${NC}"
for i in {1..30}; do
  if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo -e "${RED}[API] Ready!${NC}"
    break
  fi
  sleep 1
  if [ $i -eq 30 ]; then
    echo -e "${RED}[API] Failed to start after 30s${NC}"
    cleanup
  fi
done

# Start Frontend
echo -e "${GREEN}[2/3] Starting Frontend on port 3000...${NC}"
(
  cd "$PROJECT_ROOT/packages/frontend"
  pnpm dev 2>&1 | sed "s/^/[FE]  /"
) &
FRONTEND_PID=$!

# Wait for frontend to compile
sleep 3

# Start Simulation (delayed to ensure API is ready)
echo -e "${BLUE}[3/3] Starting Simulation (mode=${SIM_MODE:-normal}, days=$SIM_DAYS)...${NC}"
sleep 2
(
  cd "$PROJECT_ROOT/packages/simulation"
  ATLAS_API_URL=http://localhost:8000 uv run python -m atlas_town.orchestrator $SIM_MODE --days=$SIM_DAYS 2>&1 | sed "s/^/[SIM] /"
) &
SIM_PID=$!

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  All services running!                ${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo -e "  ${RED}Atlas API:${NC}    http://localhost:8000/docs"
echo -e "  ${GREEN}Frontend:${NC}     http://localhost:3000"
echo -e "  ${BLUE}Simulation:${NC}   Running ${SIM_MODE:-with LLMs} for $SIM_DAYS day(s)"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all processes${NC}"
echo ""

# Wait for any process to exit
wait
