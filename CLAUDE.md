# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Atlas Town is an AI simulation system where LLM-powered agents role-play business stakeholders in a visual 2D town, generating realistic accounting data through the existing Atlas API. The simulation runs 5 businesses with different owners, customers, and vendors, all managed by a central accountant agent (Sarah).

## Commands

### Simulation (Python)

```bash
cd packages/simulation

# Install dependencies
uv sync

# Run simulation
python -m atlas_town.orchestrator

# Run all tests
pytest

# Run specific test file
pytest tests/test_scheduler.py

# Run with verbose output
pytest -v

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

### Frontend (Next.js) - Not yet implemented

```bash
cd packages/frontend
pnpm install
pnpm dev
```

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
