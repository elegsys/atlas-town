# Atlas Town

AI simulation system where LLM-powered agents role-play business stakeholders in a visual 2D town, generating realistic accounting data through the Atlas API.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      ATLAS TOWN                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐         ┌──────────────────────────────┐ │
│  │  SIMULATION      │ ──ws──► │  FRONTEND (Next.js + PixiJS) │ │
│  │  (Python)        │         │  - Town visualization         │ │
│  │  - Orchestrator  │         │  - Agent sprites              │ │
│  │  - LLM Agents    │         │  - Financial dashboard        │ │
│  │  - Tool Executor │         │  - Real-time updates          │ │
│  └────────┬─────────┘         └──────────────────────────────┘ │
│           │                                                      │
│           │ HTTP/JWT                                             │
│           ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              ATLAS API (Existing)                         │   │
│  │  FastAPI + PostgreSQL + RLS                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Python 3.11+** with [uv](https://docs.astral.sh/uv/) package manager
- **Node.js 18+** with pnpm
- **Atlas API** running locally on port 8000 (see [Atlas repo](https://github.com/elegsys/atlas))
- **LLM API Keys**: At least one of Anthropic, OpenAI, or Google

## Quick Start

### 1. Start Atlas API (required)

```bash
# In the atlas repo directory
cd /path/to/atlas/backend
./scripts/setup-db.sh  # First time only
uvicorn app.main:app --reload
```

### 2. Configure Simulation

```bash
cd packages/simulation

# Copy environment template
cp .env.example .env

# Edit .env with your settings:
# - ATLAS_USERNAME/PASSWORD: Create a user in Atlas or use existing
# - LLM API keys: Add at least ANTHROPIC_API_KEY
```

**Required `.env` variables:**

```bash
# Atlas API
ATLAS_API_URL=http://localhost:8000
ATLAS_USERNAME=your-email@example.com
ATLAS_PASSWORD=your-password

# LLM API Keys (at least one required)
ANTHROPIC_API_KEY=sk-ant-...    # For Sarah (accountant)
OPENAI_API_KEY=sk-...           # For owners (Craig, Tony, Marcus)
GOOGLE_API_KEY=...              # For Dr. Chen
```

### 3. Install Dependencies

```bash
# Simulation (Python)
cd packages/simulation
uv sync

# Frontend (Next.js)
cd packages/frontend
pnpm install
```

### 4. Seed Database (first time)

The simulation needs customers, vendors, and a chart of accounts. Run the seed script:

```bash
cd packages/simulation
source .venv/bin/activate
python scripts/seed_data.py  # Or manually via Atlas UI
```

Or create via Atlas API:
- Setup chart of accounts: `POST /api/v1/accounts/setup-coa`
- Create customers/vendors via the Atlas UI

### 5. Run the Simulation

```bash
# Terminal 1: Start simulation (runs for 30 days by default)
cd packages/simulation
source .venv/bin/activate
python -m atlas_town.orchestrator --run 30

# Terminal 2: Start frontend
cd packages/frontend
pnpm dev
```

### 6. View the Visualization

Open http://localhost:3000 in your browser.

## Running Options

```bash
# Run single day (default)
python -m atlas_town.orchestrator

# Run continuous simulation for N days
python -m atlas_town.orchestrator --run 30

# Run a single task
python -m atlas_town.orchestrator "Create an invoice for Acme Corp for consulting services"
```

## Services & Ports

| Service | Port | Description |
|---------|------|-------------|
| Atlas API | 8000 | Backend accounting API |
| Simulation WebSocket | 8765 | Real-time events to frontend |
| Frontend | 3000 | Next.js visualization |

## The 5 Simulated Businesses

| Business | Industry | Owner (LLM) | Key Patterns |
|----------|----------|-------------|--------------|
| Craig's Landscaping | Service | Craig (GPT) | Seasonal, project-based |
| Tony's Pizzeria | F&B | Tony (GPT) | Daily sales, inventory |
| Nexus Tech | Consulting | Maya (Claude) | Hourly billing, retainers |
| Main Street Dental | Healthcare | Dr. Chen (Gemini) | Appointments, insurance |
| Harbor Realty | Real Estate | Marcus (GPT) | Commissions, trust accounts |

**Sarah Chen (Claude)** = Accountant managing books for all 5 organizations

## Tech Stack

| Layer | Technology |
|-------|------------|
| Simulation | Python 3.11+, asyncio, httpx |
| LLM Providers | Claude (Haiku 4.5), GPT (5-nano), Gemini (2.5 Flash) |
| Frontend | Next.js 14, TypeScript |
| Rendering | PixiJS v8 + @pixi/react |
| State | Zustand |
| Real-time | WebSocket |

## Project Structure

```
atlas-town/
├── packages/
│   ├── simulation/           # Python simulation engine
│   │   ├── .env.example      # Environment template
│   │   └── src/atlas_town/
│   │       ├── orchestrator.py   # Main coordinator
│   │       ├── scheduler.py      # Day/phase timing
│   │       ├── agents/           # BaseAgent, AccountantAgent, OwnerAgent
│   │       ├── clients/          # Claude, OpenAI, Gemini clients
│   │       ├── tools/            # Atlas API client & tool definitions
│   │       ├── events/           # WebSocket publisher
│   │       └── config/           # Settings, personas (YAML)
│   │
│   ├── frontend/             # Next.js + PixiJS visualization
│   │   └── src/
│   │       ├── app/              # Next.js App Router
│   │       ├── components/
│   │       │   ├── town/         # TownCanvas, Building, Character
│   │       │   └── dashboard/    # FinancialOverlay, TransactionFeed
│   │       └── lib/
│   │           ├── pixi/         # PixiJS engine setup
│   │           ├── state/        # Zustand stores
│   │           └── api/          # WebSocket client
│   │
│   └── shared/               # Shared TypeScript types
│
├── assets/sprites/           # Character and building sprites
├── CLAUDE.md                 # AI assistant context
└── README.md
```

## Development

```bash
# Run simulation tests
cd packages/simulation
pytest

# Lint Python code
ruff check src/ tests/

# Type check
mypy src/

# Frontend dev
cd packages/frontend
pnpm dev
pnpm lint
pnpm build
```

## LLM Cost Estimates (Jan 2026)

| Model | Input | Output | Used For |
|-------|-------|--------|----------|
| claude-haiku-4-5 | $1.00/M | $5.00/M | Sarah (accountant), Maya |
| gpt-5-nano | $0.05/M | $0.40/M | Craig, Tony, Marcus |
| gemini-2.5-flash | FREE* | FREE* | Dr. Chen |

*Gemini free tier: 15 RPM, 500 requests/day

## Troubleshooting

**422 Unprocessable Entity on API calls**
- Ensure chart of accounts is set up: `POST /api/v1/accounts/setup-coa`
- Check that company_id is being passed (automatic in latest version)

**Simulation stops after 1 day**
- Update to latest version with continuous mode fix

**WebSocket connection errors**
- Ensure simulation is running before opening frontend
- Check port 8765 is not in use

**LLM API errors**
- Verify API keys in `.env`
- Check model names match your API access level

## Related

- [Atlas](https://github.com/elegsys/atlas) - The accounting API backend
