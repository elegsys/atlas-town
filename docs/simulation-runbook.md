# Simulation Runbook

Use this when you need a clean, repeatable simulation run with reliable logs.

## Quick Start (Recommended)

Run everything with one command from the project root:

```bash
# Fresh start: reset DB, reseed, and run all services
./scripts/run-all.sh --reset --fast --days=1

# Just run services (no DB reset)
./scripts/run-all.sh --fast --days=1

# Run without simulation (just API + frontend for testing)
./scripts/run-all.sh --no-sim
```

This starts:
- **Atlas API** on http://localhost:8000
- **Frontend** on http://localhost:3000
- **Simulation** with WebSocket on ws://localhost:8765

All logs are color-coded and prefixed: `[API]`, `[FE]`, `[SIM]`

Press `Ctrl+C` to stop all processes.

---

## Manual Setup (Alternative)

Use the sections below if you need more control over individual components.

## Prerequisites

- Atlas API running locally (default `http://localhost:8000`).
- If port 8000 is in use, run Atlas on `http://localhost:8001` and set `ATLAS_API_URL`.
- All commands run from `packages/simulation` unless noted.

## Start Atlas API (Backend)

If another app is already on port 8000, set `PORT=8001` before running.

```bash
cd ../atlas/backend
source venv/bin/activate
export PORT=8000
TAX_ID_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
```

Health check (new terminal):
```bash
curl -sS http://localhost:${PORT:-8000}/docs
```

## Reset DB + Reseed Data

```bash
# From repo root
../atlas/scripts/setup-db.sh

# From packages/simulation (set ATLAS_API_URL if not using 8000)
ATLAS_API_URL=http://localhost:8000 uv run python scripts/seed_data.py
```

Seeding updates:
- `packages/simulation/.env` with simulation credentials
- `packages/simulation/business_credentials.json` with org IDs

## Credentials + Config

- Default password: `AtlasTown2024!`
- Business credentials: `packages/simulation/business_credentials.json`
- Simulation config: `packages/simulation/.env`

## Run Simulation (Best Practice)

Always run with logs redirected to a file.

```bash
LOG=logs/sim_365d_$(date +%Y%m%d_%H%M%S).log
mkdir -p logs
ATLAS_API_URL=http://localhost:8000 \
  uv run python -m atlas_town.orchestrator --mode=fast --days=365 > "$LOG" 2>&1
echo "$LOG"
```

Notes:
- `--mode=fast` is 10-15x faster and no LLM cost.
- Default is `--days=1` if omitted.
- Logs live in `packages/simulation/logs/`.

## Quick Health Checks

- Confirm run completion:
  - Look for `simulation_ended` in the log.
- Scan for errors:
  - `rg -n "error|exception|traceback" logs/sim_*.log`

## Inventory Verification (Tony + Chen)

Confirm inventory receipts/issues hit Atlas API.

```bash
ATLAS_API_URL=http://localhost:8000 uv run python - <<'PY'
import asyncio
import json
from collections import Counter

from atlas_town.tools.atlas_api import AtlasAPIClient

async def inspect_business(key: str):
    with open("business_credentials.json") as f:
        creds = json.load(f)[key]

    api = AtlasAPIClient(username=creds["email"], password=creds["password"])
    await api.login()
    await api.switch_organization(creds["organization_id"])

    items = await api.list_inventory_items()
    summary = {}
    for item in items:
        item_id = item.get("id")
        sku = item.get("sku")
        if not item_id:
            continue
        resp = await api.get(f"/api/v1/inventory/items/{item_id}/transactions")
        txns = resp.get("items", []) if isinstance(resp, dict) else []
        types = Counter(
            (t.get("transaction_type") or t.get("movement_type") or "unknown")
            for t in txns
        )
        summary[sku] = dict(types)

    await api.close()
    return summary

async def main():
    for key in ("tony", "chen"):
        summary = await inspect_business(key)
        print(key)
        for sku, counts in summary.items():
            print(" ", sku, counts)

asyncio.run(main())
PY
```

## Sales Tax Verification (Tony)

Use Tony's org to confirm sales tax lines and remittance bills.

Compatibility note:
- Atlas API expects `tax_type=sales_tax` and uses `region`/`country` fields.
- Persona configs may still say `tax_type: "sales"` and `jurisdiction: "NY"`; the loader normalizes `sales` -> `sales_tax`, and `jurisdiction` is treated as `region` (with `country=US` when region is a 2-letter state).

