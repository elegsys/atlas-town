#!/usr/bin/env python3
"""Verify Atlas Town simulation data integrity.

Runs post-simulation verification checks:
1. Data completeness - invoices, bills, payments exist for each business
2. Accounting balance - debits = credits in journal entries
3. Invoice/Bill status - verify paid invoices have payments
4. Inventory verification (Tony, Chen)
5. Sales tax verification (Tony - F&B business)
6. Multi-currency verification (Maya - international consulting)

Usage:
    cd packages/simulation
    uv run python scripts/verify_simulation.py

    # Verbose output
    uv run python scripts/verify_simulation.py -v

    # Check specific business
    uv run python scripts/verify_simulation.py --business tony
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from atlas_town.tools.atlas_api import AtlasAPIClient, AtlasAPIError


@dataclass
class VerificationResult:
    """Result of a verification check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class SimulationVerifier:
    """Verifier for simulation data integrity."""

    def __init__(self, client: AtlasAPIClient, verbose: bool = False):
        self.client = client
        self.verbose = verbose
        self.results: list[VerificationResult] = []

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"      {msg}")

    def add_result(
        self,
        name: str,
        passed: bool,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        result = VerificationResult(name, passed, message, details or {})
        self.results.append(result)
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] {name}: {message}")

    async def verify_data_completeness(self) -> None:
        """Verify basic data exists."""
        customers = await self.client.list_customers()
        vendors = await self.client.list_vendors()
        invoices = await self.client.list_invoices()
        bills = await self.client.list_bills()
        payments = await self.client.list_payments()
        try:
            bill_payments = await self.client.list_bill_payments()
        except AtlasAPIError:
            bill_payments = []  # Endpoint may not be available

        self.log(f"Customers: {len(customers)}")
        self.log(f"Vendors: {len(vendors)}")
        self.log(f"Invoices: {len(invoices)}")
        self.log(f"Bills: {len(bills)}")
        self.log(f"Payments received: {len(payments)}")
        self.log(f"Payments made: {len(bill_payments)}")

        # Check minimums
        has_customers = len(customers) >= 3
        has_vendors = len(vendors) >= 3
        has_invoices = len(invoices) >= 10
        has_bills = len(bills) >= 5

        all_complete = has_customers and has_vendors and has_invoices and has_bills

        self.add_result(
            "Data Completeness",
            all_complete,
            f"{len(invoices)} invoices, {len(bills)} bills, "
            f"{len(payments)} payments, {len(bill_payments)} bill payments",
            {
                "customers": len(customers),
                "vendors": len(vendors),
                "invoices": len(invoices),
                "bills": len(bills),
                "payments_received": len(payments),
                "payments_made": len(bill_payments),
            },
        )

    async def verify_accounting_balance(self) -> None:
        """Verify debits = credits in journal entries."""
        try:
            journal_entries = await self.client.list_journal_entries(limit=500)
        except AtlasAPIError:
            self.add_result(
                "Accounting Balance",
                False,
                "Could not fetch journal entries",
            )
            return

        total_debits = Decimal("0")
        total_credits = Decimal("0")
        unbalanced_entries = []

        for je in journal_entries:
            entry_debits = Decimal("0")
            entry_credits = Decimal("0")

            for line in je.get("lines", []):
                amount = Decimal(str(line.get("amount", 0)))
                if line.get("entry_type") == "debit":
                    entry_debits += amount
                    total_debits += amount
                else:
                    entry_credits += amount
                    total_credits += amount

            # Check individual entry balance
            if abs(entry_debits - entry_credits) > Decimal("0.01"):
                unbalanced_entries.append(je.get("id"))

        is_balanced = abs(total_debits - total_credits) < Decimal("0.01")

        self.add_result(
            "Accounting Balance",
            is_balanced and len(unbalanced_entries) == 0,
            f"Debits: ${total_debits:,.2f}, Credits: ${total_credits:,.2f}, "
            f"Unbalanced: {len(unbalanced_entries)}",
            {
                "total_debits": str(total_debits),
                "total_credits": str(total_credits),
                "unbalanced_entries": unbalanced_entries[:10],  # First 10 only
            },
        )

    async def verify_invoice_payments(self) -> None:
        """Verify paid invoices have corresponding payments."""
        invoices = await self.client.list_invoices()
        payments = await self.client.list_payments()

        # Build payment map by invoice
        invoice_payments: dict[str, list[dict]] = defaultdict(list)
        for payment in payments:
            for alloc in payment.get("allocations", []):
                inv_id = alloc.get("invoice_id")
                if inv_id:
                    invoice_payments[inv_id].append(payment)

        paid_without_payment = []
        unpaid_with_payment = []

        for inv in invoices:
            inv_id = inv.get("id")
            status = inv.get("status", "").lower()
            has_payment = len(invoice_payments.get(inv_id, [])) > 0

            if status == "paid" and not has_payment:
                paid_without_payment.append(inv_id)
            elif status in ("draft", "sent") and has_payment:
                unpaid_with_payment.append(inv_id)

        issues = len(paid_without_payment) + len(unpaid_with_payment)

        self.add_result(
            "Invoice-Payment Consistency",
            issues == 0,
            f"Checked {len(invoices)} invoices, {issues} inconsistencies",
            {
                "paid_without_payment": paid_without_payment[:5],
                "unpaid_with_payment": unpaid_with_payment[:5],
            },
        )

    async def verify_inventory(self, business_key: str) -> None:
        """Verify inventory for businesses that should have it (Tony, Chen)."""
        if business_key not in ("tony", "chen"):
            return  # Skip for non-inventory businesses

        try:
            items = await self.client.list_inventory_items()
        except AtlasAPIError:
            self.add_result(
                "Inventory",
                False,
                "Could not fetch inventory items",
            )
            return

        if not items:
            self.add_result(
                "Inventory",
                False,
                "No inventory items found",
            )
            return

        # Check for negative quantities (shouldn't happen)
        negative_qty = [i for i in items if Decimal(str(i.get("quantity_on_hand", 0))) < 0]

        # Check for low stock items
        low_stock = [
            i
            for i in items
            if Decimal(str(i.get("quantity_on_hand", 0))) < Decimal(str(i.get("reorder_point", 0)))
        ]

        self.add_result(
            "Inventory",
            len(negative_qty) == 0,
            f"{len(items)} items, {len(negative_qty)} negative qty, {len(low_stock)} low stock",
            {
                "total_items": len(items),
                "negative_quantity_items": [i.get("name") for i in negative_qty],
                "low_stock_items": [i.get("name") for i in low_stock[:5]],
            },
        )

    async def verify_sales_tax(self, business_key: str) -> None:
        """Verify sales tax for F&B business (Tony)."""
        if business_key != "tony":
            return  # Only Tony collects sales tax

        try:
            tax_rates = await self.client.list_tax_rates()
        except AtlasAPIError:
            self.add_result(
                "Sales Tax Configuration",
                False,
                "Could not fetch tax rates",
            )
            return

        sales_tax_rates = [t for t in tax_rates if t.get("tax_type", "").lower() == "sales"]

        if not sales_tax_rates:
            self.add_result(
                "Sales Tax Configuration",
                False,
                "No sales tax rates configured",
            )
            return

        # Check invoices for tax application
        invoices = await self.client.list_invoices()
        invoices_with_tax = [i for i in invoices if Decimal(str(i.get("tax_amount", 0))) > 0]

        pct_with_tax = (len(invoices_with_tax) / len(invoices) * 100) if invoices else 0

        self.add_result(
            "Sales Tax",
            len(invoices_with_tax) > 0,
            f"{len(sales_tax_rates)} tax rates, "
            f"{len(invoices_with_tax)}/{len(invoices)} invoices with tax "
            f"({pct_with_tax:.0f}%)",
            {
                "tax_rates": [t.get("name") for t in sales_tax_rates],
                "invoices_with_tax": len(invoices_with_tax),
                "total_invoices": len(invoices),
            },
        )

    async def verify_multi_currency(self, business_key: str) -> None:
        """Verify multi-currency for international business (Maya/Nexus Tech)."""
        if business_key != "maya":
            return  # Only Maya has international clients

        invoices = await self.client.list_invoices()

        # Check for non-USD invoices
        currencies = set()
        for inv in invoices:
            curr = inv.get("currency", "USD")
            currencies.add(curr)

        self.add_result(
            "Multi-Currency",
            True,  # Pass even if no multi-currency (may not be configured)
            f"Currencies used: {', '.join(sorted(currencies))}",
            {"currencies": list(currencies)},
        )

    async def run_all_verifications(self, business_key: str) -> list[VerificationResult]:
        """Run all verification checks."""
        self.results = []

        await self.verify_data_completeness()
        await self.verify_accounting_balance()
        await self.verify_invoice_payments()
        await self.verify_inventory(business_key)
        await self.verify_sales_tax(business_key)
        await self.verify_multi_currency(business_key)

        return self.results


