"""Deterministic accounting workflow - Non-LLM alternative to Sarah agent.

This module provides rule-based accounting operations that can replace
the LLM-driven AccountantAgent for scenarios where:
- You need faster execution (no API latency)
- You want deterministic, reproducible results
- You're generating bulk data
- You don't need natural language interaction

The LLM agent is still valuable for:
- Interactive Q&A with users
- Handling unexpected edge cases
- Generating insights and analysis
- Demo/showcase scenarios
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog

from atlas_town.transactions import (
    GeneratedTransaction,
    TransactionGenerator,
    TransactionType,
)
from atlas_town.tools.atlas_api import AtlasAPIClient

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class DailySummary:
    """Summary of a day's accounting activity."""

    org_name: str
    date: date
    invoices_created: int
    invoices_total: Decimal
    bills_created: int
    bills_total: Decimal
    payments_received: int
    payments_total: Decimal
    bills_paid: int
    bills_paid_total: Decimal
    trial_balance_ok: bool
    issues: list[str]

    def to_text(self) -> str:
        """Generate a text summary (replaces LLM-generated summaries)."""
        status = "✓ Balanced" if self.trial_balance_ok else "✗ UNBALANCED"

        issues_text = ""
        if self.issues:
            issues_text = "\n\nIssues requiring attention:\n" + "\n".join(
                f"  - {issue}" for issue in self.issues
            )

        return f"""
Daily Summary for {self.org_name} - {self.date}
{'=' * 50}

Revenue Activity:
  Invoices Created: {self.invoices_created} (${self.invoices_total:,.2f})
  Payments Received: {self.payments_received} (${self.payments_total:,.2f})

Expense Activity:
  Bills Entered: {self.bills_created} (${self.bills_total:,.2f})
  Bills Paid: {self.bills_paid} (${self.bills_paid_total:,.2f})

Books Status: {status}
{issues_text}
""".strip()


# =============================================================================
# DETERMINISTIC ACCOUNTING WORKFLOW
# =============================================================================


