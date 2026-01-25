"""Economics helpers for simulation (inflation, pricing adjustments)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from atlas_town.config import get_settings


@dataclass(frozen=True)
class InflationModel:
    """Inflation model for adjusting amounts over simulation time."""

    annual_rate: Decimal
    start_date: date

    @classmethod
    def disabled(cls) -> InflationModel:
        """Return a model that applies no inflation."""
        return cls(annual_rate=Decimal("0"), start_date=date.max)

    def factor_for(self, current_date: date) -> Decimal:
        """Return the inflation factor for the given date."""
        if self.annual_rate <= 0 or current_date <= self.start_date:
            return Decimal("1")
        days = (current_date - self.start_date).days
        years = days / 365.0
        factor = (1.0 + float(self.annual_rate)) ** years
        return Decimal(str(factor))

    def apply(
        self,
        amount: Decimal,
        current_date: date,
        quantize: Decimal = Decimal("0.01"),
    ) -> Decimal:
        """Apply inflation to a monetary amount."""
        if amount <= 0:
            return amount
        factor = self.factor_for(current_date)
        inflated = amount * factor
        return inflated.quantize(quantize, rounding=ROUND_HALF_UP)

    def annual_increase_multiplier(self) -> Decimal:
        """Return the annual multiplier (1 + annual_rate)."""
        return Decimal("1") + self.annual_rate

    def is_anniversary(self, current_date: date) -> bool:
        """Return True if current_date is the inflation anniversary."""
        if current_date < self.start_date:
            return False
        return (
            current_date.month == self.start_date.month
            and current_date.day == self.start_date.day
        )


def get_inflation_model() -> InflationModel:
    """Build InflationModel from settings."""
    settings = get_settings()
    return InflationModel(
        annual_rate=Decimal(str(settings.inflation_annual_rate)),
        start_date=settings.inflation_start_date,
    )


def apply_inflation_to_amounts(
    amounts: Iterable[Decimal],
    current_date: date,
    model: InflationModel,
    quantize: Decimal = Decimal("0.01"),
) -> list[Decimal]:
    """Apply inflation to a list of amounts."""
    return [model.apply(amount, current_date, quantize=quantize) for amount in amounts]
