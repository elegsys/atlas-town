#!/usr/bin/env python3
"""Generate journal entries from existing invoices, bills, and payments.

This script creates journal entries for transactions that are missing them,
which can happen if the simulation ran without proper JE generation or if
journal entries were deleted.

Usage:
    cd packages/simulation
    uv run python scripts/generate_journal_entries.py --dry-run  # Preview
    uv run python scripts/generate_journal_entries.py            # Execute
    uv run python scripts/generate_journal_entries.py --org craig  # Single org

Journal Entry Patterns:
    Invoice (status=sent/paid):
        DEBIT  Accounts Receivable    total_amount
        CREDIT Revenue Account(s)     line amounts
        CREDIT Sales Tax Payable      tax_amount (if any)

    Bill (status=received/paid):
        DEBIT  Expense Account(s)     line amounts
        CREDIT Accounts Payable       total_amount

    Payment Received (status=completed):
        DEBIT  Deposit Account        amount
        CREDIT Accounts Receivable    amount
"""

import argparse
import asyncio
import os
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Business org IDs from simulation
# Note: Maya's data is in "Nexus Tech" not "Nexus Tech Consulting"
BUSINESS_ORGS = {
    "craig": "6e8d9a08-0208-4a6a-86c8-26412c9adb1b",
    "tony": "e3764ea7-ef6e-454f-9220-b5770931fbd7",
    "maya": "4c52731c-07c4-4189-812b-8595eadb3d53",  # Nexus Tech (has actual data)
    "chen": "abaec6e8-9f1d-413d-b525-50b6e8708092",
    "marcus": "799f5703-403d-4c3b-9e2b-c97e0b213b68",
}


