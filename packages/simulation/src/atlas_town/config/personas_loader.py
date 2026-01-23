"""Utilities for loading persona configuration from YAML files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

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