class AccountingWorkflow:
    """Rule-based accounting workflow - no LLM required.

    This class handles all accounting operations through direct API calls
    with deterministic logic. It replaces the think-act-observe loop of
    the LLM agent with explicit, predictable code paths.
    """

    def __init__(
        self,
        api_client: AtlasAPIClient,
        transaction_generator: TransactionGenerator | None = None,
    ):
        self._api = api_client
        self._tx_gen = transaction_generator or TransactionGenerator()
        self._logger = logger.bind(component="accounting_workflow")

    # =========================================================================
    # CORE WORKFLOWS (Replace LLM decision-making)
    # =========================================================================

    async def run_daily_workflow(
        self,
        business_key: str,
        org_id: UUID,
        current_date: date,
        current_hour: int | None = None,
        current_phase: str | None = None,
    ) -> DailySummary:
        """Run complete daily accounting workflow for a business.

        This replaces the LLM's "End of day" task with deterministic steps:
        1. Generate transactions (probabilistic - unchanged)
        2. Create invoices (deterministic)
        3. Record payments (deterministic)
        4. Enter bills (deterministic)
        5. Pay due bills (deterministic)
        6. Run trial balance (deterministic)
        7. Generate summary (template-based)
        """
        self._logger.info(
            "starting_daily_workflow",
            business=business_key,
            org_id=str(org_id),
            date=current_date.isoformat(),
        )

        # Set organization context
        self._api.set_org_id(org_id)
        org_name = await self._get_org_name(org_id)

        # Step 1: Generate transactions (probabilistic layer - unchanged)
        customers = await self._api.list_customers()
        vendors = await self._api.list_vendors()
        pending_invoices = await self._api.list_invoices(status="sent")

        transactions = self._tx_gen.generate_daily_transactions(
            business_key=business_key,
            current_date=current_date,
            customers=customers,
            vendors=vendors,
            pending_invoices=pending_invoices,
            current_hour=current_hour,
            current_phase=current_phase,
        )

        # Step 2-5: Process transactions (deterministic)
        results = await self._process_transactions(transactions, current_date)

        # Step 6: Verify books are balanced
        trial_balance = await self._api.get_trial_balance(as_of_date=current_date)
        is_balanced = self._check_trial_balance(trial_balance)

        # Step 7: Identify any issues
        issues = await self._identify_issues(org_id, current_date)

        summary = DailySummary(
            org_name=org_name,
            date=current_date,
            invoices_created=results["invoices_created"],
            invoices_total=results["invoices_total"],
            bills_created=results["bills_created"],
            bills_total=results["bills_total"],
            payments_received=results["payments_received"],
            payments_total=results["payments_total"],
            bills_paid=results["bills_paid"],
            bills_paid_total=results["bills_paid_total"],
            trial_balance_ok=is_balanced,
            issues=issues,
        )

        self._logger.info(
            "daily_workflow_complete",
            business=business_key,
            invoices=summary.invoices_created,
            bills=summary.bills_created,
            balanced=is_balanced,
        )

        return summary

    async def _process_transactions(
        self,
        transactions: list[GeneratedTransaction],
        current_date: date,
    ) -> dict[str, Any]:
        """Process generated transactions into accounting records.

        This is the deterministic replacement for LLM tool-calling.
        Instead of the LLM deciding what to do, we have explicit rules.
        """
        results = {
            "invoices_created": 0,
            "invoices_total": Decimal("0"),
            "bills_created": 0,
            "bills_total": Decimal("0"),
            "payments_received": 0,
            "payments_total": Decimal("0"),
            "bills_paid": 0,
            "bills_paid_total": Decimal("0"),
        }

        for tx in transactions:
            try:
                if tx.transaction_type == TransactionType.INVOICE:
                    await self._create_invoice(tx, current_date)
                    results["invoices_created"] += 1
                    results["invoices_total"] += tx.amount

                elif tx.transaction_type == TransactionType.CASH_SALE:
                    # Cash sales: create invoice + immediate payment
                    invoice = await self._create_invoice(tx, current_date)
                    if invoice:
                        await self._record_payment(
                            invoice_id=invoice["id"],
                            amount=tx.amount,
                            payment_date=current_date,
                        )
                    results["invoices_created"] += 1
                    results["invoices_total"] += tx.amount
                    results["payments_received"] += 1
                    results["payments_total"] += tx.amount

                elif tx.transaction_type == TransactionType.BILL:
                    await self._create_bill(tx, current_date)
                    results["bills_created"] += 1
                    results["bills_total"] += tx.amount

                elif tx.transaction_type == TransactionType.PAYMENT_RECEIVED:
                    # Payment for existing invoice
                    if tx.metadata and tx.metadata.get("invoice_id"):
                        await self._record_payment(
                            invoice_id=tx.metadata["invoice_id"],
                            amount=tx.amount,
                            payment_date=current_date,
                        )
                        results["payments_received"] += 1
                        results["payments_total"] += tx.amount

                elif tx.transaction_type == TransactionType.BILL_PAYMENT:
                    if tx.metadata and tx.metadata.get("bill_id"):
                        await self._pay_bill(
                            bill_id=tx.metadata["bill_id"],
                            amount=tx.amount,
                            payment_date=current_date,
                        )
                        results["bills_paid"] += 1
                        results["bills_paid_total"] += tx.amount

            except Exception as e:
                self._logger.error(
                    "transaction_processing_error",
                    tx_type=tx.transaction_type.value,
                    error=str(e),
                )

        return results

    # =========================================================================
    # ACCOUNTING OPERATIONS (Direct API calls - no LLM)
    # =========================================================================

    async def _create_invoice(
        self,
        tx: GeneratedTransaction,
        invoice_date: date,
    ) -> dict[str, Any] | None:
        """Create an invoice - deterministic, no LLM reasoning needed."""
        if not tx.customer_id:
            self._logger.warning("invoice_missing_customer", description=tx.description)
            return None

        due_date = invoice_date + timedelta(days=30)  # Net 30 terms

        invoice = await self._api.create_invoice(
            customer_id=str(tx.customer_id),
            line_items=[
                {
                    "description": tx.description,
                    "quantity": 1,
                    "unit_price": float(tx.amount),
                }
            ],
            invoice_date=invoice_date,
            due_date=due_date,
        )

        # Auto-send the invoice
        if invoice and invoice.get("id"):
            await self._api.send_invoice(invoice["id"])

        return invoice

    async def _create_bill(
        self,
        tx: GeneratedTransaction,
        bill_date: date,
    ) -> dict[str, Any] | None:
        """Create a bill - deterministic, no LLM reasoning needed."""
        if not tx.vendor_id:
            self._logger.warning("bill_missing_vendor", description=tx.description)
            return None

        due_date = bill_date + timedelta(days=30)  # Net 30 terms

        bill = await self._api.create_bill(
            vendor_id=str(tx.vendor_id),
            line_items=[
                {
                    "description": tx.description,
                    "quantity": 1,
                    "unit_price": float(tx.amount),
                }
            ],
            bill_date=bill_date,
            due_date=due_date,
        )

        return bill

    async def _record_payment(
        self,
        invoice_id: str,
        amount: Decimal,
        payment_date: date,
    ) -> dict[str, Any] | None:
        """Record a customer payment - deterministic."""
        payment = await self._api.create_payment(
            invoice_id=invoice_id,
            amount=float(amount),
            payment_date=payment_date,
            payment_method="check",  # Default method
        )
        return payment

    async def _pay_bill(
        self,
        bill_id: str,
        amount: Decimal,
        payment_date: date,
    ) -> dict[str, Any] | None:
        """Pay a vendor bill - deterministic."""
        payment = await self._api.create_bill_payment(
            bill_id=bill_id,
            amount=float(amount),
            payment_date=payment_date,
            payment_method="check",
        )
        return payment

    # =========================================================================
    # VERIFICATION & REPORTING (Template-based - no LLM)
    # =========================================================================

    def _check_trial_balance(self, trial_balance: dict[str, Any]) -> bool:
        """Check if trial balance is balanced - simple comparison."""
        total_debits = Decimal(str(trial_balance.get("total_debits", 0)))
        total_credits = Decimal(str(trial_balance.get("total_credits", 0)))

        # Allow for small rounding differences
        return abs(total_debits - total_credits) < Decimal("0.01")

    async def _identify_issues(
        self,
        org_id: UUID,
        current_date: date,
    ) -> list[str]:
        """Identify accounting issues - rule-based, no LLM analysis."""
        issues = []

        # Check for overdue invoices
        overdue_invoices = await self._api.list_invoices(status="overdue")
        if overdue_invoices:
            total_overdue = sum(
                Decimal(str(inv.get("balance", 0))) for inv in overdue_invoices
            )
            issues.append(
                f"{len(overdue_invoices)} overdue invoices totaling ${total_overdue:,.2f}"
            )

        # Check for bills due soon
        upcoming_bills = await self._api.list_bills(status="pending")
        bills_due_soon = [
            b for b in upcoming_bills
            if self._is_due_within_days(b.get("due_date"), current_date, 7)
        ]
        if bills_due_soon:
            total_due = sum(
                Decimal(str(b.get("balance", 0))) for b in bills_due_soon
            )
            issues.append(
                f"{len(bills_due_soon)} bills due within 7 days totaling ${total_due:,.2f}"
            )

        # Check for large outstanding receivables
        ar_aging = await self._api.get_ar_aging()
        if ar_aging:
            over_90 = Decimal(str(ar_aging.get("over_90_days", 0)))
            if over_90 > Decimal("1000"):
                issues.append(f"${over_90:,.2f} in receivables over 90 days old")

        return issues

    def _is_due_within_days(
        self,
        due_date_str: str | None,
        current_date: date,
        days: int,
    ) -> bool:
        """Check if a date is within N days."""
        if not due_date_str:
            return False
        try:
            due_date = date.fromisoformat(due_date_str[:10])
            return current_date <= due_date <= current_date + timedelta(days=days)
        except (ValueError, TypeError):
            return False

    async def _get_org_name(self, org_id: UUID) -> str:
        """Get organization name."""
        try:
            org = await self._api.get_organization(str(org_id))
            return org.get("name", f"Org {org_id}")
        except Exception:
            return f"Organization {org_id}"

    # =========================================================================
    # BATCH OPERATIONS (Efficient bulk processing)
    # =========================================================================

    async def run_month(
        self,
        business_key: str,
        org_id: UUID,
        year: int,
        month: int,
    ) -> list[DailySummary]:
        """Run accounting for an entire month - much faster without LLM.

        With LLM: ~30 seconds per day = ~15 minutes for a month
        Without LLM: ~1 second per day = ~30 seconds for a month
        """
        from calendar import monthrange

        _, num_days = monthrange(year, month)
        summaries = []

        for day in range(1, num_days + 1):
            current_date = date(year, month, day)

            # Skip weekends for some businesses
            if current_date.weekday() >= 5 and business_key in ["chen", "maya"]:
                continue

            summary = await self.run_daily_workflow(
                business_key=business_key,
                org_id=org_id,
                current_date=current_date,
            )
            summaries.append(summary)

        return summaries

    def generate_monthly_report(
        self,
        summaries: list[DailySummary],
    ) -> str:
        """Generate monthly report from daily summaries - template-based."""
        if not summaries:
            return "No data for this period."

        org_name = summaries[0].org_name
        month_start = summaries[0].date
        month_end = summaries[-1].date

        total_invoices = sum(s.invoices_created for s in summaries)
        total_invoice_amount = sum(s.invoices_total for s in summaries)
        total_payments = sum(s.payments_received for s in summaries)
        total_payment_amount = sum(s.payments_total for s in summaries)
        total_bills = sum(s.bills_created for s in summaries)
        total_bill_amount = sum(s.bills_total for s in summaries)
        total_bills_paid = sum(s.bills_paid for s in summaries)
        total_bills_paid_amount = sum(s.bills_paid_total for s in summaries)

        unbalanced_days = [s.date for s in summaries if not s.trial_balance_ok]
        all_issues = []
        for s in summaries:
            all_issues.extend(s.issues)

        return f"""
Monthly Report: {org_name}
Period: {month_start} to {month_end}
{'=' * 60}

REVENUE SUMMARY
  Invoices Created: {total_invoices}
  Total Invoiced: ${total_invoice_amount:,.2f}
  Payments Received: {total_payments}
  Total Collected: ${total_payment_amount:,.2f}
  Collection Rate: {(total_payment_amount / total_invoice_amount * 100) if total_invoice_amount else 0:.1f}%

EXPENSE SUMMARY
  Bills Entered: {total_bills}
  Total Billed: ${total_bill_amount:,.2f}
  Bills Paid: {total_bills_paid}
  Total Paid: ${total_bills_paid_amount:,.2f}

NET ACTIVITY
  Net Revenue: ${total_payment_amount - total_bills_paid_amount:,.2f}

BOOKS STATUS
  Days with balanced books: {len(summaries) - len(unbalanced_days)}/{len(summaries)}
  {f"Unbalanced days: {unbalanced_days}" if unbalanced_days else "All days balanced ✓"}

{f"ISSUES IDENTIFIED ({len(all_issues)}):" if all_issues else "No issues identified."}
{chr(10).join(f"  - {issue}" for issue in all_issues[:10])}
{f"  ... and {len(all_issues) - 10} more" if len(all_issues) > 10 else ""}
""".strip()


