"""Utilities for loading persona configuration from YAML files."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
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
def load_persona_cash_flow_settings() -> dict[str, dict[str, Any]]:
    """Load cash flow settings from persona YAML files."""
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    settings: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        cash_flow = data.get("cash_flow")

        if cash_flow is None:
            continue
        if not isinstance(cash_flow, dict):
            raise ValueError(f"{path.name}: cash_flow must be a mapping")

        normalized: dict[str, Any] = {}

        def _parse_decimal(value: Any, label: str, path_name: str) -> Decimal:
            try:
                return Decimal(str(value))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{path_name}: cash_flow.{label} must be numeric"
                ) from exc

        for key in ("min_cash", "reserve_target", "auto_draw_threshold"):
            if key in cash_flow and cash_flow[key] is not None:
                normalized[key] = _parse_decimal(cash_flow[key], key, path.name)

        reserve_by_month = cash_flow.get("reserve_by_month")
        if reserve_by_month is not None:
            if not isinstance(reserve_by_month, dict):
                raise ValueError(
                    f"{path.name}: cash_flow.reserve_by_month must be a mapping"
                )
            month_targets: dict[int, Decimal] = {}
            for raw_month, value in reserve_by_month.items():
                try:
                    month = int(raw_month)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path.name}: cash_flow.reserve_by_month invalid month {raw_month!r}"
                    ) from exc
                if not (1 <= month <= 12):
                    raise ValueError(
                        f"{path.name}: cash_flow.reserve_by_month month must be 1-12"
                    )
                month_targets[month] = _parse_decimal(
                    value, f"reserve_by_month[{month}]", path.name
                )
            normalized["reserve_by_month"] = month_targets

        essential_keywords = cash_flow.get("essential_vendor_keywords")
        if essential_keywords is not None:
            if not isinstance(essential_keywords, list):
                raise ValueError(
                    f"{path.name}: cash_flow.essential_vendor_keywords must be a list"
                )
            normalized["essential_vendor_keywords"] = [
                str(value).strip().lower() for value in essential_keywords if str(value).strip()
            ]

        defer_nonessential = cash_flow.get("defer_nonessential")
        if defer_nonessential is not None:
            normalized["defer_nonessential"] = bool(defer_nonessential)

        if normalized:
            settings[path.stem] = normalized

    return settings


@lru_cache
def load_persona_payment_behaviors() -> dict[str, dict[str, dict[str, Any]]]:
    """Load payment behavior configs from persona YAML files."""
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    behaviors: dict[str, dict[str, dict[str, Any]]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        payment_behavior = data.get("payment_behavior")

        if payment_behavior is None:
            continue
        if not isinstance(payment_behavior, dict):
            raise ValueError(f"{path.name}: payment_behavior must be a mapping")

        normalized: dict[str, dict[str, Any]] = {}
        for kind in ("invoice", "bill"):
            behavior = payment_behavior.get(kind)
            if behavior is None:
                continue
            if not isinstance(behavior, dict):
                raise ValueError(f"{path.name}: payment_behavior.{kind} must be a mapping")

            normalized_behavior: dict[str, Any] = {}
            for key in (
                "base_probability",
                "max_probability",
                "amount_ratio_min",
                "amount_ratio_max",
            ):
                if key in behavior:
                    try:
                        normalized_behavior[key] = float(behavior[key])
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"{path.name}: payment_behavior.{kind}.{key} must be a number"
                        ) from exc

            amount_thresholds = behavior.get("amount_thresholds")
            if amount_thresholds is not None:
                if not isinstance(amount_thresholds, dict):
                    raise ValueError(
                        f"{path.name}: payment_behavior.{kind}.amount_thresholds must be a mapping"
                    )
                normalized_thresholds: list[tuple[str, float]] = []
                for raw_threshold, bonus in amount_thresholds.items():
                    try:
                        threshold = str(raw_threshold)
                        bonus_value = float(bonus)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"{path.name}: payment_behavior.{kind}.amount_thresholds "
                            f"invalid entry {raw_threshold!r}:{bonus!r}"
                        ) from exc
                    normalized_thresholds.append((threshold, bonus_value))
                normalized_behavior["amount_thresholds"] = normalized_thresholds

            overdue_bonus = behavior.get("overdue_bonus")
            if overdue_bonus is not None:
                if not isinstance(overdue_bonus, dict):
                    raise ValueError(
                        f"{path.name}: payment_behavior.{kind}.overdue_bonus must be a mapping"
                    )
                normalized_overdue: list[tuple[int, float]] = []
                for raw_days, bonus in overdue_bonus.items():
                    try:
                        days_value = int(raw_days)
                        bonus_value = float(bonus)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"{path.name}: payment_behavior.{kind}.overdue_bonus "
                            f"invalid entry {raw_days!r}:{bonus!r}"
                        ) from exc
                    normalized_overdue.append((days_value, bonus_value))
                normalized_behavior["overdue_bonus"] = normalized_overdue

            if normalized_behavior:
                normalized[kind] = normalized_behavior

        if normalized:
            behaviors[path.stem] = normalized

    return behaviors


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
def load_persona_financing_configs() -> dict[str, dict[str, Any]]:
    """Load financing configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to financing config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    financing_by_persona: dict[str, dict[str, Any]] = {}

    def normalize_entries(
        value: Any, path: Path, key: str
    ) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            entries = [value]
        elif isinstance(value, list):
            entries = value
        else:
            raise ValueError(f"{path.name}: financing.{key} must be a mapping or list")

        normalized_entries: list[dict[str, Any]] = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"{path.name}: financing.{key}[{idx}] must be a mapping"
                )
            normalized_entries.append(entry)
        return normalized_entries

    def parse_date_value(
        raw_value: Any, path: Path, label: str
    ) -> date | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, date):
            return raw_value
        if not isinstance(raw_value, str):
            raise ValueError(f"{path.name}: {label} must be an ISO date string")
        try:
            return date.fromisoformat(raw_value)
        except ValueError as exc:
            raise ValueError(f"{path.name}: invalid {label}") from exc

    def normalize_rate_adjustments(
        raw_value: Any, path: Path, label: str
    ) -> list[dict[str, Any]]:
        if raw_value is None:
            return []
        if not isinstance(raw_value, list):
            raise ValueError(f"{path.name}: {label} must be a list")
        adjustments: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_value):
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: {label}[{idx}] must be a mapping")
            effective_date = parse_date_value(
                item.get("effective_date"), path, f"{label}[{idx}].effective_date"
            )
            if effective_date is None:
                raise ValueError(
                    f"{path.name}: {label}[{idx}] missing effective_date"
                )
            if "rate" not in item:
                raise ValueError(f"{path.name}: {label}[{idx}] missing rate")
            adjustments.append(
                {
                    "effective_date": effective_date,
                    "rate": item.get("rate"),
                }
            )
        return adjustments

    def normalize_balance_events(
        raw_value: Any, path: Path, label: str
    ) -> list[dict[str, Any]]:
        if raw_value is None:
            return []
        if not isinstance(raw_value, list):
            raise ValueError(f"{path.name}: {label} must be a list")
        events: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_value):
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: {label}[{idx}] must be a mapping")
            effective_date = parse_date_value(
                item.get("effective_date"), path, f"{label}[{idx}].effective_date"
            )
            if effective_date is None:
                raise ValueError(
                    f"{path.name}: {label}[{idx}] missing effective_date"
                )
            if "balance" not in item:
                raise ValueError(f"{path.name}: {label}[{idx}] missing balance")
            events.append(
                {
                    "effective_date": effective_date,
                    "balance": item.get("balance"),
                }
            )
        return events

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        financing = data.get("financing")

        if financing is None:
            continue
        if not isinstance(financing, dict):
            raise ValueError(f"{path.name}: financing must be a mapping")

        term_loans = normalize_entries(
            financing.get("term_loan", financing.get("term_loans")),
            path,
            "term_loan",
        )
        lines_of_credit = normalize_entries(
            financing.get("line_of_credit", financing.get("lines_of_credit")),
            path,
            "line_of_credit",
        )
        equipment_financing = normalize_entries(
            financing.get("equipment_financing"), path, "equipment_financing"
        )

        normalized_term_loans: list[dict[str, Any]] = []
        for idx, loan in enumerate(term_loans):
            principal = loan.get("principal")
            rate = loan.get("rate")
            term_months = loan.get("term_months")
            if principal is None or rate is None or term_months is None:
                raise ValueError(
                    f"{path.name}: financing.term_loan[{idx}] missing principal/rate/term_months"
                )

            normalized_term_loans.append(
                {
                    "name": loan.get("name"),
                    "principal": principal,
                    "rate": rate,
                    "term_months": term_months,
                    "payment_day": loan.get("payment_day", 1),
                    "lender": loan.get("lender"),
                    "start_date": parse_date_value(
                        loan.get("start_date"), path, "financing.term_loan.start_date"
                    ),
                    "rate_adjustments": normalize_rate_adjustments(
                        loan.get("rate_adjustments"),
                        path,
                        "financing.term_loan.rate_adjustments",
                    ),
                }
            )

        normalized_lines: list[dict[str, Any]] = []
        for idx, line in enumerate(lines_of_credit):
            balance = line.get("balance")
            rate = line.get("rate")
            if balance is None or rate is None:
                raise ValueError(
                    f"{path.name}: financing.line_of_credit[{idx}] missing balance/rate"
                )
            normalized_lines.append(
                {
                    "name": line.get("name"),
                    "balance": balance,
                    "rate": rate,
                    "limit": line.get("limit"),
                    "auto_draw_threshold": line.get("auto_draw_threshold"),
                    "billing_day": line.get("billing_day", 1),
                    "lender": line.get("lender"),
                    "start_date": parse_date_value(
                        line.get("start_date"),
                        path,
                        "financing.line_of_credit.start_date",
                    ),
                    "rate_adjustments": normalize_rate_adjustments(
                        line.get("rate_adjustments"),
                        path,
                        "financing.line_of_credit.rate_adjustments",
                    ),
                    "balance_events": normalize_balance_events(
                        line.get("balance_events"),
                        path,
                        "financing.line_of_credit.balance_events",
                    ),
                }
            )

        normalized_equipment: list[dict[str, Any]] = []
        for idx, equip in enumerate(equipment_financing):
            principal = equip.get("principal")
            rate = equip.get("rate")
            term_months = equip.get("term_months")
            if principal is None or rate is None or term_months is None:
                raise ValueError(
                    f"{path.name}: financing.equipment_financing[{idx}] "
                    "missing principal/rate/term_months"
                )
            normalized_equipment.append(
                {
                    "name": equip.get("name"),
                    "principal": principal,
                    "rate": rate,
                    "term_months": term_months,
                    "payment_day": equip.get("payment_day", 1),
                    "lender": equip.get("lender"),
                    "start_date": parse_date_value(
                        equip.get("start_date"),
                        path,
                        "financing.equipment_financing.start_date",
                    ),
                    "rate_adjustments": normalize_rate_adjustments(
                        equip.get("rate_adjustments"),
                        path,
                        "financing.equipment_financing.rate_adjustments",
                    ),
                    "decision": equip.get("decision", "auto"),
                    "decision_rate_threshold": equip.get("decision_rate_threshold"),
                    "decision_principal_threshold": equip.get("decision_principal_threshold"),
                    "lease_probability": equip.get("lease_probability"),
                    "purchase_probability": equip.get("purchase_probability"),
                }
            )

        if normalized_term_loans or normalized_lines or normalized_equipment:
            financing_by_persona[path.stem] = {
                "term_loans": normalized_term_loans,
                "lines_of_credit": normalized_lines,
                "equipment_financing": normalized_equipment,
            }

    return financing_by_persona


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
def load_persona_year_end_configs() -> dict[str, dict[str, Any]]:
    """Load year-end configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to year-end config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    year_end_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        year_end = data.get("year_end")

        if year_end is None:
            continue
        if not isinstance(year_end, dict):
            raise ValueError(f"{path.name}: year_end must be a mapping")

        year_end_by_persona[path.stem] = {
            "accrual_rate": year_end.get("accrual_rate"),
            "tax_provision_rate": year_end.get("tax_provision_rate"),
            "depreciation_rate": year_end.get("depreciation_rate"),
            "inventory_shrink_rate": year_end.get("inventory_shrink_rate"),
            "fixed_asset_keywords": year_end.get("fixed_asset_keywords"),
            "accumulated_dep_keywords": year_end.get("accumulated_dep_keywords"),
            "depreciation_expense_keywords": year_end.get("depreciation_expense_keywords"),
            "inventory_keywords": year_end.get("inventory_keywords"),
            "cogs_keywords": year_end.get("cogs_keywords"),
            "tax_expense_keywords": year_end.get("tax_expense_keywords"),
            "tax_payable_keywords": year_end.get("tax_payable_keywords"),
            "retained_earnings_keywords": year_end.get("retained_earnings_keywords"),
            "income_summary_keywords": year_end.get("income_summary_keywords"),
        }

    return year_end_by_persona


@lru_cache
def load_persona_inventory_configs() -> dict[str, dict[str, Any]]:
    """Load inventory configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to inventory config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    inventory_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        inventory = data.get("inventory")
        policy = data.get("inventory_policy")

        if inventory is None:
            continue

        items: list[dict[str, Any]] = []
        if isinstance(inventory, list):
            items = inventory
        elif isinstance(inventory, dict):
            raw_items = inventory.get("items")
            if raw_items is None:
                raw_items = []
            if not isinstance(raw_items, list):
                raise ValueError(f"{path.name}: inventory.items must be a list")
            items = raw_items
            nested_policy = inventory.get("policy")
            if isinstance(nested_policy, dict):
                policy = {**nested_policy, **(policy or {})}
        else:
            raise ValueError(f"{path.name}: inventory must be a list or mapping")

        if policy is not None and not isinstance(policy, dict):
            raise ValueError(f"{path.name}: inventory_policy must be a mapping")

        inventory_by_persona[path.stem] = {
            "items": items,
            "policy": policy or {},
        }

    return inventory_by_persona


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