```bash
uv run python - <<'PY'
import asyncio
import json

from atlas_town.tools.atlas_api import AtlasAPIClient

async def main():
    with open("business_credentials.json") as f:
        creds = json.load(f)["tony"]

    api = AtlasAPIClient(username=creds["email"], password=creds["password"])
    await api.login()
    await api.switch_organization(creds["organization_id"])

    invoices = await api.list_invoices()
    checked = 0
    tax_lines = 0
    for inv in invoices:
        inv_id = inv.get("id")
        if not inv_id:
            continue
        detail = await api.get_invoice(inv_id)
        checked += 1
        for line in detail.get("lines", []):
            desc = str(line.get("description", "")).lower()
            if "sales tax" in desc:
                tax_lines += 1
                break

    remits = []
    offset = 0
    limit = 100
    while True:
        bills = await api.list_bills(offset=offset, limit=limit)
        if not bills:
            break
        for b in bills:
            bill_id = b.get("id")
            if not bill_id:
                continue
            detail = await api.get_bill(bill_id)
            for line in detail.get("lines", []):
                if "sales tax remittance" in str(line.get("description", "")).lower():
                    remits.append(bill_id)
                    break
        if len(bills) < limit:
            break
        offset += limit

    print(f"invoices_checked={checked}")
    print(f"invoices_with_tax_lines={tax_lines}")
    print(f"sales_tax_remittance_bills={len(remits)}")

    await api.close()

asyncio.run(main())
PY
```

Example output:
```
invoices_checked=100
invoices_with_tax_lines=57
sales_tax_remittance_bills=12
```

If tax lines are missing or 422 errors appear in logs for tax rates, check the Atlas API tax rate query parameters and adjust `list_tax_rates` usage in `packages/simulation/src/atlas_town/tools/atlas_api.py`.

## Multi-Currency Verification (Maya)

Maya's Nexus Tech Consulting has international clients that are invoiced in foreign currencies (GBP, EUR, CAD). The simulation tracks FX rates, calculates gain/loss on payment, and revalues foreign AR at month-end.

### Configuration

Multi-currency is configured in `packages/simulation/src/atlas_town/config/personas/maya.yaml`:

```yaml
multi_currency:
  enabled: true
  base_currency: USD
  revaluation_enabled: true
  fx_gain_loss_account_name: "Foreign Exchange Gain/Loss"

  clients:
    - name: "TechCorp UK Ltd"
      currency: GBP
      base_rate: 1.27
      volatility: 0.005
      invoice_probability: 0.15
      # ...
```

### Verify International Invoices

```bash
uv run python - <<'PY'
import asyncio
import json

from atlas_town.tools.atlas_api import AtlasAPIClient

async def main():
    with open("business_credentials.json") as f:
        creds = json.load(f)["maya"]

    api = AtlasAPIClient(username=creds["email"], password=creds["password"])
    await api.login()
    await api.switch_organization(creds["organization_id"])

    invoices = await api.list_invoices()
    intl_count = 0
    currencies = set()

    for inv in invoices:
        notes = inv.get("notes", "") or ""
        if "Currency:" in notes:
            intl_count += 1
            # Parse currency from notes
            for part in notes.split(","):
                if "Currency:" in part:
                    currency = part.split(":")[1].strip()
                    currencies.add(currency)

    print(f"total_invoices={len(invoices)}")
    print(f"international_invoices={intl_count}")
    print(f"currencies={sorted(currencies)}")

    await api.close()

asyncio.run(main())
PY
```

Example output:
```
total_invoices=85
international_invoices=12
currencies=['CAD', 'EUR', 'GBP']
```

### Verify FX Journal Entries

Check for FX revaluation and gain/loss journal entries:

```bash
uv run python - <<'PY'
import asyncio
import json

from atlas_town.tools.atlas_api import AtlasAPIClient

async def main():
    with open("business_credentials.json") as f:
        creds = json.load(f)["maya"]

    api = AtlasAPIClient(username=creds["email"], password=creds["password"])
    await api.login()
    await api.switch_organization(creds["organization_id"])

    # List journal entries
    entries = await api.list_journal_entries()
    fx_entries = []

    for entry in entries:
        desc = entry.get("description", "").lower()
        if "fx" in desc or "foreign exchange" in desc or "revaluation" in desc:
            fx_entries.append({
                "id": entry.get("id"),
                "date": entry.get("entry_date"),
                "description": entry.get("description"),
            })

    print(f"total_journal_entries={len(entries)}")
    print(f"fx_related_entries={len(fx_entries)}")
    for entry in fx_entries[:5]:
        print(f"  - {entry['date']}: {entry['description']}")

    await api.close()

asyncio.run(main())
PY
```

### Exchange Rate Behavior

The exchange rate simulator uses deterministic seeded random to ensure reproducible results:
- Same `run_id` + date + currency always produces the same rate
- Daily drift: small random walk (±volatility, typically 0.3-0.5%)
- Periodic events: ~5% of days have larger moves (±2-3%)

Rates stay within reasonable bounds of the base rate (typically ±30% over a full year).
