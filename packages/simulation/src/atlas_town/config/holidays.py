"""Holiday and special event calendar loader."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from atlas_town.config.personas_loader import WEEKDAY_NAME_TO_INDEX

MONTH_NAME_TO_INDEX = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

ORDINAL_NAME_TO_INDEX = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
}

RuleType = Literal["fixed", "nth_weekday", "last_weekday", "range"]


@dataclass(frozen=True)
class HolidayRule:
    """Date matching rule for a holiday or event."""

    rule_type: RuleType
    month: int | None = None
    day: int | None = None
    weekday: int | None = None
    nth: int | None = None
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None

    def matches(self, target_date: date) -> bool:
        """Return True if the rule matches the target date."""
        if self.rule_type == "fixed":
            return (
                self.month == target_date.month and self.day == target_date.day
            )

        if self.rule_type == "nth_weekday":
            if self.month is None or self.weekday is None or self.nth is None:
                return False
            if target_date.month != self.month:
                return False
            match_day = _nth_weekday_of_month(
                target_date.year, self.month, self.weekday, self.nth
            )
            return match_day == target_date.day

        if self.rule_type == "last_weekday":
            if self.month is None or self.weekday is None:
                return False
            if target_date.month != self.month:
                return False
            match_day = _last_weekday_of_month(
                target_date.year, self.month, self.weekday
            )
            return match_day == target_date.day

        if self.rule_type == "range":
            if self.start is None or self.end is None:
                return False
            start_month, start_day = self.start
            end_month, end_day = self.end
            start_date = date(target_date.year, start_month, start_day)
            end_date = date(target_date.year, end_month, end_day)
            if end_date >= start_date:
                return start_date <= target_date <= end_date
            return target_date >= start_date or target_date <= end_date

        return False


@dataclass(frozen=True)
class HolidayDefinition:
    """Holiday or event configuration."""

    name: str
    rule: HolidayRule
    business_modifiers: dict[str, float]
    default_multiplier: float = 1.0

    def matches(self, target_date: date) -> bool:
        return self.rule.matches(target_date)

    def modifier_for(self, business_key: str) -> float:
        return self.business_modifiers.get(business_key, self.default_multiplier)


def _nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> int | None:
    month_weeks = calendar.monthcalendar(year, month)
    weekday_days = [week[weekday] for week in month_weeks if week[weekday] != 0]
    if nth < 1 or nth > len(weekday_days):
        return None
    return weekday_days[nth - 1]


def _last_weekday_of_month(year: int, month: int, weekday: int) -> int | None:
    month_weeks = calendar.monthcalendar(year, month)
    weekday_days = [week[weekday] for week in month_weeks if week[weekday] != 0]
    if not weekday_days:
        return None
    return weekday_days[-1]


def _parse_month(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped.isdigit():
            return int(stripped)
        return MONTH_NAME_TO_INDEX.get(stripped)
    return None


def _parse_weekday(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return WEEKDAY_NAME_TO_INDEX.get(value.strip().lower())
    return None


def _parse_month_day(value: Any) -> tuple[int, int] | None:
    if isinstance(value, str):
        parts = value.strip().split("-")
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            return int(parts[0]), int(parts[1])
    return None


def _parse_rule_from_string(rule: str) -> HolidayRule:
    normalized = rule.strip().lower()
    if normalized == "range":
        raise ValueError("date_rule 'range' requires start/end fields")

    if "-" in normalized:
        month_day = _parse_month_day(normalized)
        if month_day:
            fixed_month, day = month_day
            return HolidayRule(rule_type="fixed", month=fixed_month, day=day)

    parts = normalized.split("_")
    if len(parts) == 3:
        ordinal, weekday_name, month_name = parts
        if ordinal == "last":
            weekday = _parse_weekday(weekday_name)
            month_value = _parse_month(month_name)
            if weekday is None or month_value is None:
                raise ValueError(f"Invalid date_rule {rule!r}")
            return HolidayRule(
                rule_type="last_weekday",
                month=month_value,
                weekday=weekday,
            )

        nth = ORDINAL_NAME_TO_INDEX.get(ordinal)
        weekday = _parse_weekday(weekday_name)
        month_value = _parse_month(month_name)
        if nth is None or weekday is None or month_value is None:
            raise ValueError(f"Invalid date_rule {rule!r}")
        return HolidayRule(
            rule_type="nth_weekday",
            month=month_value,
            weekday=weekday,
            nth=nth,
        )

    raise ValueError(f"Invalid date_rule {rule!r}")


def _parse_rule(item: dict[str, Any]) -> HolidayRule:
    rule_value = item.get("date_rule")
    if not rule_value:
        raise ValueError("holiday missing date_rule")
    if not isinstance(rule_value, str):
        raise ValueError("holiday date_rule must be a string")

    normalized = rule_value.strip().lower()
    if normalized == "fixed":
        month = _parse_month(item.get("month"))
        day = item.get("day")
        if month is None or not isinstance(day, int):
            raise ValueError("fixed date_rule requires month (1-12) and day (1-31)")
        if not (1 <= month <= 12) or not (1 <= day <= 31):
            raise ValueError("fixed date_rule month/day out of range")
        return HolidayRule(rule_type="fixed", month=month, day=day)

    if normalized == "range":
        start_raw = item.get("start")
        end_raw = item.get("end")
        start = _parse_month_day(start_raw)
        end = _parse_month_day(end_raw)
        if not start or not end:
            raise ValueError("range date_rule requires start/end in MM-DD format")
        start_month, start_day = start
        end_month, end_day = end
        if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
            raise ValueError("range date_rule start/end month out of range")
        if not (1 <= start_day <= 31 and 1 <= end_day <= 31):
            raise ValueError("range date_rule start/end day out of range")
        return HolidayRule(rule_type="range", start=start, end=end)

    return _parse_rule_from_string(normalized)


@lru_cache
def load_holiday_calendar() -> list[HolidayDefinition]:
    """Load holiday and event definitions from YAML."""
    holidays_path = Path(__file__).resolve().parent / "holidays.yaml"
    if not holidays_path.exists():
        return []

    raw = holidays_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("holidays") or []
    else:
        raise ValueError("holidays.yaml must be a list or mapping with 'holidays'")

    if not isinstance(items, list):
        raise ValueError("holidays must be a list")

    results: list[HolidayDefinition] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"holidays[{idx}] must be a mapping")
        name = item.get("name")
        if not name:
            raise ValueError(f"holidays[{idx}] missing name")

        rule = _parse_rule(item)

        raw_modifiers = item.get("business_modifiers")
        if not isinstance(raw_modifiers, dict):
            raise ValueError(f"holidays[{idx}] business_modifiers must be a mapping")

        modifiers: dict[str, float] = {}
        for key, value in raw_modifiers.items():
            try:
                modifiers[str(key)] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"holidays[{idx}] invalid modifier for {key!r}: {value!r}"
                ) from exc

        default_multiplier = item.get("default_multiplier", 1.0)
        try:
            default_value = float(default_multiplier)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"holidays[{idx}] invalid default_multiplier: {default_multiplier!r}"
            ) from exc

        results.append(
            HolidayDefinition(
                name=str(name),
                rule=rule,
                business_modifiers=modifiers,
                default_multiplier=default_value,
            )
        )

    return results
