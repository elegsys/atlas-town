#!/usr/bin/env python3
"""Export Atlas Town simulation data via API to JSON.

Exports all entities (invoices, bills, payments, journal entries, customers,
vendors) for all 5 businesses via paginated API calls to JSON files.

Usage:
    cd packages/simulation
    uv run python scripts/export_data.py

    # Export to specific directory
    uv run python scripts/export_data.py --output-dir /path/to/exports

    # Export specific business only
    uv run python scripts/export_data.py --business craig
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from atlas_town.tools.atlas_api import AtlasAPIClient, AtlasAPIError


# Custom JSON encoder for UUID and Decimal
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return str(obj)
        if hasattr(obj, "isoformat"):  # datetime/date
            return obj.isoformat()
        return super().default(obj)


async def paginated_fetch(
    fetch_fn,
    limit: int = 100,
    max_items: int | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """Fetch all items using pagination."""
    all_items = []
    offset = 0

    while True:
        items = await fetch_fn(offset=offset, limit=limit, **kwargs)
        if not items:
            break

        all_items.extend(items)
        offset += len(items)

        if max_items and len(all_items) >= max_items:
            break

        if len(items) < limit:
            break  # Last page

    return all_items


async def export_business_data(
    client: AtlasAPIClient,
    org_id: UUID,
    org_name: str,
    output_dir: Path,
) -> dict[str, int]:
    """Export all data for a single business."""
    stats = {}

    print(f"\n  Exporting {org_name}...")

    # Switch to organization
    await client.switch_organization(org_id)

    # Create business output directory
    business_dir = output_dir / org_name.lower().replace(" ", "_").replace("'", "")
    business_dir.mkdir(parents=True, exist_ok=True)

    # Export customers
    print("    - Customers...", end=" ", flush=True)
    customers = await paginated_fetch(client.list_customers)
    (business_dir / "customers.json").write_text(
        json.dumps(customers, cls=CustomJSONEncoder, indent=2)
    )
    print(f"{len(customers)}")
    stats["customers"] = len(customers)

    # Export vendors
    print("    - Vendors...", end=" ", flush=True)
    vendors = await paginated_fetch(client.list_vendors)
    (business_dir / "vendors.json").write_text(json.dumps(vendors, cls=CustomJSONEncoder, indent=2))
    print(f"{len(vendors)}")
    stats["vendors"] = len(vendors)

    # Export accounts (chart of accounts)
    print("    - Accounts...", end=" ", flush=True)
    accounts = await paginated_fetch(client.list_accounts, limit=200)
    (business_dir / "accounts.json").write_text(
        json.dumps(accounts, cls=CustomJSONEncoder, indent=2)
    )
    print(f"{len(accounts)}")
    stats["accounts"] = len(accounts)

    # Export invoices
    print("    - Invoices...", end=" ", flush=True)
    invoices = await paginated_fetch(client.list_invoices)
    (business_dir / "invoices.json").write_text(
        json.dumps(invoices, cls=CustomJSONEncoder, indent=2)
    )
    print(f"{len(invoices)}")
    stats["invoices"] = len(invoices)

    # Export bills
    print("    - Bills...", end=" ", flush=True)
    bills = await paginated_fetch(client.list_bills)
    (business_dir / "bills.json").write_text(json.dumps(bills, cls=CustomJSONEncoder, indent=2))
    print(f"{len(bills)}")
    stats["bills"] = len(bills)

    # Export payments (received)
    print("    - Payments received...", end=" ", flush=True)
    payments = await paginated_fetch(client.list_payments)
    (business_dir / "payments_received.json").write_text(
        json.dumps(payments, cls=CustomJSONEncoder, indent=2)
    )
    print(f"{len(payments)}")
    stats["payments_received"] = len(payments)

    # Export bill payments (made)
    print("    - Payments made...", end=" ", flush=True)
    try:
        bill_payments = await paginated_fetch(client.list_bill_payments)
        (business_dir / "payments_made.json").write_text(
            json.dumps(bill_payments, cls=CustomJSONEncoder, indent=2)
        )
        print(f"{len(bill_payments)}")
        stats["payments_made"] = len(bill_payments)
    except AtlasAPIError:
        print("skipped (endpoint unavailable)")
        stats["payments_made"] = 0

    # Export journal entries
    print("    - Journal entries...", end=" ", flush=True)
    try:
        journal_entries = await paginated_fetch(client.list_journal_entries)
        (business_dir / "journal_entries.json").write_text(
            json.dumps(journal_entries, cls=CustomJSONEncoder, indent=2)
        )
        print(f"{len(journal_entries)}")
        stats["journal_entries"] = len(journal_entries)
    except AtlasAPIError as e:
        print(f"skipped ({e})")
        stats["journal_entries"] = 0

    # Export bank accounts
    print("    - Bank accounts...", end=" ", flush=True)
    try:
        bank_accounts = await paginated_fetch(lambda **kw: client.list_bank_accounts(), limit=50)
        (business_dir / "bank_accounts.json").write_text(
            json.dumps(bank_accounts, cls=CustomJSONEncoder, indent=2)
        )
        print(f"{len(bank_accounts)}")
        stats["bank_accounts"] = len(bank_accounts)
    except AtlasAPIError as e:
        print(f"skipped ({e})")
        stats["bank_accounts"] = 0

    # Export tax rates
    print("    - Tax rates...", end=" ", flush=True)
    try:
        tax_rates = await paginated_fetch(client.list_tax_rates)
        (business_dir / "tax_rates.json").write_text(
            json.dumps(tax_rates, cls=CustomJSONEncoder, indent=2)
        )
        print(f"{len(tax_rates)}")
        stats["tax_rates"] = len(tax_rates)
    except AtlasAPIError as e:
        print(f"skipped ({e})")
        stats["tax_rates"] = 0

    # Export inventory items
    print("    - Inventory items...", end=" ", flush=True)
    try:
        inventory = await paginated_fetch(client.list_inventory_items)
        (business_dir / "inventory_items.json").write_text(
            json.dumps(inventory, cls=CustomJSONEncoder, indent=2)
        )
        print(f"{len(inventory)}")
        stats["inventory_items"] = len(inventory)
    except AtlasAPIError as e:
        print(f"skipped ({e})")
        stats["inventory_items"] = 0

    return stats


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Export Atlas Town simulation data")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: exports/YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--business",
        type=str,
        default=None,
        choices=["craig", "tony", "maya", "chen", "marcus"],
        help="Export specific business only",
    )
    args = parser.parse_args()

    # Load environment
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

    api_url = os.environ.get("ATLAS_API_URL", "http://localhost:8000")

    # Load business credentials
    creds_file = Path(__file__).parent.parent / "business_credentials.json"
    if not creds_file.exists():
        print("Error: business_credentials.json not found")
        print("Run seed_data.py first to create business accounts")
        sys.exit(1)

    credentials = json.loads(creds_file.read_text())

    # Filter to specific business if requested
    if args.business:
        if args.business not in credentials:
            print(f"Error: Business '{args.business}' not found")
            sys.exit(1)
        credentials = {args.business: credentials[args.business]}

    # Setup output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).parent.parent.parent.parent / "exports" / timestamp

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Atlas Town - Data Export")
    print("=" * 60)
    print(f"\nAPI URL: {api_url}")
    print(f"Output: {output_dir}")
    print(f"Businesses: {list(credentials.keys())}")

    all_stats = {}

    for biz_key, creds in credentials.items():
        # Login to get fresh tokens
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as http_client:
            response = await http_client.post(
                "/api/v1/auth/login",
                json={"email": creds["email"], "password": creds["password"]},
            )
            if response.status_code != 200:
                print(f"  Error: Login failed for {creds['email']}")
                continue

            login_data = response.json()
            tokens = login_data["tokens"]

        # Create API client
        client = AtlasAPIClient(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
        )

        try:
            org_id = UUID(creds["organization_id"])
            org_name = creds["organization_name"]

            stats = await export_business_data(client, org_id, org_name, output_dir)
            all_stats[biz_key] = stats
        finally:
            await client.close()

    # Save summary
    summary = {
        "export_timestamp": datetime.now().isoformat(),
        "api_url": api_url,
        "businesses": all_stats,
        "totals": {
            "invoices": sum(s.get("invoices", 0) for s in all_stats.values()),
            "bills": sum(s.get("bills", 0) for s in all_stats.values()),
            "payments_received": sum(s.get("payments_received", 0) for s in all_stats.values()),
            "payments_made": sum(s.get("payments_made", 0) for s in all_stats.values()),
            "journal_entries": sum(s.get("journal_entries", 0) for s in all_stats.values()),
        },
    }

    (output_dir / "export_summary.json").write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 60)
    print("EXPORT COMPLETE")
    print("=" * 60)
    print("\nTotals across all businesses:")
    for key, value in summary["totals"].items():
        print(f"  {key}: {value:,}")
    print(f"\nOutput directory: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