@lru_cache
def load_persona_multi_currency_configs() -> dict[str, dict[str, Any]]:
    """Load multi-currency configs from persona YAML files.

    Returns:
        Mapping of persona key (filename stem) to multi-currency config dict.
    """
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return {}

    multi_currency_by_persona: dict[str, dict[str, Any]] = {}

    for path in sorted(personas_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        multi_currency = data.get("multi_currency")

        if multi_currency is None:
            continue
        if not isinstance(multi_currency, dict):
            raise ValueError(f"{path.name}: multi_currency must be a mapping")

        enabled = bool(multi_currency.get("enabled", False))
        if not enabled:
            continue

        base_currency = str(multi_currency.get("base_currency", "USD")).upper()
        revaluation_enabled = bool(multi_currency.get("revaluation_enabled", True))
        fx_gain_loss_account_name = str(
            multi_currency.get("fx_gain_loss_account_name", "Foreign Exchange Gain/Loss")
        )

        clients_raw = multi_currency.get("clients", [])
        if not isinstance(clients_raw, list):
            raise ValueError(f"{path.name}: multi_currency.clients must be a list")

        normalized_clients: list[dict[str, Any]] = []
        for idx, client in enumerate(clients_raw):
            if not isinstance(client, dict):
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] must be a mapping"
                )

            name = client.get("name")
            currency = client.get("currency")
            if not name or not currency:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] missing name/currency"
                )

            base_rate = client.get("base_rate")
            if base_rate is None:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] missing base_rate"
                )
            try:
                base_rate_decimal = Decimal(str(base_rate))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] invalid base_rate"
                ) from exc

            volatility = client.get("volatility", 0.005)
            try:
                volatility_decimal = Decimal(str(volatility))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] invalid volatility"
                ) from exc

            invoice_probability = client.get("invoice_probability", 0.1)
            try:
                invoice_prob_float = float(invoice_probability)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] invalid invoice_probability"
                ) from exc

            min_amount = client.get("min_amount", 1000)
            max_amount = client.get("max_amount", 10000)
            try:
                min_amount_decimal = Decimal(str(min_amount))
                max_amount_decimal = Decimal(str(max_amount))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] invalid min_amount/max_amount"
                ) from exc

            payment_terms_days = client.get("payment_terms_days", 30)
            if not isinstance(payment_terms_days, int) or payment_terms_days < 1:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] payment_terms_days must be >= 1"
                )

            payment_reliability = client.get("payment_reliability", 0.85)
            try:
                payment_rel_float = float(payment_reliability)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{path.name}: multi_currency.clients[{idx}] invalid payment_reliability"
                ) from exc

            normalized_clients.append({
                "name": str(name),
                "currency": str(currency).upper(),
                "base_rate": base_rate_decimal,
                "volatility": volatility_decimal,
                "invoice_probability": invoice_prob_float,
                "min_amount": min_amount_decimal,
                "max_amount": max_amount_decimal,
                "payment_terms_days": payment_terms_days,
                "payment_reliability": payment_rel_float,
            })

        if normalized_clients:
            multi_currency_by_persona[path.stem] = {
                "enabled": True,
                "base_currency": base_currency,
                "revaluation_enabled": revaluation_enabled,
                "fx_gain_loss_account_name": fx_gain_loss_account_name,
                "clients": normalized_clients,
            }

    return multi_currency_by_persona

