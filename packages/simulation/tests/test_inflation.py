"""Tests for inflation adjustments in transactions."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from atlas_town.b2b import B2BCoordinator
from atlas_town.economics import InflationModel
from atlas_town.orchestrator import OrganizationContext
from atlas_town.transactions import (
    EmployeeSpec,
    PayrollConfig,
    PayrollGenerator,
    TransactionGenerator,
    TransactionPattern,
    TransactionType,
)


def _vendor(name: str) -> dict[str, str]:
    return {"id": str(uuid4()), "display_name": name}


def test_inflation_model_applies_after_start_date():
    model = InflationModel(annual_rate=Decimal("0.10"), start_date=date(2023, 1, 1))
    base = Decimal("100.00")

    assert model.apply(base, date(2022, 12, 31)) == base
    assert model.apply(base, date(2024, 1, 1)) == Decimal("110.00")


def test_transaction_generator_applies_inflation_to_amounts():
    model = InflationModel(annual_rate=Decimal("0.10"), start_date=date(2023, 1, 1))
    generator = TransactionGenerator(seed=1, inflation=model)

    pattern = TransactionPattern(
        transaction_type=TransactionType.INVOICE,
        description_template="Fixed price",
        min_amount=Decimal("100.00"),
        max_amount=Decimal("100.00"),
        probability=1.0,
    )

    amount = generator._generate_amount(pattern, date(2024, 1, 1))
    assert amount == Decimal("110.00")


def test_payroll_inflation_adjusts_gross_pay():
    model = InflationModel(annual_rate=Decimal("0.10"), start_date=date(2023, 1, 1))
    employees = [
        EmployeeSpec(
            role="Staff",
            count=1,
            pay_rate=Decimal("100.00"),
            hours_per_week=Decimal("10"),
        )
    ]
    config = PayrollConfig(
        frequency="monthly",
        pay_day=1,
        payroll_vendor="Acme Payroll",
        tax_authority="IRS Payroll Taxes",
    )
    vendors = [_vendor("Acme Payroll")]

    generator = PayrollGenerator(
        {"biz": employees},
        {"biz": config},
        inflation=model,
    )
    pay_date = date(2024, 1, 1)
    transactions = generator.get_due_transactions("biz", pay_date, vendors)

    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("4400.00")


def test_b2b_amounts_are_inflated():
    model = InflationModel(annual_rate=Decimal("0.10"), start_date=date(2023, 1, 1))
    seller = OrganizationContext(
        id=uuid4(),
        name="Craig's Landscaping",
        industry="landscaping",
        owner_key="craig",
    )
    buyer = OrganizationContext(
        id=uuid4(),
        name="Tony's Pizzeria",
        industry="restaurant",
        owner_key="tony",
    )
    orgs = {"craig": seller, "tony": buyer}
    configs = {
        "craig": {
            "enabled": True,
            "counterparties": [
                {
                    "org_key": "tony",
                    "relationship": "vendor",
                    "frequency": "monthly",
                    "day_of_month": 1,
                    "amount_min": 100,
                    "amount_max": 100,
                }
            ],
        }
    }

    coordinator = B2BCoordinator(
        orgs_by_key=orgs,
        configs=configs,
        org_reference={},
        inflation=model,
    )

    planned = coordinator.plan_pairs(
        date(2024, 1, 1),
        customers_by_org={"craig": [], "tony": []},
    )

    assert planned
    assert planned[0].amount == Decimal("110.00")
