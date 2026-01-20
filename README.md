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

## The 5 Simulated Businesses

| Business | Industry | Owner | Key Patterns |
|----------|----------|-------|--------------|
| Craig's Landscaping | Service | Craig (GPT) | Seasonal, project-based |
| Tony's Pizzeria | F&B | Tony (GPT) | Daily sales, inventory |
| Nexus Tech | Consulting | Maya (Claude) | Hourly billing, retainers |
| Main Street Dental | Healthcare | Dr. Chen (Gemini) | Appointments, insurance |
| Harbor Realty | Real Estate | Marcus (GPT) | Commissions, trust accounts |

**Sarah (Claude)** = Accountant managing books for all 5 organizations

## Tech Stack

| Layer | Technology |
|-------|------------|
| Simulation | Python 3.11+, asyncio, httpx |
| LLM Providers | Claude, GPT, Gemini |
| Frontend | Next.js 14, TypeScript |
| Rendering | PixiJS v8 + @pixi/react |
| State | Zustand |
| Real-time | WebSocket |

## Project Structure

```
atlas-town/
├── packages/
│   ├── simulation/           # Python simulation engine
│   │   └── src/atlas_town/
│   │       ├── orchestrator.py
│   │       ├── scheduler.py
│   │       ├── agents/       # owner, accountant, customer, vendor
│   │       ├── clients/      # claude, openai, gemini LLM clients
│   │       ├── tools/        # Atlas API tool definitions
│   │       ├── events/       # WebSocket publisher
│   │       └── config/       # YAML configs, personas
│   │
│   ├── frontend/             # Next.js + PixiJS visualization
│   │   └── src/
│   │       ├── app/          # Next.js App Router
│   │       ├── components/
│   │       │   ├── town/     # TownCanvas, Building, Character
│   │       │   └── dashboard/# FinancialOverlay, TransactionFeed
│   │       └── lib/
│   │           ├── pixi/     # PixiJS engine setup
│   │           ├── state/    # Zustand stores
│   │           └── api/      # WebSocket client
│   │
│   └── shared/               # Shared TypeScript types
│
├── assets/sprites/           # Character and building sprites
└── scripts/                  # Dev and seed scripts
```

## Getting Started

```bash
# Simulation (Python)
cd packages/simulation
uv sync
python -m atlas_town.orchestrator

# Frontend (Next.js)
cd packages/frontend
pnpm install
pnpm dev
```

## Related

- [Atlas](https://github.com/elegsys/atlas) - The accounting API backend
