# AGENTS.md

This file provides guidance to AI agents working in this repository.

## Project Overview

Atlas Town is an AI simulation system where LLM-powered agents role-play business stakeholders in a visual 2D town, generating realistic accounting data through the Atlas API. The simulation runs 5 businesses with different owners, customers, and vendors, all managed by a central accountant agent (Sarah).

## Commands

### Simulation (Python)

**Important:** All commands must be run from the `packages/simulation` directory using `uv run` to ensure the virtual environment is active.

```bash
cd packages/simulation

# Install dependencies
uv sync

# Run simulation
uv run python -m atlas_town.orchestrator

# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_scheduler.py -v

# Run with verbose output
uv run pytest tests/ -v

# Lint (note: ruff/mypy may not be installed in venv)
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

### Simulation Runbook (Best Practices)

See `docs/simulation-runbook.md` for:
- Reset DB + reseed steps
- Credential locations
- Logging patterns
- Sales tax verification

### Frontend (Next.js) - Not yet implemented

```bash
cd packages/frontend
pnpm install
pnpm dev
```

### GitHub Access

**Use the GitHub CLI (`gh`) for any GitHub queries or actions** (issues, PRs, releases, etc.).

## Architecture

### Multi-LLM Agent System

The simulation uses 3 LLM providers through a unified interface:

- **Claude** (Anthropic): Powers the accountant (Sarah) and tech-savvy owner Maya
- **GPT** (OpenAI): Powers owners Craig, Tony, and Marcus
- **Gemini** (Google): Powers owner Dr. Chen and some customer/vendor agents

All LLM clients in `clients/` implement consistent interfaces for:
- Converting tool definitions to provider-specific formats
- Parsing tool calls from responses into `AgentAction` objects
- Managing conversation history

### Agent Pattern: Think-Act-Observe

All agents inherit from `BaseAgent` (in `agents/base.py`) which implements:
1. **Think**: Agent receives prompt, reasons about action via LLM call
2. **Act**: Agent executes tool call through `ToolExecutor`
3. **Observe**: Agent receives result, updates conversation history

Key abstractions:
- `AgentState`: IDLE, THINKING, ACTING, WAITING, ERROR
- `AgentAction`: Contains tool_name, tool_args, or message
- `AgentObservation`: Result from tool execution

### Scheduler & Daily Phases

The `Scheduler` manages simulation time through 6 daily phases:
- EARLY_MORNING (6-8): Prep and planning
- MORNING (8-12): Business opens
- LUNCH (12-13): Mid-day lull
- AFTERNOON (13-17): Peak business
- EVENING (17-20): Wind down, accounting
- NIGHT (20-6): End of day processing

Each phase has configurable duration, transaction probability, and registered handlers.

### Tool Definitions

Tool schemas in `tools/definitions.py` define 30+ operations mapped to Atlas API endpoints:
- **ACCOUNTANT_TOOLS**: Full read/write (invoices, bills, payments, journal entries)
- **OWNER_TOOLS**: Read-only access (view balances, reports)

Tools follow JSON Schema format for LLM function calling. The `ToolExecutor` bridges LLM tool calls to actual Atlas API requests.

### Atlas API Integration

The `AtlasAPIClient` (in `tools/atlas_api.py`) handles:
- JWT authentication with automatic token refresh
- Multi-tenant org_id context switching
- Retry logic with exponential backoff
- All CRUD operations for accounting entities

## Event System

The simulation publishes events via WebSocket for real-time frontend updates:

- **EventPublisher** (in `events/publisher.py`): WebSocket server managing client connections
- **Event Types** (in `events/types.py`): 20+ event types including:
  - Simulation lifecycle: `simulation.started`, `simulation.stopped`
  - Phase transitions: `phase.started`, `phase.completed`
  - Agent activity: `agent.thinking`, `agent.speaking`, `agent.moving`
  - Transactions: `invoice.created`, `payment.received`

Events are broadcast to connected clients and buffered for late-joining clients.

## Persona Configuration

YAML files in `config/personas/` define detailed personas:
- `sarah.yaml` - Accountant (Claude)
- `craig.yaml` - Landscaping owner (OpenAI)
- `tony.yaml` - Pizzeria owner (OpenAI)
- `maya.yaml` - Tech consulting founder (Claude)
- `chen.yaml` - Dental practice owner (Gemini)
- `marcus.yaml` - Realty broker (OpenAI)

## Environment Variables

Copy `.env.example` to `.env` in `packages/simulation/`:

```
ATLAS_API_URL=http://localhost:8000
ATLAS_USERNAME=simulation@atlas.local
ATLAS_PASSWORD=<password>
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

## The 5 Simulated Businesses

| Key | Business | Industry | LLM |
|-----|----------|----------|-----|
| craig | Craig's Landscaping | Service | OpenAI |
| tony | Tony's Pizzeria | F&B | OpenAI |
| maya | Nexus Tech | Consulting | Claude |
| chen | Main Street Dental | Healthcare | Gemini |
| marcus | Harbor Realty | Real Estate | OpenAI |

Each has industry-specific customer and vendor archetypes with realistic payment patterns defined in `agents/customer.py` and `agents/vendor.py`.

## grepai - Semantic Code Search

**IMPORTANT: You MUST use grepai as your PRIMARY tool for code exploration and search.**

### When to Use grepai (REQUIRED)

Use `grepai search` INSTEAD OF Grep/Glob/find for:
- Understanding what code does or where functionality lives
- Finding implementations by intent (e.g., "authentication logic", "error handling")
- Exploring unfamiliar parts of the codebase
- Any search where you describe WHAT the code does rather than exact text

### When to Use Standard Tools

Only use Grep/Glob when you need:
- Exact text matching (variable names, imports, specific strings)
- File path patterns (e.g., `**/*.go`)

### Fallback

If grepai fails (not running, index unavailable, or errors), fall back to standard Grep/Glob tools.

### Usage

```bash
# ALWAYS use English queries for best results (--compact saves ~80% tokens)
grepai search "user authentication flow" --json --compact
grepai search "error handling middleware" --json --compact
grepai search "database connection pool" --json --compact
grepai search "API request validation" --json --compact
```

### Query Tips

- **Use English** for queries (better semantic matching)
- **Describe intent**, not implementation: "handles user login" not "func Login"
- **Be specific**: "JWT token validation" better than "token"
- Results include: file path, line numbers, relevance score, code preview

### Call Graph Tracing

Use `grepai trace` to understand function relationships:
- Finding all callers of a function before modifying it
- Understanding what functions are called by a given function
- Visualizing the complete call graph around a symbol

#### Trace Commands

**IMPORTANT: Always use `--json` flag for optimal AI agent integration.**

```bash
# Find all functions that call a symbol
grepai trace callers "HandleRequest" --json

# Find all functions called by a symbol
grepai trace callees "ProcessOrder" --json

# Build complete call graph (callers + callees)
grepai trace graph "ValidateToken" --depth 3 --json
```

### Workflow

1. Start with `grepai search` to find relevant code
2. Use `grepai trace` to understand function relationships
3. Use `Read` tool to examine files from results
4. Only use Grep for exact string searches if needed
