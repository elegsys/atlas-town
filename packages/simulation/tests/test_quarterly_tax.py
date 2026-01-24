"""Tests for quarterly estimated tax scheduling."""

from datetime import date
from decimal import Decimal

from atlas_town.transactions import QuarterlyTaxConfig, QuarterlyTaxScheduler


def _config() -> QuarterlyTaxConfig:
    return QuarterlyTaxConfig(
        entity_type="sole_proprietor",
        estimated_annual_income=Decimal("120000"),
        estimated_tax_rate=Decimal("0.25"),
        tax_vendor="IRS Estimated Taxes",
    )


def test_quarterly_tax_actions_create():
    scheduler = QuarterlyTaxScheduler({"craig": _config()})

    actions = scheduler.get_actions("craig", date(2025, 4, 1))

    assert len(actions) == 1
    action = actions[0]
    assert action.action == "create"
    assert action.tax_year == 2025
    assert action.quarter == 1
    assert action.due_date == date(2025, 4, 15)
    assert action.estimated_income == Decimal("30000.00")
    assert action.estimated_tax == Decimal("7500.00")


def test_quarterly_tax_actions_pay():
    scheduler = QuarterlyTaxScheduler({"craig": _config()})

    actions = scheduler.get_actions("craig", date(2025, 4, 15))

    assert len(actions) == 1
    action = actions[0]
    assert action.action == "pay"
    assert action.tax_year == 2025
    assert action.quarter == 1
    assert action.due_date == date(2025, 4, 15)


def test_quarterly_tax_actions_q4_previous_year():
    scheduler = QuarterlyTaxScheduler({"craig": _config()})

    actions = scheduler.get_actions("craig", date(2025, 1, 1))

    assert len(actions) == 1
    action = actions[0]
    assert action.action == "create"
    assert action.tax_year == 2024
    assert action.quarter == 4
    assert action.due_date == date(2025, 1, 15)


def test_quarterly_tax_actions_suppressed_after_mark():
    scheduler = QuarterlyTaxScheduler({"craig": _config()})

    actions = scheduler.get_actions("craig", date(2025, 4, 1))
    assert actions
    action = actions[0]
    scheduler.mark_created("craig", action.tax_year, action.quarter)

    again = scheduler.get_actions("craig", date(2025, 4, 1))
    assert again == []
