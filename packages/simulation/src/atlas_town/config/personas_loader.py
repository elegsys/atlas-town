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
