"""Tests for financing interest generation."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import atlas_town.transactions as transactions


def test_term_loan_interest_with_rate_adjustment(monkeypatch):
    vendor_id = uuid4()

    def fake_financing_configs():
        return {
            "testbiz": {
                "term_loans": [
                    {
                        "name": "SBA Loan",
                        "principal": 10000,
                        "rate": 0.06,
                        "term_months": 12,
                        "payment_day": 15,
                        "lender": "Acme Bank",
                        "start_date": date(2024, 1, 1),
                        "rate_adjustments": [
                            {"effective_date": date(2024, 2, 1), "rate": 0.08}
                        ],
                    }
                ],
                "lines_of_credit": [],
                "equipment_financing": [],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_financing_configs", fake_financing_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Acme Bank"}]

    jan_tx = generator.generate_financing_transactions(
        "testbiz", date(2024, 1, 15), vendors
    )
    assert len(jan_tx) == 1
    expected_jan = (Decimal("10000") * Decimal("0.06") / Decimal("12")).quantize(
        Decimal("0.01")
    )
    assert jan_tx[0].amount == expected_jan

    feb_tx = generator.generate_financing_transactions(
        "testbiz", date(2024, 2, 15), vendors
    )
    assert len(feb_tx) == 1
    expected_feb = (Decimal("10000") * Decimal("0.08") / Decimal("12")).quantize(
        Decimal("0.01")
    )
    assert feb_tx[0].amount == expected_feb

    repeat = generator.generate_financing_transactions(
        "testbiz", date(2024, 2, 15), vendors
    )
    assert repeat == []


def test_loc_interest_accrues_and_bills_previous_month(monkeypatch):
    vendor_id = uuid4()

    def fake_financing_configs():
        return {
            "testbiz": {
                "term_loans": [],
                "lines_of_credit": [
                    {
                        "name": "Operating LOC",
                        "balance": 12000,
                        "rate": 0.12,
                        "billing_day": 5,
                        "lender": "Acme Bank",
                        "start_date": date(2024, 1, 1),
                        "rate_adjustments": [],
                        "balance_events": [],
                    }
                ],
                "equipment_financing": [],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_financing_configs", fake_financing_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Acme Bank"}]

    for day in range(1, 32):
        generator.generate_financing_transactions("testbiz", date(2024, 1, day), vendors)
    for day in range(1, 5):
        generator.generate_financing_transactions("testbiz", date(2024, 2, day), vendors)

    feb_bill = generator.generate_financing_transactions(
        "testbiz", date(2024, 2, 5), vendors
    )
    assert len(feb_bill) == 1
    expected_interest = (
        Decimal("12000")
        * Decimal("0.12")
        / Decimal("365")
        * Decimal("31")
    ).quantize(Decimal("0.01"))
    assert feb_bill[0].amount == expected_interest

    repeat = generator.generate_financing_transactions(
        "testbiz", date(2024, 2, 5), vendors
    )
    assert repeat == []
