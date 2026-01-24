"""Tests for payroll transaction generation."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from atlas_town.transactions import (
    EmployeeSpec,
    PayrollConfig,
    PayrollGenerator,
    TransactionType,
)


def _vendor(name: str) -> dict[str, str]:
    return {"id": str(uuid4()), "display_name": name}


def test_payroll_run_generates_bill_with_hint():
    employees = [
        EmployeeSpec(
            role="Staff",
            count=2,
            pay_rate=Decimal("20.00"),
            hours_per_week=Decimal("30"),
        )
    ]
    payroll_vendor = "Acme Payroll"
    config = PayrollConfig(
        frequency="bi-weekly",
        pay_day="friday",
        payroll_vendor=payroll_vendor,
        tax_authority="IRS Payroll Taxes",
    )
    vendors = [_vendor(payroll_vendor)]

    generator = PayrollGenerator({"biz": employees}, {"biz": config})
    pay_date = date(2024, 1, 5)  # Friday

    transactions = generator.get_due_transactions("biz", pay_date, vendors)

    assert len(transactions) == 1
    tx = transactions[0]
    assert tx.transaction_type == TransactionType.BILL
    assert str(tx.vendor_id) == vendors[0]["id"]
    assert tx.metadata is not None
    assert tx.metadata["expense_account_hint"] == "payroll"
    assert Decimal(tx.metadata["payroll_gross"]) == tx.amount


def test_payroll_tax_deposit_semiweekly_schedule():
    employees = [
        EmployeeSpec(
            role="Crew",
            count=2,
            pay_rate=Decimal("50.00"),
            hours_per_week=Decimal("60"),
        )
    ]
    payroll_vendor = "Acme Payroll"
    tax_vendor = "IRS Payroll Taxes"
    config = PayrollConfig(
        frequency="weekly",
        pay_day="friday",
        payroll_vendor=payroll_vendor,
        tax_authority=tax_vendor,
    )
    vendors = [_vendor(payroll_vendor), _vendor(tax_vendor)]

    generator = PayrollGenerator({"biz": employees}, {"biz": config})
    pay_date = date(2024, 1, 5)  # Friday
    gross = Decimal("6000.00")
    taxes = (gross * Decimal("0.1965")).quantize(Decimal("0.01"))

    payroll_txs = generator.get_due_transactions("biz", pay_date, vendors)
    assert any(tx.description.startswith("Payroll") for tx in payroll_txs)

    due_date = pay_date + timedelta(days=3)
    tax_txs = generator.get_due_transactions("biz", due_date, vendors)

    assert len(tax_txs) == 1
    tax_tx = tax_txs[0]
    assert tax_tx.transaction_type == TransactionType.BILL
    assert tax_tx.description == "Payroll tax deposit"
    assert tax_tx.amount == taxes
    assert str(tax_tx.vendor_id) == vendors[1]["id"]
    assert tax_tx.metadata is not None
    assert tax_tx.metadata["expense_account_hint"] == "payroll tax"


def test_payroll_tax_deposit_monthly_schedule():
    employees = [
        EmployeeSpec(
            role="Assistant",
            count=1,
            pay_rate=Decimal("20.00"),
            hours_per_week=Decimal("20"),
        )
    ]
    payroll_vendor = "Acme Payroll"
    tax_vendor = "IRS Payroll Taxes"
    config = PayrollConfig(
        frequency="weekly",
        pay_day="friday",
        payroll_vendor=payroll_vendor,
        tax_authority=tax_vendor,
    )
    vendors = [_vendor(payroll_vendor), _vendor(tax_vendor)]

    generator = PayrollGenerator({"biz": employees}, {"biz": config})
    pay_date = date(2024, 1, 5)  # Friday

    payroll_txs = generator.get_due_transactions("biz", pay_date, vendors)
    assert any(tx.description.startswith("Payroll") for tx in payroll_txs)

    due_date = date(2024, 2, 15)
    tax_txs = generator.get_due_transactions("biz", due_date, vendors)

    assert len(tax_txs) == 1
    tax_tx = tax_txs[0]
    assert tax_tx.description == "Payroll tax deposit"
    assert tax_tx.metadata is not None
    assert tax_tx.metadata["expense_account_hint"] == "payroll tax"