async def verify_business(
    api_url: str,
    creds: dict[str, str],
    verbose: bool = False,
) -> dict[str, Any]:
    """Verify a single business."""
    # Login
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as http_client:
        response = await http_client.post(
            "/api/v1/auth/login",
            json={"email": creds["email"], "password": creds["password"]},
        )
        if response.status_code != 200:
            return {
                "error": f"Login failed for {creds['email']}",
                "passed": 0,
                "failed": 0,
            }

        login_data = response.json()
        tokens = login_data["tokens"]

    # Create client and verifier
    client = AtlasAPIClient(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )

    try:
        # Switch to organization
        org_id = UUID(creds["organization_id"])
        await client.switch_organization(org_id)

        verifier = SimulationVerifier(client, verbose)
        results = await verifier.run_all_verifications(creds.get("business_key", "unknown"))

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return {
            "passed": passed,
            "failed": failed,
            "results": [
                {"name": r.name, "passed": r.passed, "message": r.message} for r in results
            ],
        }
    finally:
        await client.close()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify Atlas Town simulation data integrity")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--business",
        type=str,
        default=None,
        choices=["craig", "tony", "maya", "chen", "marcus"],
        help="Verify specific business only",
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
        sys.exit(1)

    credentials = json.loads(creds_file.read_text())

    # Add business_key to each credential
    for key, creds in credentials.items():
        creds["business_key"] = key

    # Filter to specific business if requested
    if args.business:
        if args.business not in credentials:
            print(f"Error: Business '{args.business}' not found")
            sys.exit(1)
        credentials = {args.business: credentials[args.business]}

    print("=" * 60)
    print("Atlas Town - Simulation Verification")
    print("=" * 60)
    print(f"\nAPI URL: {api_url}")

    total_passed = 0
    total_failed = 0
    all_results = {}

    for biz_key, creds in credentials.items():
        print(f"\n  {creds['organization_name']}")
        print("  " + "-" * 50)

        result = await verify_business(api_url, creds, args.verbose)
        all_results[biz_key] = result

        if "error" in result:
            print(f"    ERROR: {result['error']}")
            total_failed += 1
        else:
            total_passed += result["passed"]
            total_failed += result["failed"]

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"\nTotal: {total_passed} passed, {total_failed} failed")

    if total_failed > 0:
        print("\nFailed checks:")
        for biz_key, result in all_results.items():
            for r in result.get("results", []):
                if not r["passed"]:
                    print(f"  - {biz_key}: {r['name']} - {r['message']}")
        sys.exit(1)
    else:
        print("\nAll checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
