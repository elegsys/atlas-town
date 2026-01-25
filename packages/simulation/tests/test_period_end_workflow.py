"""Tests for period-end workflows in AccountingWorkflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from atlas_town.accounting_workflow import AccountingWorkflow


@dataclass
class FakeAPI:
    accounts: list[dict[str, Any]] = field(default_factory=list)
    bills: list[dict[str, Any]] = field(default_factory=list)
    bank_transactions: list[dict[str, Any]] = field(default_factory=list)
    bank_accounts: list[dict[str, Any]] = field(default_factory=list)
    payments: list[dict[str, Any]] = field(default_factory=list)
    payments_made: list[dict[str, Any]] = field(default_factory=list)
    customers: list[dict[str, Any]] = field(default_factory=list)
    vendors: list[dict[str, Any]] = field(default_factory=list)
    budgets: list[dict[str, Any]] = field(default_factory=list)
    vendor_tax_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    profit_loss: dict[str, Any] = field(default_factory=dict)
    balance_sheet: dict[str, Any] = field(default_factory=dict)
    cash_flow: dict[str, Any] = field(default_factory=dict)
    trial_balance: dict[str, Any] = field(default_factory=dict)
    ar_aging: dict[str, Any] = field(default_factory=dict)
    ap_aging: dict[str, Any] = field(default_factory=dict)
    journal_entries: list[dict[str, Any]] = field(default_factory=list)

    async def switch_organization(self, org_id: UUID) -> None:  # noqa: ARG002
        return None

    async def list_accounts(self, limit: int = 200) -> list[dict[str, Any]]:  # noqa: ARG002
        return self.accounts

    async def list_bills(
        self,
        offset: int = 0,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
        status: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.bills

    async def list_invoices(
        self, offset: int = 0, limit: int = 100, status: str | None = None  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return []

    async def list_bank_transactions(
        self,
        bank_account_id: UUID,  # noqa: ARG002
        offset: int = 0,  # noqa: ARG002
        limit: int = 200,  # noqa: ARG002
        status_filter: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.bank_transactions

    async def list_bank_accounts(
        self, include_inactive: bool = False  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.bank_accounts

    async def list_payments(
        self, offset: int = 0, limit: int = 100  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.payments

    async def list_payments_made(
        self, offset: int = 0, limit: int = 100  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.payments_made

    async def list_customers(self) -> list[dict[str, Any]]:
        return self.customers

    async def list_vendors(self) -> list[dict[str, Any]]:
        return self.vendors

    async def list_budgets(
        self,
        offset: int = 0,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
        fiscal_year: int | None = None,  # noqa: ARG002
        status: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.budgets

    async def create_budget(self, data: dict[str, Any]) -> dict[str, Any]:
        budget = {"id": str(uuid4()), **data}
        self.budgets.append(budget)
        return budget

    async def get_vendor_tax_profile(self, vendor_id: UUID) -> dict[str, Any]:
        return self.vendor_tax_profiles.get(str(vendor_id), {})

    async def categorize_bank_transaction(
        self, transaction_id: UUID, account_id: UUID  # noqa: ARG002
    ) -> dict[str, Any]:
        return {"id": str(transaction_id), "categorized": True}

    async def match_bank_transaction(
        self, transaction_id: UUID, match_id: UUID, match_type: str  # noqa: ARG002
    ) -> dict[str, Any]:
        return {"id": str(transaction_id), "matched": True}

    async def get_profit_loss(self, period_start: str, period_end: str) -> dict[str, Any]:  # noqa: ARG002
        return self.profit_loss

    async def get_balance_sheet(self, as_of_date: str) -> dict[str, Any]:  # noqa: ARG002
        return self.balance_sheet

    async def get_cash_flow(self, period_start: str, period_end: str) -> dict[str, Any]:  # noqa: ARG002
        return self.cash_flow

    async def get_trial_balance(self, as_of_date: str | None = None) -> dict[str, Any]:  # noqa: ARG002
        return self.trial_balance

    async def get_ar_aging(self) -> dict[str, Any]:
        return self.ar_aging

    async def get_ap_aging(self) -> dict[str, Any]:
        return self.ap_aging

    async def get_account_balance(self, account_id: UUID) -> dict[str, Any]:  # noqa: ARG002
        return {"balance": "0.00"}

    async def create_journal_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        entry = {"id": str(uuid4()), **data}
        self.journal_entries.append(entry)
        return entry


def _accounts() -> list[dict[str, Any]]:
    return [
        {"id": "11111111-1111-1111-1111-111111111111", "name": "Supplies Expense", "account_type": "expense"},
        {"id": "22222222-2222-2222-2222-222222222222", "name": "Accrued Expenses", "account_type": "liability"},
        {"id": "33333333-3333-3333-3333-333333333333", "name": "Income Tax Expense", "account_type": "expense"},
        {"id": "44444444-4444-4444-4444-444444444444", "name": "Income Tax Payable", "account_type": "liability"},
        {"id": "55555555-5555-5555-5555-555555555555", "name": "Kitchen Equipment", "account_type": "asset"},
        {"id": "66666666-6666-6666-6666-666666666666", "name": "Accumulated Depreciation", "account_type": "asset"},
        {"id": "77777777-7777-7777-7777-777777777777", "name": "Depreciation Expense", "account_type": "expense"},
        {"id": "88888888-8888-8888-8888-888888888888", "name": "Food Inventory", "account_type": "asset"},
        {"id": "99999999-9999-9999-9999-999999999999", "name": "Cost of Goods Sold", "account_type": "expense"},
        {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "Income Summary", "account_type": "equity"},
        {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "name": "Retained Earnings", "account_type": "equity"},
    ]


def _trial_balance() -> dict[str, Any]:
    return {
        "total_debits": "100.00",
        "total_credits": "100.00",
        "accounts": [
            {"account_id": "55555555-5555-5555-5555-555555555555", "balance": "10000.00"},
            {"account_id": "88888888-8888-8888-8888-888888888888", "balance": "5000.00"},
        ],
    }


@pytest.mark.asyncio
async def test_month_end_close_creates_accrual_entry():
    api = FakeAPI(
        accounts=_accounts(),
        bills=[
            {"balance": "1200.00", "due_date": "2025-01-20"},
            {"balance": "800.00", "due_date": "2025-01-15"},
        ],
        bank_transactions=[{"id": "tx1"}, {"id": "tx2", "matched": True}],
        trial_balance=_trial_balance(),
        ar_aging={"over_90_days": "0"},
        ap_aging={"total": "1000"},
    )
    workflow = AccountingWorkflow(api_client=api)

    result = await workflow.run_period_end_workflow(
        business_key="tony",
        org_id=uuid4(),
        current_date=date(2025, 1, 3),
    )

    assert "month_end" in result
    assert len(api.journal_entries) == 1
    entry = api.journal_entries[0]
    assert entry["description"].startswith("Month-end accrual adjustment")
    assert entry["lines"][0]["entry_type"] == "debit"
    assert entry["lines"][0]["amount"] == "200.00"


@pytest.mark.asyncio
async def test_quarter_end_close_creates_tax_provision_entry():
    api = FakeAPI(
        accounts=_accounts(),
        profit_loss={"net_income": "10000.00"},
        balance_sheet={"assets": []},
        cash_flow={"cash": []},
    )
    workflow = AccountingWorkflow(api_client=api)

    result = await workflow.run_period_end_workflow(
        business_key="tony",
        org_id=uuid4(),
        current_date=date(2025, 4, 5),
    )

    assert "quarter_end" in result
    assert result["quarter_end"]["quarter"] == 1
    assert result["quarter_end"]["year"] == 2025
    assert len(api.journal_entries) == 1
    entry = api.journal_entries[0]
    assert entry["description"].startswith("Quarter-end tax provision Q1 2025")
    assert entry["lines"][0]["entry_type"] == "debit"
    assert entry["lines"][0]["amount"] == "2300.00"


@pytest.mark.asyncio
async def test_year_end_close_creates_entries():
    api = FakeAPI(
        accounts=_accounts(),
        trial_balance=_trial_balance(),
        profit_loss={"net_income": "20000.00"},
    )
    workflow = AccountingWorkflow(api_client=api)

    result = await workflow.run_period_end_workflow(
        business_key="tony",
        org_id=uuid4(),
        current_date=date(2025, 12, 31),
    )

    assert "year_end" in result
    assert len(api.journal_entries) == 3
    descriptions = [entry["description"] for entry in api.journal_entries]
    assert any(text.startswith("Year-end depreciation") for text in descriptions)
    assert any(text.startswith("Inventory adjustment") for text in descriptions)
    assert any(text.startswith("Closing entry 2025") for text in descriptions)


@pytest.mark.asyncio
async def test_year_end_reporting_counts_1099_bills():
    api = FakeAPI(
        vendors=[
            {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "display_name": "Vendor A"},
            {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "display_name": "Vendor B"},
        ],
        payments_made=[
            {"vendor_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "payment_date": "2024-06-15", "amount": "1200.00"},
            {"vendor_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "payment_date": "2024-07-01", "amount": "200.00"},
        ],
        vendor_tax_profiles={
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {"tax_form_on_file": False},
        },
    )
    workflow = AccountingWorkflow(api_client=api)

    result = await workflow.run_period_end_workflow(
        business_key="tony",
        org_id=uuid4(),
        current_date=date(2025, 1, 20),
    )

    assert result["year_end_reporting"]["tax_year"] == 2024
    assert result["year_end_reporting"]["vendors_over_threshold"] == 1
    assert result["year_end_reporting"]["vendors_missing_w9"] == 1