# =============================================================================
# COMPARISON: LLM vs Non-LLM
# =============================================================================

"""
PERFORMANCE COMPARISON:

| Operation              | LLM-Based         | Rule-Based        |
|------------------------|-------------------|-------------------|
| Daily workflow         | ~20-30 seconds    | ~1-2 seconds      |
| Monthly workflow       | ~15 minutes       | ~30 seconds       |
| Create invoice         | ~2-3 seconds      | ~100ms            |
| Generate summary       | ~3-5 seconds      | ~1ms              |
| API cost               | $0.01-0.05/day    | $0                |

WHEN TO USE EACH:

LLM-Based (AccountantAgent):
  - Interactive demos where "thinking" adds value
  - User Q&A ("Why did expenses increase?")
  - Handling edge cases not covered by rules
  - Generating insights and analysis
  - When personality/narrative matters

Rule-Based (AccountingWorkflow):
  - Bulk data generation
  - Automated testing
  - Performance-critical paths
  - Reproducible simulations
  - Cost-sensitive environments

HYBRID APPROACH:
  # Use rule-based for transactions
  workflow = AccountingWorkflow(api_client)
  summary = await workflow.run_daily_workflow(...)

  # Use LLM only for analysis/Q&A
  if user_has_question:
      agent = AccountantAgent()
      response = await agent.run_task(
          f"Analyze this summary and answer: {user_question}\n{summary.to_text()}"
      )
"""
