"""Utilities for loading persona configuration from YAML files."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

WEEKDAY_NAME_TO_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def _normalize_day_key(day_key: Any) -> int | None:
    """Normalize a day key from YAML into a weekday index (0=Mon..6=Sun)."""
    if isinstance(day_key, int):
        return day_key
    if isinstance(day_key, str):
        return WEEKDAY_NAME_TO_INDEX.get(day_key.strip().lower())
    return None


@lru_cache
def load_persona_day_patterns() -> dict[str, dict[int, float]]:
    """Load day-of-week multipliers from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to weekday multiplier map.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    patterns: dict[str, dict[int, float]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        day_patterns = data.get("day_patterns")

        if day_patterns is None:
            continue
        if not isinstance(day_patterns, dict):
            raise ValueError(f"{path.name}: day_patterns must be a mapping")

        normalized: dict[int, float] = {}
        for day_key, value in day_patterns.items():
            day_index = _normalize_day_key(day_key)
            if day_index is None or not (0 <= day_index <= 6):
                raise ValueError(f"{path.name}: invalid day key {day_key!r}")

            try:
                mult = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{path.name}: invalid multiplier for {day_key!r}: {value!r}"
                ) from exc

            if mult < 0:
                raise ValueError(
                    f"{path.name}: negative multiplier for {day_key!r}: {mult}"
                )

            normalized[day_index] = mult

        if normalized:
            patterns[path.stem] = normalized

    return patterns


@lru_cache
def load_persona_recurring_transactions() -> dict[str, list[dict[str, Any]]]:
    """Load recurring transaction configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to recurring transaction configs.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    recurring_by_persona: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        recurring = data.get("recurring_transactions")

        if recurring is None:
            continue
        if not isinstance(recurring, list):
            raise ValueError(f"{path.name}: recurring_transactions must be a list")

        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(recurring):
            if not isinstance(item, dict):
                raise ValueError(
                    f"{path.name}: recurring_transactions[{idx}] must be a mapping"
                )

            name = item.get("name")
            vendor = item.get("vendor")
            amount = item.get("amount")
            category = item.get("category")
            day_of_month = item.get("day_of_month")
            anniversary_raw = item.get("anniversary_date")
            interval_months = item.get("interval_months", 1)

            if not name or not vendor or amount is None:
                raise ValueError(
                    f"{path.name}: recurring_transactions[{idx}] missing name/vendor/amount"
                )

            if day_of_month is not None and (
                not isinstance(day_of_month, int) or not (1 <= day_of_month <= 31)
            ):
                raise ValueError(
                    f"{path.name}: recurring_transactions[{idx}] day_of_month must be 1-31"
                )

            anniversary_date = None
            if anniversary_raw is not None:
                if not isinstance(anniversary_raw, str):
                    raise ValueError(
                        f"{path.name}: recurring_transactions[{idx}] "
                        "anniversary_date must be string"
                    )
                try:
                    anniversary_date = date.fromisoformat(anniversary_raw)
                except ValueError as exc:
                    raise ValueError(
                        f"{path.name}: recurring_transactions[{idx}] invalid anniversary_date"
                    ) from exc

            if day_of_month is None and anniversary_date:
                day_of_month = anniversary_date.day

            if day_of_month is None and anniversary_date is None:
                raise ValueError(
                    f"{path.name}: recurring_transactions[{idx}] needs "
                    "day_of_month or anniversary_date"
                )

            if not isinstance(interval_months, int) or interval_months < 1:
                raise ValueError(
                    f"{path.name}: recurring_transactions[{idx}] interval_months must be >= 1"
                )

            normalized.append(
                {
                    "name": str(name),
                    "vendor": str(vendor),
                    "amount": amount,
                    "category": str(category) if category is not None else None,
                    "day_of_month": day_of_month,
                    "anniversary_date": anniversary_date,
                    "interval_months": interval_months,
                }
            )

        if normalized:
            recurring_by_persona[path.stem] = normalized

    return recurring_by_persona


@lru_cache
def load_persona_employees() -> dict[str, list[dict[str, Any]]]:
    """Load employee configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to employee config list.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    employees_by_persona: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        employees = data.get("employees")

        if employees is None:
            continue
        if not isinstance(employees, list):
            raise ValueError(f"{path.name}: employees must be a list")

        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(employees):
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: employees[{idx}] must be a mapping")

            role = item.get("role")
            count = item.get("count", 1)
            pay_rate = item.get("pay_rate")
            hours = item.get("hours_per_week")

            if not role:
                raise ValueError(f"{path.name}: employees[{idx}] missing role")
            if pay_rate is None or hours is None:
                raise ValueError(
                    f"{path.name}: employees[{idx}] missing pay_rate/hours_per_week"
                )
            if not isinstance(count, int) or count < 1:
                raise ValueError(
                    f"{path.name}: employees[{idx}] count must be >= 1"
                )

            normalized.append(
                {
                    "role": str(role),
                    "count": count,
                    "pay_rate": pay_rate,
                    "hours_per_week": hours,
                }
            )

        if normalized:
            employees_by_persona[path.stem] = normalized

    return employees_by_persona


