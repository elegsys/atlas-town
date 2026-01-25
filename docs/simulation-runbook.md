# Simulation Runbook

Use this when you need a clean, repeatable simulation run with reliable logs.

## Prerequisites

- Atlas API running locally (default `http://localhost:8000`).
- All commands run from `packages/simulation` unless noted.

## Reset DB + Reseed Data

```bash
# From repo root
../atlas/scripts/setup-db.sh

# From packages/simulation
uv run python scripts/seed_data.py
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