class JournalEntryGenerator:
    """Generates journal entries from existing transactions."""

    def __init__(self, engine: AsyncEngine, dry_run: bool = False):
        self.engine = engine
        self.dry_run = dry_run
        self.stats: dict[str, int] = defaultdict(int)
        # Cache for account lookups per org
        self._account_cache: dict[str, UUID | None] = {}
        # Cache for entry number counters per company
        self._entry_counters: dict[str, int] = {}

    async def get_account(self, org_id: str, account_name: str) -> UUID | None:
        """Get account ID by name for an organization."""
        cache_key = f"{org_id}:{account_name}"
        if cache_key in self._account_cache:
            return self._account_cache[cache_key]

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT id FROM accounts
                    WHERE org_id = :org_id AND name = :name
                    LIMIT 1
                """),
                {"org_id": org_id, "name": account_name},
            )
            row = result.fetchone()
            account_id: UUID | None = row[0] if row else None
            self._account_cache[cache_key] = account_id
            return account_id

    async def get_next_entry_number(self, company_id: str, entry_date: str) -> str:
        """Generate next journal entry number for a company."""
        year = entry_date[:4]
        cache_key = f"{company_id}:{year}"

        if cache_key not in self._entry_counters:
            # Initialize counter from database
            async with self.engine.connect() as conn:
                result = await conn.execute(
                    text("""
                        SELECT COALESCE(
                            MAX(CAST(SUBSTRING(entry_number FROM 'JE-\\d{4}-(\\d+)') AS INTEGER)),
                            0
                        )
                        FROM journal_entries
                        WHERE company_id = :company_id
                          AND entry_number LIKE :pattern
                    """),
                    {"company_id": company_id, "pattern": f"JE-{year}-%"},
                )
                row = result.fetchone()
                self._entry_counters[cache_key] = row[0] if row else 0

        self._entry_counters[cache_key] += 1
        return f"JE-{year}-{self._entry_counters[cache_key]:04d}"

    async def create_invoice_journal_entries(self, org_id: str) -> int:
        """Create journal entries for invoices without JEs."""
        ar_account = await self.get_account(org_id, "Accounts Receivable")
        tax_account = await self.get_account(org_id, "Sales Tax Payable")

        if not ar_account:
            print(f"    WARNING: No AR account found for org {org_id}")
            return 0

        async with self.engine.connect() as conn:
            # Get invoices without journal entries
            result = await conn.execute(
                text("""
                    SELECT i.id, i.org_id, i.company_id, i.customer_id,
                           i.invoice_number, i.invoice_date, i.total_amount,
                           i.tax_amount, i.currency_code, i.exchange_rate,
                           c.display_name as customer_name
                    FROM invoices i
                    JOIN customers c ON c.id = i.customer_id
                    WHERE i.org_id = :org_id
                      AND i.status IN ('sent', 'paid')
                      AND i.journal_entry_id IS NULL
                    ORDER BY i.invoice_date
                """),
                {"org_id": org_id},
            )
            invoices = result.fetchall()

            if not invoices:
                return 0

            print(f"    Processing {len(invoices)} invoices...")
            created = 0

            for inv in invoices:
                # Get invoice lines for revenue accounts
                lines_result = await conn.execute(
                    text("""
                        SELECT revenue_account_id, SUM(amount) as total
                        FROM invoice_lines
                        WHERE invoice_id = :invoice_id
                        GROUP BY revenue_account_id
                    """),
                    {"invoice_id": str(inv.id)},
                )
                revenue_lines = lines_result.fetchall()

                if not revenue_lines:
                    continue

                # Generate entry number
                entry_number = await self.get_next_entry_number(
                    str(inv.company_id), str(inv.invoice_date)
                )

                je_id = uuid4()
                now = datetime.now(UTC)
                # Convert date to proper type if needed
                entry_date = (
                    inv.invoice_date
                    if isinstance(inv.invoice_date, date)
                    else date.fromisoformat(str(inv.invoice_date))
                )

                if not self.dry_run:
                    # Create journal entry
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entries (
                                id, org_id, company_id, entry_number, entry_date,
                                posting_date, entry_type, source_type, source_id,
                                description, status, posted_at, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :company_id, :entry_number, :entry_date,
                                :entry_date, 'invoice', 'invoice', :source_id,
                                :description, 'posted', :now, :now, :now
                            )
                        """),
                        {
                            "id": str(je_id),
                            "org_id": org_id,
                            "company_id": str(inv.company_id),
                            "entry_number": entry_number,
                            "entry_date": entry_date,
                            "source_id": str(inv.id),
                            "description": f"Invoice {inv.invoice_number} - {inv.customer_name}",
                            "now": now,
                        },
                    )

                    line_num = 1

                    # DEBIT: Accounts Receivable
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entry_lines (
                                id, org_id, journal_entry_id, account_id, line_number,
                                description, entry_type, amount, currency, exchange_rate,
                                base_amount, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :je_id, :account_id, :line_num,
                                :description, 'debit', :amount, :currency, :rate,
                                :base_amount, :now, :now
                            )
                        """),
                        {
                            "id": str(uuid4()),
                            "org_id": org_id,
                            "je_id": str(je_id),
                            "account_id": str(ar_account),
                            "line_num": line_num,
                            "description": f"Invoice {inv.invoice_number}",
                            "amount": str(inv.total_amount),
                            "currency": inv.currency_code or "USD",
                            "rate": str(inv.exchange_rate or 1),
                            "base_amount": str(inv.total_amount),
                            "now": now,
                        },
                    )
                    line_num += 1

                    # CREDIT: Revenue accounts (from lines)
                    for rev_line in revenue_lines:
                        await conn.execute(
                            text("""
                                INSERT INTO journal_entry_lines (
                                    id, org_id, journal_entry_id, account_id, line_number,
                                    description, entry_type, amount, currency, exchange_rate,
                                    base_amount, created_at, updated_at
                                ) VALUES (
                                    :id, :org_id, :je_id, :account_id, :line_num,
                                    :description, 'credit', :amount, :currency, :rate,
                                    :base_amount, :now, :now
                                )
                            """),
                            {
                                "id": str(uuid4()),
                                "org_id": org_id,
                                "je_id": str(je_id),
                                "account_id": str(rev_line.revenue_account_id),
                                "line_num": line_num,
                                "description": "Revenue",
                                "amount": str(rev_line.total),
                                "currency": inv.currency_code or "USD",
                                "rate": str(inv.exchange_rate or 1),
                                "base_amount": str(rev_line.total),
                                "now": now,
                            },
                        )
                        line_num += 1

                    # CREDIT: Sales Tax Payable (if tax > 0)
                    if inv.tax_amount and Decimal(str(inv.tax_amount)) > 0 and tax_account:
                        await conn.execute(
                            text("""
                                INSERT INTO journal_entry_lines (
                                    id, org_id, journal_entry_id, account_id, line_number,
                                    description, entry_type, amount, currency, exchange_rate,
                                    base_amount, created_at, updated_at
                                ) VALUES (
                                    :id, :org_id, :je_id, :account_id, :line_num,
                                    :description, 'credit', :amount, :currency, :rate,
                                    :base_amount, :now, :now
                                )
                            """),
                            {
                                "id": str(uuid4()),
                                "org_id": org_id,
                                "je_id": str(je_id),
                                "account_id": str(tax_account),
                                "line_num": line_num,
                                "description": "Sales Tax",
                                "amount": str(inv.tax_amount),
                                "currency": inv.currency_code or "USD",
                                "rate": str(inv.exchange_rate or 1),
                                "base_amount": str(inv.tax_amount),
                                "now": now,
                            },
                        )

                    # Update invoice with JE reference
                    await conn.execute(
                        text("""
                            UPDATE invoices SET journal_entry_id = :je_id
                            WHERE id = :invoice_id
                        """),
                        {"je_id": str(je_id), "invoice_id": str(inv.id)},
                    )

                created += 1
                if created % 500 == 0:
                    print(f"      ... {created}/{len(invoices)} invoices")

            if not self.dry_run:
                await conn.commit()

            return created

    async def create_bill_journal_entries(self, org_id: str) -> int:
        """Create journal entries for bills without JEs."""
        ap_account = await self.get_account(org_id, "Accounts Payable")

        if not ap_account:
            print(f"    WARNING: No AP account found for org {org_id}")
            return 0

        async with self.engine.connect() as conn:
            # Get bills without journal entries
            result = await conn.execute(
                text("""
                    SELECT b.id, b.org_id, b.company_id, b.vendor_id,
                           b.bill_number, b.bill_date, b.total_amount,
                           b.tax_amount, b.currency_code, b.exchange_rate,
                           v.display_name as vendor_name
                    FROM bills b
                    JOIN vendors v ON v.id = b.vendor_id
                    WHERE b.org_id = :org_id
                      AND b.status IN ('approved', 'draft')
                      AND b.journal_entry_id IS NULL
                    ORDER BY b.bill_date
                """),
                {"org_id": org_id},
            )
            bills = result.fetchall()

            if not bills:
                return 0

            print(f"    Processing {len(bills)} bills...")
            created = 0

            for bill in bills:
                # Get bill lines for expense accounts
                lines_result = await conn.execute(
                    text("""
                        SELECT expense_account_id, SUM(amount) as total
                        FROM bill_lines
                        WHERE bill_id = :bill_id
                        GROUP BY expense_account_id
                    """),
                    {"bill_id": str(bill.id)},
                )
                expense_lines = lines_result.fetchall()

                if not expense_lines:
                    continue

                entry_number = await self.get_next_entry_number(
                    str(bill.company_id), str(bill.bill_date)
                )

                je_id = uuid4()
                now = datetime.now(UTC)
                entry_date = (
                    bill.bill_date
                    if isinstance(bill.bill_date, date)
                    else date.fromisoformat(str(bill.bill_date))
                )

                if not self.dry_run:
                    # Create journal entry
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entries (
                                id, org_id, company_id, entry_number, entry_date,
                                posting_date, entry_type, source_type, source_id,
                                description, status, posted_at, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :company_id, :entry_number, :entry_date,
                                :entry_date, 'bill', 'bill', :source_id,
                                :description, 'posted', :now, :now, :now
                            )
                        """),
                        {
                            "id": str(je_id),
                            "org_id": org_id,
                            "company_id": str(bill.company_id),
                            "entry_number": entry_number,
                            "entry_date": entry_date,
                            "source_id": str(bill.id),
                            "description": f"Bill {bill.bill_number} - {bill.vendor_name}",
                            "now": now,
                        },
                    )

                    line_num = 1

                    # DEBIT: Expense accounts (from lines)
                    for exp_line in expense_lines:
                        await conn.execute(
                            text("""
                                INSERT INTO journal_entry_lines (
                                    id, org_id, journal_entry_id, account_id, line_number,
                                    description, entry_type, amount, currency, exchange_rate,
                                    base_amount, created_at, updated_at
                                ) VALUES (
                                    :id, :org_id, :je_id, :account_id, :line_num,
                                    :description, 'debit', :amount, :currency, :rate,
                                    :base_amount, :now, :now
                                )
                            """),
                            {
                                "id": str(uuid4()),
                                "org_id": org_id,
                                "je_id": str(je_id),
                                "account_id": str(exp_line.expense_account_id),
                                "line_num": line_num,
                                "description": "Expense",
                                "amount": str(exp_line.total),
                                "currency": bill.currency_code or "USD",
                                "rate": str(bill.exchange_rate or 1),
                                "base_amount": str(exp_line.total),
                                "now": now,
                            },
                        )
                        line_num += 1

                    # CREDIT: Accounts Payable
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entry_lines (
                                id, org_id, journal_entry_id, account_id, line_number,
                                description, entry_type, amount, currency, exchange_rate,
                                base_amount, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :je_id, :account_id, :line_num,
                                :description, 'credit', :amount, :currency, :rate,
                                :base_amount, :now, :now
                            )
                        """),
                        {
                            "id": str(uuid4()),
                            "org_id": org_id,
                            "je_id": str(je_id),
                            "account_id": str(ap_account),
                            "line_num": line_num,
                            "description": f"Bill {bill.bill_number}",
                            "amount": str(bill.total_amount),
                            "currency": bill.currency_code or "USD",
                            "rate": str(bill.exchange_rate or 1),
                            "base_amount": str(bill.total_amount),
                            "now": now,
                        },
                    )

                    # Update bill with JE reference
                    await conn.execute(
                        text("""
                            UPDATE bills SET journal_entry_id = :je_id
                            WHERE id = :bill_id
                        """),
                        {"je_id": str(je_id), "bill_id": str(bill.id)},
                    )

                created += 1
                if created % 500 == 0:
                    print(f"      ... {created}/{len(bills)} bills")

            if not self.dry_run:
                await conn.commit()

            return created

    async def create_payment_journal_entries(self, org_id: str) -> int:
        """Create journal entries for payments without JEs."""
        ar_account = await self.get_account(org_id, "Accounts Receivable")

        if not ar_account:
            print(f"    WARNING: No AR account found for org {org_id}")
            return 0

        async with self.engine.connect() as conn:
            # Get payments without journal entries
            result = await conn.execute(
                text("""
                    SELECT p.id, p.org_id, p.company_id, p.customer_id,
                           p.deposit_account_id, p.payment_number, p.payment_date,
                           p.amount, c.display_name as customer_name
                    FROM payments_received p
                    JOIN customers c ON c.id = p.customer_id
                    WHERE p.org_id = :org_id
                      AND p.status IN ('completed', 'draft')
                      AND p.journal_entry_id IS NULL
                    ORDER BY p.payment_date
                """),
                {"org_id": org_id},
            )
            payments = result.fetchall()

            if not payments:
                return 0

            print(f"    Processing {len(payments)} payments...")
            created = 0

            for pmt in payments:
                entry_number = await self.get_next_entry_number(
                    str(pmt.company_id), str(pmt.payment_date)
                )

                je_id = uuid4()
                now = datetime.now(UTC)
                entry_date = (
                    pmt.payment_date
                    if isinstance(pmt.payment_date, date)
                    else date.fromisoformat(str(pmt.payment_date))
                )

                if not self.dry_run:
                    # Create journal entry
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entries (
                                id, org_id, company_id, entry_number, entry_date,
                                posting_date, entry_type, source_type, source_id,
                                description, status, posted_at, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :company_id, :entry_number, :entry_date,
                                :entry_date, 'payment', 'payment_received', :source_id,
                                :description, 'posted', :now, :now, :now
                            )
                        """),
                        {
                            "id": str(je_id),
                            "org_id": org_id,
                            "company_id": str(pmt.company_id),
                            "entry_number": entry_number,
                            "entry_date": entry_date,
                            "source_id": str(pmt.id),
                            "description": f"Payment {pmt.payment_number} from {pmt.customer_name}",
                            "now": now,
                        },
                    )

                    # DEBIT: Deposit Account (bank/cash)
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entry_lines (
                                id, org_id, journal_entry_id, account_id, line_number,
                                description, entry_type, amount, currency, exchange_rate,
                                base_amount, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :je_id, :account_id, 1,
                                :description, 'debit', :amount, 'USD', 1.0,
                                :amount, :now, :now
                            )
                        """),
                        {
                            "id": str(uuid4()),
                            "org_id": org_id,
                            "je_id": str(je_id),
                            "account_id": str(pmt.deposit_account_id),
                            "description": f"Payment {pmt.payment_number}",
                            "amount": str(pmt.amount),
                            "now": now,
                        },
                    )

                    # CREDIT: Accounts Receivable
                    await conn.execute(
                        text("""
                            INSERT INTO journal_entry_lines (
                                id, org_id, journal_entry_id, account_id, line_number,
                                description, entry_type, amount, currency, exchange_rate,
                                base_amount, created_at, updated_at
                            ) VALUES (
                                :id, :org_id, :je_id, :account_id, 2,
                                :description, 'credit', :amount, 'USD', 1.0,
                                :amount, :now, :now
                            )
                        """),
                        {
                            "id": str(uuid4()),
                            "org_id": org_id,
                            "je_id": str(je_id),
                            "account_id": str(ar_account),
                            "description": f"Payment {pmt.payment_number}",
                            "amount": str(pmt.amount),
                            "now": now,
                        },
                    )

                    # Update payment with JE reference
                    await conn.execute(
                        text("""
                            UPDATE payments_received SET journal_entry_id = :je_id
                            WHERE id = :payment_id
                        """),
                        {"je_id": str(je_id), "payment_id": str(pmt.id)},
                    )

                created += 1
                if created % 500 == 0:
                    print(f"      ... {created}/{len(payments)} payments")

            if not self.dry_run:
                await conn.commit()

            return created

    async def process_organization(self, org_id: str, org_name: str) -> dict[str, int]:
        """Process all transactions for an organization."""
        print(f"\n  {org_name}")
        print("  " + "-" * 50)

        results = {
            "invoices": await self.create_invoice_journal_entries(org_id),
            "bills": await self.create_bill_journal_entries(org_id),
            "payments": await self.create_payment_journal_entries(org_id),
        }

        total = sum(results.values())
        print(f"    Total: {total} journal entries {'(dry-run)' if self.dry_run else 'created'}")

        return results

    async def verify_balance(self) -> bool:
        """Verify that total debits = total credits."""
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT
                        SUM(CASE WHEN entry_type = 'debit' THEN amount ELSE 0 END) as debits,
                        SUM(CASE WHEN entry_type = 'credit' THEN amount ELSE 0 END) as credits
                    FROM journal_entry_lines
                """)
            )
            row = result.fetchone()
            debits = Decimal(str(row.debits or 0)) if row else Decimal("0")
            credits = Decimal(str(row.credits or 0)) if row else Decimal("0")
            diff = abs(debits - credits)

            print("\n  Verification:")
            print(f"    Total Debits:  ${debits:,.2f}")
            print(f"    Total Credits: ${credits:,.2f}")
            print(f"    Difference:    ${diff:,.2f}")

            return diff < Decimal("0.01")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate journal entries from existing transactions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without creating entries",
    )
    parser.add_argument(
        "--org",
        type=str,
        choices=list(BUSINESS_ORGS.keys()),
        help="Process single organization",
    )
    args = parser.parse_args()

    # Database URL
    db_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/atlas_dev"
    )

    print("=" * 60)
    print("Generate Journal Entries from Transactions")
    print("=" * 60)
    print(f"\nDatabase: {db_url.split('@')[1] if '@' in db_url else db_url}")
    print(f"Mode: {'DRY-RUN (no changes)' if args.dry_run else 'EXECUTE'}")

    engine = create_async_engine(db_url, echo=False)
    generator = JournalEntryGenerator(engine, dry_run=args.dry_run)

    # Determine which orgs to process
    orgs_to_process = {args.org: BUSINESS_ORGS[args.org]} if args.org else BUSINESS_ORGS

    all_results = {}
    total_jes = 0

    for org_key, org_id in orgs_to_process.items():
        # Get org name
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM organizations WHERE id = :id"),
                {"id": org_id},
            )
            row = result.fetchone()
            org_name = row[0] if row else org_key

        results = await generator.process_organization(org_id, org_name)
        all_results[org_key] = results
        total_jes += sum(results.values())

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for org_key, results in all_results.items():
        print(f"\n  {org_key}:")
        print(f"    Invoices: {results['invoices']}")
        print(f"    Bills:    {results['bills']}")
        print(f"    Payments: {results['payments']}")

    print(f"\n  TOTAL: {total_jes} journal entries {'(dry-run)' if args.dry_run else 'created'}")

    # Verify balance
    if not args.dry_run and total_jes > 0:
        balanced = await generator.verify_balance()
        if balanced:
            print("\n  ✓ Accounting equation balanced!")
        else:
            print("\n  ✗ WARNING: Accounting imbalance detected!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