@lru_cache
def load_persona_industries() -> dict[str, str]:
    """Load persona industries from YAML files.

    Returns:
        Mapping of persona key (filename stem) to industry.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    industries_by_persona: dict[str, str] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        industry = data.get("industry")
        if not industry:
            continue
        industries_by_persona[path.stem] = str(industry)

    return industries_by_persona


@lru_cache
def load_persona_payroll_configs() -> dict[str, dict[str, Any]]:
    """Load payroll configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to payroll config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    payroll_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        payroll = data.get("payroll")

        if payroll is None:
            continue
        if not isinstance(payroll, dict):
            raise ValueError(f"{path.name}: payroll must be a mapping")

        frequency = payroll.get("frequency", "bi-weekly")
        pay_day = payroll.get("pay_day", "friday")
        payroll_vendor = payroll.get("payroll_vendor")
        tax_authority = payroll.get("tax_authority")

        payroll_by_persona[path.stem] = {
            "frequency": str(frequency),
            "pay_day": pay_day,
            "payroll_vendor": str(payroll_vendor)
            if payroll_vendor is not None
            else None,
            "tax_authority": str(tax_authority) if tax_authority is not None else None,
        }

    return payroll_by_persona


@lru_cache
def load_persona_tax_configs() -> dict[str, dict[str, Any]]:
    """Load quarterly tax configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to tax config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    tax_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        tax_config = data.get("tax_config")

        if tax_config is None:
            continue
        if not isinstance(tax_config, dict):
            raise ValueError(f"{path.name}: tax_config must be a mapping")

        tax_by_persona[path.stem] = {
            "entity_type": str(tax_config.get("entity_type", "sole_proprietor")),
            "estimated_annual_income": tax_config.get("estimated_annual_income"),
            "estimated_tax_rate": tax_config.get("estimated_tax_rate"),
            "tax_vendor": tax_config.get("tax_vendor"),
        }

    return tax_by_persona


@lru_cache
def load_persona_sales_tax_configs() -> dict[str, dict[str, Any]]:
    """Load sales tax configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to sales tax config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    sales_tax_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        tax_config = data.get("sales_tax")

        if tax_config is None:
            continue
        if not isinstance(tax_config, dict):
            raise ValueError(f"{path.name}: sales_tax must be a mapping")

        collect_on = tax_config.get("collect_on")
        if collect_on is None:
            collect_on = []
        if not isinstance(collect_on, list):
            raise ValueError(f"{path.name}: sales_tax.collect_on must be a list")

        raw_tax_type = tax_config.get("tax_type", "sales_tax")
        tax_type = str(raw_tax_type).strip().lower() if raw_tax_type is not None else "sales_tax"
        if tax_type == "sales":
            tax_type = "sales_tax"

        sales_tax_by_persona[path.stem] = {
            "enabled": bool(tax_config.get("enabled", False)),
            "rate": tax_config.get("rate"),
            "jurisdiction": tax_config.get("jurisdiction"),
            "tax_type": tax_type,
            "name": tax_config.get("name"),
            "collect_on": collect_on,
            "tax_authority": tax_config.get("tax_authority"),
            "remit_day": tax_config.get("remit_day", 1),
        }

    return sales_tax_by_persona


@lru_cache
def load_persona_b2b_configs() -> dict[str, dict[str, Any]]:
    """Load B2B pairing configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to B2B config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    b2b_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        b2b_config = data.get("b2b_config")

        if b2b_config is None:
            continue
        if not isinstance(b2b_config, dict):
            raise ValueError(f"{path.name}: b2b_config must be a mapping")

        enabled = bool(b2b_config.get("enabled", True))
        counterparties = b2b_config.get("counterparties", [])
        if counterparties is None:
            counterparties = []
        if not isinstance(counterparties, list):
            raise ValueError(f"{path.name}: b2b_config.counterparties must be a list")

        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(counterparties):
            if not isinstance(item, dict):
                raise ValueError(
                    f"{path.name}: b2b_config.counterparties[{idx}] must be a mapping"
                )
            org_key = item.get("org_key")
            if not org_key:
                raise ValueError(
                    f"{path.name}: b2b_config.counterparties[{idx}] missing org_key"
                )

            day_of_month = item.get("day_of_month")
            if day_of_month is not None and (
                not isinstance(day_of_month, int) or not (1 <= day_of_month <= 31)
            ):
                raise ValueError(
                    f"{path.name}: b2b_config.counterparties[{idx}] day_of_month must be 1-31"
                )

            normalized.append(
                {
                    "org_key": str(org_key),
                    "relationship": str(item.get("relationship", "auto")),
                    "frequency": str(item.get("frequency", "monthly")),
                    "day_of_month": day_of_month,
                    "amount_min": item.get("amount_min"),
                    "amount_max": item.get("amount_max"),
                    "amount": item.get("amount"),
                    "description": item.get("description"),
                    "invoice_terms_days": item.get("invoice_terms_days", 30),
                    "payment_flow": item.get("payment_flow", "same_day"),
                }
            )

        b2b_by_persona[path.stem] = {
            "enabled": enabled,
            "counterparties": normalized,
        }

    return b2b_by_persona
