"""Transaction generator for realistic daily business activity.

This module generates realistic transactions based on business type,
day of week, and seasonal patterns.
"""

import calendar
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from atlas_town.agents.vendor import VENDOR_ARCHETYPES, VendorType
from atlas_town.config.holidays import load_holiday_calendar
from atlas_town.config.personas_loader import (
    WEEKDAY_NAME_TO_INDEX,
    load_persona_day_patterns,
    load_persona_employees,
    load_persona_financing_configs,
    load_persona_industries,
    load_persona_payroll_configs,
    load_persona_recurring_transactions,
    load_persona_tax_configs,
)
from atlas_town.economics import InflationModel, get_inflation_model
from atlas_town.scheduler import PHASE_TIMES, DayPhase

logger = structlog.get_logger(__name__)


class TransactionType(str, Enum):
    """Types of transactions that can be generated."""
    INVOICE = "invoice"
    BILL = "bill"
    PAYMENT_RECEIVED = "payment_received"
    BILL_PAYMENT = "bill_payment"
    CASH_SALE = "cash_sale"


@dataclass
class TransactionPattern:
    """Defines a transaction pattern for a business type."""
    transaction_type: TransactionType
    description_template: str
    min_amount: Decimal
    max_amount: Decimal
    probability: float  # 0.0 to 1.0 - chance of occurring each day
    weekday_only: bool = False  # Only occurs Mon-Fri
    weekend_boost: float = 1.0  # Multiplier for weekend probability
    # Time-of-day modifiers for realistic business patterns
    phase_multipliers: dict[str, float] | None = None
    # e.g., {"evening": 2.5, "night": 1.5}
    active_hours: tuple[int, int] | None = None
    # (start_hour, end_hour) - restricts when pattern is active
    # Seasonal modifiers - maps month (1-12) to multiplier for pattern-specific overrides
    seasonal_multipliers: dict[int, float] | None = None


@dataclass
class GeneratedTransaction:
    """A transaction ready to be created via the API."""
    transaction_type: TransactionType
    description: str
    amount: Decimal
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RecurringTransactionSpec:
    """Config for a recurring calendar-based transaction."""

    name: str
    vendor: str
    amount: Decimal
    day_of_month: int
    anniversary_date: date | None = None
    category: str | None = None
    interval_months: int = 1

    def is_due(self, current_date: date) -> bool:
        """Check if this recurring transaction should fire on the given date."""
        if current_date.day != self.day_of_month:
            return False

        if self.anniversary_date:
            months_delta = (
                (current_date.year - self.anniversary_date.year) * 12
                + (current_date.month - self.anniversary_date.month)
            )
            if months_delta < 0:
                return False
            if self.interval_months > 1 and months_delta % self.interval_months != 0:
                return False
        elif self.interval_months > 1:
            return False

        return True


class RecurringTransactionScheduler:
    """Deterministic scheduler for recurring monthly transactions."""

    def __init__(self, recurring_by_business: dict[str, list[RecurringTransactionSpec]]):
        self._recurring_by_business = recurring_by_business
        self._last_generated: dict[tuple[str, str], date] = {}
        self._logger = logger.bind(component="recurring_scheduler")

    def _find_vendor_id(
        self, vendor_name: str, vendors: list[dict[str, Any]]
    ) -> UUID | None:
        normalized = vendor_name.strip().lower()
        for vendor in vendors:
            name = str(
                vendor.get("display_name") or vendor.get("name", "")
            ).strip().lower()
            if name == normalized:
                try:
                    return UUID(vendor["id"])
                except (KeyError, ValueError, TypeError):
                    continue
        return None

    def get_due_transactions(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
    ) -> list[GeneratedTransaction]:
        """Return recurring transactions due on the given date."""
        results: list[GeneratedTransaction] = []
        for spec in self._recurring_by_business.get(business_key, []):
            if not spec.is_due(current_date):
                continue

            key = (business_key, spec.name)
            last = self._last_generated.get(key)
            if last and last.year == current_date.year and last.month == current_date.month:
                continue

            vendor_id = self._find_vendor_id(spec.vendor, vendors)
            if vendor_id is None and vendors:
                self._logger.warning(
                    "recurring_vendor_fallback",
                    business=business_key,
                    vendor=spec.vendor,
                )
                try:
                    vendor_id = UUID(vendors[0]["id"])
                except (KeyError, ValueError, TypeError):
                    vendor_id = None

            if vendor_id is None:
                self._logger.warning(
                    "recurring_vendor_missing",
                    business=business_key,
                    vendor=spec.vendor,
                )
                continue

            description = spec.name
            if spec.category:
                description = f"{spec.name} ({spec.category})"

            results.append(
                GeneratedTransaction(
                    transaction_type=TransactionType.BILL,
                    description=description,
                    amount=spec.amount,
                    vendor_id=vendor_id,
                    metadata={
                        "recurring_name": spec.name,
                        "vendor_name": spec.vendor,
                        "category": spec.category,
                    },
                )
            )
            self._last_generated[key] = current_date

        return results


@dataclass(frozen=True)
class FinancingRateAdjustment:
    """Interest rate change effective on a given date."""

    effective_date: date
    rate: Decimal


@dataclass(frozen=True)
class LoanSpec:
    """Fixed principal loan configuration."""

    name: str
    principal: Decimal
    annual_rate: Decimal
    term_months: int
    payment_day: int
    lender: str
    loan_type: str = "term_loan"
    start_date: date | None = None
    rate_adjustments: tuple[FinancingRateAdjustment, ...] = ()


@dataclass(frozen=True)
class EquipmentFinancingSpec:
    """Equipment financing configuration with decision metadata."""

    name: str
    principal: Decimal
    annual_rate: Decimal
    term_months: int
    payment_day: int
    lender: str
    start_date: date | None = None
    rate_adjustments: tuple[FinancingRateAdjustment, ...] = ()
    decision: str = "auto"  # auto, lease, purchase, loan
    decision_rate_threshold: Decimal | None = None
    decision_principal_threshold: Decimal | None = None
    lease_probability: float | None = None
    purchase_probability: float | None = None


@dataclass
class EquipmentLeaseState:
    """Mutable state for lease amortization schedules."""

    remaining_balance: Decimal
    remaining_terms: int


@dataclass(frozen=True)
class BalanceEvent:
    """Line of credit balance event."""

    effective_date: date
    balance: Decimal


@dataclass(frozen=True)
class LineOfCreditSpec:
    """Line of credit configuration."""

    name: str
    annual_rate: Decimal
    balance: Decimal
    billing_day: int
    lender: str
    start_date: date | None = None
    rate_adjustments: tuple[FinancingRateAdjustment, ...] = ()
    balance_events: tuple[BalanceEvent, ...] = ()


class FinancingScheduler:
    """Generate interest expense transactions for loans and credit lines."""

    def __init__(
        self,
        term_loans_by_business: dict[str, list[LoanSpec]],
        locs_by_business: dict[str, list[LineOfCreditSpec]],
        equipment_financing_by_business: dict[str, list[EquipmentFinancingSpec]],
        rng: random.Random | None = None,
    ) -> None:
        self._term_loans_by_business: dict[str, list[LoanSpec]] = (
            term_loans_by_business
        )
        self._locs_by_business: dict[str, list[LineOfCreditSpec]] = locs_by_business
        self._equipment_by_business: dict[str, list[EquipmentFinancingSpec]] = (
            equipment_financing_by_business
        )
        self._equipment_decisions: dict[tuple[str, str], str] = {}
        self._equipment_state: dict[tuple[str, str], EquipmentLeaseState] = {}
        self._equipment_payment_generated: set[tuple[str, str, int, int]] = set()
        self._equipment_purchase_recorded: set[tuple[str, str]] = set()
        self._rng = rng or random.Random()
        self._loan_interest_generated: set[tuple[str, str, int, int]] = set()
        self._loc_interest_billed: set[tuple[str, str, int, int]] = set()
        self._loc_accrued_interest: dict[tuple[str, str, int, int], Decimal] = {}
        self._loc_last_accrual: dict[tuple[str, str], date] = {}
        self._loc_current_balance: dict[tuple[str, str], Decimal] = {}
        self._logger = logger.bind(component="financing_scheduler")

    @staticmethod
    def _find_vendor_id(
        vendor_name: str, vendors: list[dict[str, Any]]
    ) -> UUID | None:
        normalized = vendor_name.strip().lower()
        for vendor in vendors:
            name = str(
                vendor.get("display_name") or vendor.get("name", "")
            ).strip().lower()
            if name == normalized:
                try:
                    return UUID(vendor["id"])
                except (KeyError, ValueError, TypeError):
                    continue
        return None

    @staticmethod
    def _rate_for_date(
        base_rate: Decimal, adjustments: tuple[FinancingRateAdjustment, ...], day: date
    ) -> Decimal:
        rate = base_rate
        for adjustment in adjustments:
            if adjustment.effective_date <= day:
                rate = adjustment.rate
            else:
                break
        return rate

    @staticmethod
    def _effective_day(day_of_month: int, current_date: date) -> int:
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        return min(max(1, day_of_month), last_day)

    def _loan_interest_due(
        self, spec: LoanSpec | EquipmentFinancingSpec, current_date: date
    ) -> bool:
        if spec.start_date and current_date < spec.start_date:
            return False
        due_day = self._effective_day(spec.payment_day, current_date)
        return current_date.day == due_day

    def _equipment_payment_due(
        self, spec: EquipmentFinancingSpec, current_date: date
    ) -> bool:
        if spec.start_date and current_date < spec.start_date:
            return False
        due_day = self._effective_day(spec.payment_day, current_date)
        return current_date.day == due_day

    def _bill_period_for_loc(
        self, billing_day: int, current_date: date
    ) -> tuple[int, int]:
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        if billing_day >= last_day:
            return current_date.year, current_date.month
        month = current_date.month - 1
        year = current_date.year
        if month == 0:
            month = 12
            year -= 1
        return year, month

    def _accrue_loc_interest(
        self,
        business_key: str,
        spec: LineOfCreditSpec,
        current_date: date,
    ) -> None:
        if spec.start_date and current_date < spec.start_date:
            return
        key = (business_key, spec.name)
        last_date = self._loc_last_accrual.get(key)
        if last_date is None:
            last_date = current_date - timedelta(days=1)

        day = last_date + timedelta(days=1)
        while day <= current_date:
            if spec.start_date and day < spec.start_date:
                day += timedelta(days=1)
                continue
            balance = self._loc_current_balance.get(key, spec.balance)
            for event in spec.balance_events:
                if event.effective_date == day:
                    balance = event.balance
            self._loc_current_balance[key] = balance
            if balance > 0:
                rate = self._rate_for_date(spec.annual_rate, spec.rate_adjustments, day)
                daily_interest = balance * rate / Decimal("365")
                bucket = (business_key, spec.name, day.year, day.month)
                self._loc_accrued_interest[bucket] = (
                    self._loc_accrued_interest.get(bucket, Decimal("0"))
                    + daily_interest
                )
            day += timedelta(days=1)

        self._loc_last_accrual[key] = current_date

    def _equipment_decision(
        self, business_key: str, spec: EquipmentFinancingSpec
    ) -> str:
        key = (business_key, spec.name)
        existing = self._equipment_decisions.get(key)
        if existing:
            return existing

        decision = spec.decision.strip().lower()
        if decision in {"lease", "purchase", "loan"}:
            self._equipment_decisions[key] = decision
            return decision

        if spec.lease_probability is not None or spec.purchase_probability is not None:
            lease_prob = spec.lease_probability if spec.lease_probability is not None else 0.5
            purchase_prob = (
                spec.purchase_probability
                if spec.purchase_probability is not None
                else max(0.0, 1.0 - lease_prob)
            )
            threshold = lease_prob / max(lease_prob + purchase_prob, 1e-6)
            decision = "lease" if self._rng.random() < threshold else "purchase"
            self._equipment_decisions[key] = decision
            return decision

        rate_threshold = spec.decision_rate_threshold or Decimal("0.08")
        principal_threshold = spec.decision_principal_threshold or Decimal("50000")
        decision = (
            "lease"
            if spec.annual_rate >= rate_threshold
            or spec.principal >= principal_threshold
            else "purchase"
        )
        self._equipment_decisions[key] = decision
        return decision

    @staticmethod
    def _amortized_payment(
        principal: Decimal, annual_rate: Decimal, term_months: int
    ) -> Decimal:
        if term_months <= 0:
            return Decimal("0")
        if annual_rate <= 0:
            return (principal / Decimal(term_months)).quantize(Decimal("0.01"))
        monthly_rate = annual_rate / Decimal("12")
        numerator = principal * monthly_rate
        denominator = Decimal("1") - (Decimal("1") + monthly_rate) ** Decimal(
            -term_months
        )
        if denominator == 0:
            return Decimal("0")
        return (numerator / denominator).quantize(Decimal("0.01"))

    def get_due_transactions(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
    ) -> list[GeneratedTransaction]:
        results: list[GeneratedTransaction] = []

        for loan_spec in self._term_loans_by_business.get(business_key, []):
            if not self._loan_interest_due(loan_spec, current_date):
                continue
            key = (
                business_key,
                loan_spec.name,
                current_date.year,
                current_date.month,
            )
            if key in self._loan_interest_generated:
                continue
            vendor_id = self._find_vendor_id(loan_spec.lender, vendors)
            if vendor_id is None:
                self._logger.warning(
                    "loan_interest_vendor_missing",
                    business=business_key,
                    loan=loan_spec.name,
                    vendor=loan_spec.lender,
                )
                continue
            rate = self._rate_for_date(
                loan_spec.annual_rate, loan_spec.rate_adjustments, current_date
            )
            interest = (loan_spec.principal * rate / Decimal("12")).quantize(
                Decimal("0.01")
            )
            if interest <= 0:
                continue
            results.append(
                GeneratedTransaction(
                    transaction_type=TransactionType.BILL,
                    description=f"Loan interest - {loan_spec.name}",
                    amount=interest,
                    vendor_id=vendor_id,
                    metadata={
                        "financing_type": loan_spec.loan_type,
                        "loan_name": loan_spec.name,
                        "annual_rate": str(rate),
                    },
                )
            )
            self._loan_interest_generated.add(key)

        for equipment_spec in self._equipment_by_business.get(business_key, []):
            decision = self._equipment_decision(business_key, equipment_spec)
            vendor_id = self._find_vendor_id(equipment_spec.lender, vendors)
            if vendor_id is None:
                self._logger.warning(
                    "equipment_interest_vendor_missing",
                    business=business_key,
                    loan=equipment_spec.name,
                    vendor=equipment_spec.lender,
                )
                continue

            if decision == "purchase":
                if (business_key, equipment_spec.name) in self._equipment_purchase_recorded:
                    continue
                if not equipment_spec.start_date:
                    due = self._equipment_payment_due(equipment_spec, current_date)
                else:
                    due = current_date >= equipment_spec.start_date
                if not due:
                    continue
                results.append(
                    GeneratedTransaction(
                        transaction_type=TransactionType.BILL,
                        description=f"Equipment purchase - {equipment_spec.name}",
                        amount=equipment_spec.principal.quantize(Decimal("0.01")),
                        vendor_id=vendor_id,
                        metadata={
                            "financing_type": "equipment_purchase",
                            "equipment_name": equipment_spec.name,
                            "line_items": [
                                {
                                    "description": f"{equipment_spec.name} purchase",
                                    "amount": str(
                                        equipment_spec.principal.quantize(Decimal("0.01"))
                                    ),
                                    "account_hint": "equipment_asset",
                                }
                            ],
                        },
                    )
                )
                self._equipment_purchase_recorded.add((business_key, equipment_spec.name))
                continue

            if decision == "lease":
                if not self._equipment_payment_due(equipment_spec, current_date):
                    continue
                key = (
                    business_key,
                    equipment_spec.name,
                    current_date.year,
                    current_date.month,
                )
                if key in self._equipment_payment_generated:
                    continue
                state_key = (business_key, equipment_spec.name)
                state = self._equipment_state.get(state_key)
                if state is None:
                    state = EquipmentLeaseState(
                        remaining_balance=equipment_spec.principal,
                        remaining_terms=equipment_spec.term_months,
                    )
                    self._equipment_state[state_key] = state
                if state.remaining_terms <= 0 or state.remaining_balance <= 0:
                    continue

                rate = self._rate_for_date(
                    equipment_spec.annual_rate,
                    equipment_spec.rate_adjustments,
                    current_date,
                )
                payment = self._amortized_payment(
                    state.remaining_balance, rate, state.remaining_terms
                )
                if payment <= 0:
                    continue
                monthly_rate = rate / Decimal("12")
                interest = (state.remaining_balance * monthly_rate).quantize(
                    Decimal("0.01")
                )
                principal_component = (payment - interest).quantize(Decimal("0.01"))
                if principal_component < 0:
                    principal_component = Decimal("0.00")

                results.append(
                    GeneratedTransaction(
                        transaction_type=TransactionType.BILL,
                        description=f"Equipment lease payment - {equipment_spec.name}",
                        amount=payment,
                        vendor_id=vendor_id,
                        metadata={
                            "financing_type": "equipment_lease",
                            "equipment_name": equipment_spec.name,
                            "annual_rate": str(rate),
                            "interest_amount": str(interest),
                            "principal_amount": str(principal_component),
                            "line_items": [
                                {
                                    "description": f"Interest expense - {equipment_spec.name}",
                                    "amount": str(interest),
                                    "account_hint": "interest_expense",
                                },
                                {
                                    "description": f"Equipment principal - {equipment_spec.name}",
                                    "amount": str(principal_component),
                                    "account_hint": "equipment_asset",
                                },
                            ],
                        },
                    )
                )
                state.remaining_balance = (
                    state.remaining_balance - principal_component
                ).quantize(Decimal("0.01"))
                state.remaining_terms -= 1
                self._equipment_payment_generated.add(key)
                continue

            if not self._loan_interest_due(equipment_spec, current_date):
                continue
            key = (
                business_key,
                equipment_spec.name,
                current_date.year,
                current_date.month,
            )
            if key in self._loan_interest_generated:
                continue
            rate = self._rate_for_date(
                equipment_spec.annual_rate, equipment_spec.rate_adjustments, current_date
            )
            interest = (equipment_spec.principal * rate / Decimal("12")).quantize(
                Decimal("0.01")
            )
            if interest <= 0:
                continue
            results.append(
                GeneratedTransaction(
                    transaction_type=TransactionType.BILL,
                    description=f"Equipment financing interest - {equipment_spec.name}",
                    amount=interest,
                    vendor_id=vendor_id,
                    metadata={
                        "financing_type": "equipment_financing",
                        "loan_name": equipment_spec.name,
                        "annual_rate": str(rate),
                    },
                )
            )
            self._loan_interest_generated.add(key)

        for loc_spec in self._locs_by_business.get(business_key, []):
            self._accrue_loc_interest(business_key, loc_spec, current_date)
            if loc_spec.start_date and current_date < loc_spec.start_date:
                continue
            billing_day = self._effective_day(loc_spec.billing_day, current_date)
            if current_date.day != billing_day:
                continue
            bill_year, bill_month = self._bill_period_for_loc(
                billing_day, current_date
            )
            bill_key = (business_key, loc_spec.name, bill_year, bill_month)
            if bill_key in self._loc_interest_billed:
                continue
            interest = self._loc_accrued_interest.get(bill_key, Decimal("0")).quantize(
                Decimal("0.01")
            )
            if interest <= 0:
                self._loc_interest_billed.add(bill_key)
                continue
            vendor_id = self._find_vendor_id(loc_spec.lender, vendors)
            if vendor_id is None:
                self._logger.warning(
                    "loc_interest_vendor_missing",
                    business=business_key,
                    loc=loc_spec.name,
                    vendor=loc_spec.lender,
                )
                continue
            results.append(
                GeneratedTransaction(
                    transaction_type=TransactionType.BILL,
                    description=f"Line of credit interest - {loc_spec.name}",
                    amount=interest,
                    vendor_id=vendor_id,
                    metadata={
                        "financing_type": "line_of_credit",
                        "credit_line": loc_spec.name,
                        "annual_rate": str(
                            self._rate_for_date(
                                loc_spec.annual_rate,
                                loc_spec.rate_adjustments,
                                current_date,
                            )
                        ),
                        "interest_period": f"{bill_year:04d}-{bill_month:02d}",
                    },
                )
            )
            self._loc_interest_billed.add(bill_key)
            self._loc_accrued_interest.pop(bill_key, None)

        return results


@dataclass(frozen=True)
class EmployeeSpec:
    """Employee configuration for payroll simulation."""

    role: str
    count: int
    pay_rate: Decimal
    hours_per_week: Decimal


@dataclass(frozen=True)
class PayrollConfig:
    """Payroll scheduling configuration."""

    frequency: str  # weekly, bi-weekly, monthly
    pay_day: str | int
    payroll_vendor: str | None
    tax_authority: str | None


class PayrollGenerator:
    """Generate payroll expense and tax deposit bills."""

    _SOCIAL_SECURITY = Decimal("0.062")
    _MEDICARE = Decimal("0.0145")
    _WITHHOLDING = Decimal("0.12")
    _QUARTERLY_DEPOSIT_THRESHOLD = Decimal("2500")
    _SEMI_WEEKLY_THRESHOLD = Decimal("50000")
    _FUTA_RATE = Decimal("0.006")
    _FUTA_DEPOSIT_THRESHOLD = Decimal("500")

    def __init__(
        self,
        employees_by_business: dict[str, list[EmployeeSpec]],
        payroll_by_business: dict[str, PayrollConfig],
        industries_by_business: dict[str, str] | None = None,
        inflation: InflationModel | None = None,
    ) -> None:
        self._employees_by_business = employees_by_business
        self._payroll_by_business = payroll_by_business
        self._industries_by_business = industries_by_business or {}
        self._inflation = inflation or get_inflation_model()
        self._last_pay_date: dict[str, date] = {}
        self._tax_due_by_date: dict[str, dict[date, Decimal]] = {}
        self._quarter_tax_liability: dict[tuple[str, int, int], Decimal] = {}
        self._quarter_tax_deposited: dict[tuple[str, int, int], Decimal] = {}
        self._form_941_filed: set[tuple[str, int, int]] = set()
        self._futa_liability_by_quarter: dict[tuple[str, int, int], Decimal] = {}
        self._futa_liability_by_year: dict[tuple[str, int], Decimal] = {}
        self._futa_deposited_by_year: dict[tuple[str, int], Decimal] = {}
        self._futa_deposit_recorded: set[tuple[str, int, int]] = set()
        self._form_940_filed: set[tuple[str, int]] = set()
        self._year_end_processed: set[tuple[str, int]] = set()
        self._form_1099_filed: set[tuple[str, int, UUID]] = set()
        self._eligible_1099_names = self._build_1099_eligible_names()
        self._logger = logger.bind(component="payroll_generator")

    def _normalize_frequency(self, frequency: str) -> str:
        normalized = frequency.strip().lower().replace("_", "-")
        if normalized == "biweekly":
            normalized = "bi-weekly"
        if normalized not in {"weekly", "bi-weekly", "monthly"}:
            self._logger.warning("payroll_invalid_frequency", frequency=frequency)
            return "bi-weekly"
        return normalized

    def _weekday_index(self, pay_day: Any) -> int | None:
        if isinstance(pay_day, int):
            return None
        if isinstance(pay_day, str):
            return WEEKDAY_NAME_TO_INDEX.get(pay_day.strip().lower())
        return None

    def _last_weekday_of_month(self, year: int, month: int, weekday: int) -> date:
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)
        offset = (last_day.weekday() - weekday) % 7
        return last_day - timedelta(days=offset)

    def _payroll_due(self, business_key: str, current_date: date) -> bool:
        employees = self._employees_by_business.get(business_key)
        config = self._payroll_by_business.get(business_key)
        if not employees or not config:
            return False

        frequency = self._normalize_frequency(config.frequency)
        last_date = self._last_pay_date.get(business_key)

        if frequency in {"weekly", "bi-weekly"}:
            weekday = self._weekday_index(config.pay_day)
            if weekday is None:
                return False
            if current_date.weekday() != weekday:
                return False
            if last_date is None:
                return True
            gap = (current_date - last_date).days
            return gap >= (14 if frequency == "bi-weekly" else 7)

        # Monthly
        if (
            last_date
            and last_date.year == current_date.year
            and last_date.month == current_date.month
        ):
            return False

        if isinstance(config.pay_day, int):
            return current_date.day == config.pay_day

        weekday = self._weekday_index(config.pay_day)
        if weekday is None:
            return False
        return current_date == self._last_weekday_of_month(
            current_date.year, current_date.month, weekday
        )

    def _calculate_gross_pay(
        self,
        employees: list[EmployeeSpec],
        frequency: str,
        inflation_factor: Decimal,
    ) -> Decimal:
        weeks = Decimal("1")
        if frequency == "bi-weekly":
            weeks = Decimal("2")
        elif frequency == "monthly":
            weeks = Decimal("4")

        total = Decimal("0")
        for emp in employees:
            adjusted_rate = emp.pay_rate * inflation_factor
            total += adjusted_rate * emp.hours_per_week * weeks * Decimal(emp.count)
        return total.quantize(Decimal("0.01"))

    @staticmethod
    def _quarter_for_date(current_date: date) -> tuple[int, int]:
        quarter = ((current_date.month - 1) // 3) + 1
        return current_date.year, quarter

    @staticmethod
    def _form_941_due_quarters_for_date(current_date: date) -> list[tuple[int, int]]:
        if current_date.month == 4 and current_date.day == 30:
            return [(current_date.year, 1)]
        if current_date.month == 7 and current_date.day == 31:
            return [(current_date.year, 2)]
        if current_date.month == 10 and current_date.day == 31:
            return [(current_date.year, 3)]
        if current_date.month == 1 and current_date.day == 31:
            return [(current_date.year - 1, 4)]
        return []

    @staticmethod
    def _next_monthly_deposit_date(pay_date: date) -> date:
        month = pay_date.month + 1
        year = pay_date.year
        if month > 12:
            month = 1
            year += 1
        return date(year, month, 15)

    def _build_1099_eligible_names(self) -> dict[str, set[str]]:
        eligible: dict[str, set[str]] = {}
        for business_key, industry in self._industries_by_business.items():
            profiles = VENDOR_ARCHETYPES.get(industry, [])
            names = {
                profile.name.strip().lower()
                for profile in profiles
                if profile.vendor_type == VendorType.SERVICE
            }
            if names:
                eligible[business_key] = names
        return eligible

    def _determine_deposit_schedule(self, quarter_total: Decimal) -> str:
        if quarter_total < self._QUARTERLY_DEPOSIT_THRESHOLD:
            return "quarterly"
        if quarter_total <= self._SEMI_WEEKLY_THRESHOLD:
            return "monthly"
        return "semi-weekly"

    def _schedule_tax_deposit(
        self, business_key: str, pay_date: date, tax_amount: Decimal
    ) -> None:
        if tax_amount <= 0:
            return
        tax_year, quarter = self._quarter_for_date(pay_date)
        key = (business_key, tax_year, quarter)

        quarter_total = self._quarter_tax_liability.get(key, Decimal("0")) + tax_amount
        self._quarter_tax_liability[key] = quarter_total

        schedule = self._determine_deposit_schedule(quarter_total)
        if schedule == "quarterly":
            return

        due_date = (
            pay_date + timedelta(days=3)
            if schedule == "semi-weekly"
            else self._next_monthly_deposit_date(pay_date)
        )

        deposited = self._quarter_tax_deposited.get(key, Decimal("0"))
        outstanding = quarter_total - deposited
        if outstanding <= 0:
            return

        business_due = self._tax_due_by_date.setdefault(business_key, {})
        business_due[due_date] = business_due.get(due_date, Decimal("0")) + outstanding
        self._quarter_tax_deposited[key] = quarter_total

    def _find_vendor_id(
        self, vendor_name: str | None, vendors: list[dict[str, Any]]
    ) -> UUID | None:
        if not vendors:
            return None
        if vendor_name:
            normalized = vendor_name.strip().lower()
            for vendor in vendors:
                name = str(
                    vendor.get("display_name") or vendor.get("name", "")
                ).strip().lower()
                if name == normalized:
                    try:
                        return UUID(vendor["id"])
                    except (KeyError, ValueError, TypeError):
                        continue
        try:
            return UUID(vendors[0]["id"])
        except (KeyError, ValueError, TypeError):
            return None

    def _eligible_1099_vendors(
        self, business_key: str, vendors: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        eligible_names = self._eligible_1099_names.get(business_key)
        if not eligible_names:
            return []

        matches: list[dict[str, Any]] = []
        for vendor in vendors:
            name = str(
                vendor.get("display_name") or vendor.get("name", "")
            ).strip().lower()
            if name in eligible_names:
                matches.append(vendor)
        return matches

    def get_due_transactions(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
    ) -> list[GeneratedTransaction]:
        """Return payroll and tax deposit transactions due on the given date."""
        transactions: list[GeneratedTransaction] = []
        employees = self._employees_by_business.get(business_key, [])
        config = self._payroll_by_business.get(business_key)
        if not employees or not config:
            return transactions

        frequency = self._normalize_frequency(config.frequency)
        inflation_factor = self._inflation.factor_for(current_date)

        # Payroll run
        if self._payroll_due(business_key, current_date):
            gross = self._calculate_gross_pay(employees, frequency, inflation_factor)
            if gross > 0:
                ss = (gross * self._SOCIAL_SECURITY).quantize(Decimal("0.01"))
                medicare = (gross * self._MEDICARE).quantize(Decimal("0.01"))
                withholding = (gross * self._WITHHOLDING).quantize(Decimal("0.01"))
                taxes = ss + medicare + withholding

                vendor_id = self._find_vendor_id(config.payroll_vendor, vendors)
                if vendor_id is None and vendors:
                    self._logger.warning(
                        "payroll_vendor_fallback",
                        business=business_key,
                        vendor=config.payroll_vendor,
                    )

                if vendor_id:
                    role_summary = ", ".join(
                        f"{emp.count} {emp.role}" for emp in employees
                    )
                    transactions.append(
                        GeneratedTransaction(
                            transaction_type=TransactionType.BILL,
                            description=f"Payroll ({frequency}) - {role_summary}",
                            amount=gross,
                            vendor_id=vendor_id,
                            metadata={
                                "payroll_gross": str(gross),
                                "tax_social_security": str(ss),
                                "tax_medicare": str(medicare),
                                "tax_withholding": str(withholding),
                                "expense_account_hint": "payroll",
                            },
                        )
                    )

                self._schedule_tax_deposit(business_key, current_date, taxes)
                self._last_pay_date[business_key] = current_date

                futa_tax = (gross * self._FUTA_RATE).quantize(Decimal("0.01"))
                tax_year, quarter = self._quarter_for_date(current_date)
                futa_key = (business_key, tax_year, quarter)
                year_key = (business_key, tax_year)
                self._futa_liability_by_quarter[futa_key] = (
                    self._futa_liability_by_quarter.get(futa_key, Decimal("0"))
                    + futa_tax
                )
                self._futa_liability_by_year[year_key] = (
                    self._futa_liability_by_year.get(year_key, Decimal("0"))
                    + futa_tax
                )

        # Tax deposit due today
        due_map = self._tax_due_by_date.get(business_key, {})
        tax_amount = due_map.pop(current_date, None)
        if tax_amount and tax_amount > 0:
            tax_vendor_id = self._find_vendor_id(config.tax_authority, vendors)
            if tax_vendor_id is None and vendors:
                self._logger.warning(
                    "payroll_tax_vendor_fallback",
                    business=business_key,
                    vendor=config.tax_authority,
                )

            if tax_vendor_id:
                transactions.append(
                    GeneratedTransaction(
                        transaction_type=TransactionType.BILL,
                        description="Payroll tax deposit",
                        amount=tax_amount.quantize(Decimal("0.01")),
                        vendor_id=tax_vendor_id,
                        metadata={
                            "tax_deposit": "payroll",
                            "expense_account_hint": "payroll tax",
                        },
                    )
                )

        for tax_year, quarter in self._form_941_due_quarters_for_date(current_date):
            key = (business_key, tax_year, quarter)
            if key in self._form_941_filed:
                continue

            filing_vendor_id = self._find_vendor_id(
                config.payroll_vendor or config.tax_authority, vendors
            )
            if filing_vendor_id:
                transactions.append(
                    GeneratedTransaction(
                        transaction_type=TransactionType.BILL,
                        description=f"Form 941 filing Q{quarter} {tax_year}",
                        amount=Decimal("75.00"),
                        vendor_id=filing_vendor_id,
                        metadata={
                            "compliance_filing": "form_941",
                            "tax_year": str(tax_year),
                            "quarter": str(quarter),
                            "expense_account_hint": "payroll tax",
                        },
                    )
                )

            remaining = (
                self._quarter_tax_liability.get(key, Decimal("0"))
                - self._quarter_tax_deposited.get(key, Decimal("0"))
            )
            if remaining > 0:
                tax_vendor_id = self._find_vendor_id(config.tax_authority, vendors)
                if tax_vendor_id:
                    transactions.append(
                        GeneratedTransaction(
                            transaction_type=TransactionType.BILL,
                            description="Payroll tax deposit",
                            amount=remaining.quantize(Decimal("0.01")),
                            vendor_id=tax_vendor_id,
                            metadata={
                                "tax_deposit": "payroll",
                                "expense_account_hint": "payroll tax",
                                "form_941": "true",
                                "tax_year": str(tax_year),
                                "quarter": str(quarter),
                            },
                        )
                    )
                self._quarter_tax_deposited[key] = self._quarter_tax_liability.get(
                    key, Decimal("0")
                )

            self._form_941_filed.add(key)

        for tax_year, quarter in self._form_941_due_quarters_for_date(current_date):
            futa_key = (business_key, tax_year, quarter)
            year_key = (business_key, tax_year)
            remaining = (
                self._futa_liability_by_year.get(year_key, Decimal("0"))
                - self._futa_deposited_by_year.get(year_key, Decimal("0"))
            )
            if remaining <= 0:
                continue
            if remaining < self._FUTA_DEPOSIT_THRESHOLD and quarter != 4:
                continue
            if futa_key in self._futa_deposit_recorded:
                continue

            tax_vendor_id = self._find_vendor_id(config.tax_authority, vendors)
            if tax_vendor_id:
                transactions.append(
                    GeneratedTransaction(
                        transaction_type=TransactionType.BILL,
                        description=f"FUTA tax deposit Q{quarter} {tax_year}",
                        amount=remaining.quantize(Decimal("0.01")),
                        vendor_id=tax_vendor_id,
                        metadata={
                            "tax_deposit": "futa",
                            "expense_account_hint": "payroll tax",
                            "tax_year": str(tax_year),
                            "quarter": str(quarter),
                        },
                    )
                )
                self._futa_deposited_by_year[year_key] = (
                    self._futa_deposited_by_year.get(year_key, Decimal("0"))
                    + remaining
                )
                self._futa_deposit_recorded.add(futa_key)

        if current_date.month == 1 and current_date.day == 31:
            tax_year = current_date.year - 1
            year_key = (business_key, tax_year)
            if year_key not in self._form_940_filed:
                filing_vendor_id = self._find_vendor_id(
                    config.payroll_vendor or config.tax_authority, vendors
                )
                if filing_vendor_id:
                    transactions.append(
                        GeneratedTransaction(
                            transaction_type=TransactionType.BILL,
                            description=f"Form 940 filing {tax_year}",
                            amount=Decimal("50.00"),
                            vendor_id=filing_vendor_id,
                            metadata={
                                "compliance_filing": "form_940",
                                "tax_year": str(tax_year),
                                "expense_account_hint": "payroll tax",
                            },
                        )
                    )
                self._form_940_filed.add(year_key)

            if year_key not in self._year_end_processed:
                filing_vendor_id = self._find_vendor_id(
                    config.payroll_vendor or config.tax_authority, vendors
                )
                if filing_vendor_id:
                    transactions.append(
                        GeneratedTransaction(
                            transaction_type=TransactionType.BILL,
                            description=f"Year-end W-2 processing {tax_year}",
                            amount=Decimal("85.00"),
                            vendor_id=filing_vendor_id,
                            metadata={
                                "compliance_filing": "w2",
                                "tax_year": str(tax_year),
                                "expense_account_hint": "payroll",
                            },
                        )
                    )
                self._year_end_processed.add(year_key)

            eligible_vendors = self._eligible_1099_vendors(business_key, vendors)
            if eligible_vendors:
                provider_id = self._find_vendor_id(
                    config.payroll_vendor or config.tax_authority, vendors
                )
                for vendor in eligible_vendors:
                    vendor_id_raw = vendor.get("id")
                    try:
                        vendor_id = UUID(str(vendor_id_raw))
                    except (TypeError, ValueError):
                        continue
                    filing_key = (business_key, tax_year, vendor_id)
                    if filing_key in self._form_1099_filed:
                        continue
                    filing_vendor_id = provider_id or vendor_id
                    vendor_name = (
                        vendor.get("display_name") or vendor.get("name", "")
                    )
                    if filing_vendor_id:
                        transactions.append(
                            GeneratedTransaction(
                                transaction_type=TransactionType.BILL,
                                description=(
                                    f"1099-NEC processing - {vendor_name} {tax_year}"
                                ),
                                amount=Decimal("7.50"),
                                vendor_id=filing_vendor_id,
                                metadata={
                                    "compliance_filing": "1099_nec",
                                    "tax_year": str(tax_year),
                                    "recipient_vendor_id": str(vendor_id),
                                    "recipient_vendor_name": str(vendor_name),
                                    "expense_account_hint": "payroll",
                                },
                            )
                        )
                        self._form_1099_filed.add(filing_key)

        return transactions


@dataclass(frozen=True)
class QuarterlyTaxConfig:
    """Quarterly estimated tax configuration."""

    entity_type: str
    estimated_annual_income: Decimal
    estimated_tax_rate: Decimal
    tax_vendor: str | None


@dataclass(frozen=True)
class QuarterlyTaxAction:
    """Action for quarterly estimated tax workflow."""

    action: str  # "create" or "pay"
    tax_year: int
    quarter: int
    due_date: date
    estimated_income: Decimal
    estimated_tax: Decimal
    tax_vendor: str | None


class QuarterlyTaxScheduler:
    """Schedule quarterly estimated tax actions."""

    def __init__(self, tax_by_business: dict[str, QuarterlyTaxConfig]) -> None:
        self._tax_by_business = tax_by_business
        self._created: set[tuple[str, int, int]] = set()
        self._paid: set[tuple[str, int, int]] = set()
        self._logger = logger.bind(component="quarterly_tax_scheduler")

    @staticmethod
    def _due_dates_for_tax_year(tax_year: int) -> dict[int, date]:
        return {
            1: date(tax_year, 4, 15),
            2: date(tax_year, 6, 15),
            3: date(tax_year, 9, 15),
            4: date(tax_year + 1, 1, 15),
        }

    @staticmethod
    def _quarter_amounts(config: QuarterlyTaxConfig) -> tuple[Decimal, Decimal]:
        quarter_income = (config.estimated_annual_income / Decimal("4")).quantize(
            Decimal("0.01")
        )
        quarter_tax = (quarter_income * config.estimated_tax_rate).quantize(
            Decimal("0.01")
        )
        return quarter_income, quarter_tax

    def mark_created(self, business_key: str, tax_year: int, quarter: int) -> None:
        self._created.add((business_key, tax_year, quarter))

    def mark_paid(self, business_key: str, tax_year: int, quarter: int) -> None:
        self._paid.add((business_key, tax_year, quarter))

    def get_actions(
        self,
        business_key: str,
        current_date: date,
    ) -> list[QuarterlyTaxAction]:
        config = self._tax_by_business.get(business_key)
        if not config:
            return []

        actions: list[QuarterlyTaxAction] = []
        quarter_income, quarter_tax = self._quarter_amounts(config)

        for tax_year in (current_date.year - 1, current_date.year):
            for quarter, due_date in self._due_dates_for_tax_year(tax_year).items():
                create_date = due_date - timedelta(days=14)
                key = (business_key, tax_year, quarter)

                if current_date == create_date and key not in self._created:
                    actions.append(
                        QuarterlyTaxAction(
                            action="create",
                            tax_year=tax_year,
                            quarter=quarter,
                            due_date=due_date,
                            estimated_income=quarter_income,
                            estimated_tax=quarter_tax,
                            tax_vendor=config.tax_vendor,
                        )
                    )

                if current_date == due_date and key not in self._paid:
                    actions.append(
                        QuarterlyTaxAction(
                            action="pay",
                            tax_year=tax_year,
                            quarter=quarter,
                            due_date=due_date,
                            estimated_income=quarter_income,
                            estimated_tax=quarter_tax,
                            tax_vendor=config.tax_vendor,
                        )
                    )

        if actions:
            self._logger.info(
                "quarterly_tax_actions",
                business=business_key,
                date=current_date.isoformat(),
                actions=len(actions),
            )

        return actions


# ============================================================================
# BUSINESS TRANSACTION PATTERNS
# ============================================================================

BUSINESS_PATTERNS: dict[str, list[TransactionPattern]] = {
    "craig": [
        # Landscaping Services
        TransactionPattern(
            TransactionType.INVOICE,
            "Lawn maintenance - {location}",
            Decimal("75.00"), Decimal("250.00"),
            probability=0.7,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.INVOICE,
            "Landscaping project - {project_type}",
            Decimal("500.00"), Decimal("3500.00"),
            probability=0.3,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Plant supplies - {supplier}",
            Decimal("150.00"), Decimal("800.00"),
            probability=0.4,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Equipment rental",
            Decimal("100.00"), Decimal("400.00"),
            probability=0.2,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Fuel for vehicles",
            Decimal("80.00"), Decimal("200.00"),
            probability=0.5,
        ),
        TransactionPattern(
            TransactionType.PAYMENT_RECEIVED,
            "Payment from {customer}",
            Decimal("0"), Decimal("0"),  # Will match existing invoices
            probability=0.4,
        ),
    ],
    "tony": [
        # Pizzeria - time-of-day aware patterns for realistic restaurant activity
        # Lunch service (lower volume, daytime crowd)
        TransactionPattern(
            TransactionType.CASH_SALE,
            "Lunch service - pizza sales",
            Decimal("400.00"), Decimal("1200.00"),
            probability=0.7,
            phase_multipliers={"morning": 0.3, "lunch": 1.5, "afternoon": 0.8},
            active_hours=(11, 14),  # 11 AM - 2 PM
        ),
        # Dinner rush (peak activity)
        TransactionPattern(
            TransactionType.CASH_SALE,
            "Dinner service - pizza sales",
            Decimal("1200.00"), Decimal("3500.00"),
            probability=0.95,
            weekend_boost=1.4,
            phase_multipliers={"evening": 2.5},  # Peak dinner rush
            active_hours=(17, 21),  # 5 PM - 9 PM
        ),
        # Late-night (reduced but active)
        TransactionPattern(
            TransactionType.CASH_SALE,
            "Late night - pizza sales",
            Decimal("600.00"), Decimal("1800.00"),
            probability=0.6,
            weekend_boost=1.8,  # Busier weekend nights
            phase_multipliers={"night": 1.5},
            active_hours=(21, 24),  # 9 PM - midnight
        ),
        # Catering orders (unchanged - not time-sensitive)
        TransactionPattern(
            TransactionType.INVOICE,
            "Catering order - {event_type}",
            Decimal("200.00"), Decimal("1200.00"),
            probability=0.4,
        ),
        # Bills (unchanged - not time-sensitive)
        TransactionPattern(
            TransactionType.BILL,
            "Food supplies - {supplier}",
            Decimal("400.00"), Decimal("1500.00"),
            probability=0.6,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Beverage inventory",
            Decimal("150.00"), Decimal("500.00"),
            probability=0.3,
        ),
        TransactionPattern(
            TransactionType.PAYMENT_RECEIVED,
            "Payment from {customer}",
            Decimal("0"), Decimal("0"),
            probability=0.5,
        ),
    ],
    "maya": [
        # Tech Consulting - high value, lower volume
        TransactionPattern(
            TransactionType.INVOICE,
            "IT consulting - {hours} hours",
            Decimal("800.00"), Decimal("4800.00"),
            probability=0.5,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.INVOICE,
            "Website development - {client}",
            Decimal("2000.00"), Decimal("8000.00"),
            probability=0.2,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.INVOICE,
            "Monthly retainer - {client}",
            Decimal("1500.00"), Decimal("5000.00"),
            probability=0.15,  # Monthly
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Cloud services - AWS/Azure",
            Decimal("100.00"), Decimal("500.00"),
            probability=0.1,  # Monthly
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Software subscription",
            Decimal("50.00"), Decimal("300.00"),
            probability=0.1,
        ),
        TransactionPattern(
            TransactionType.PAYMENT_RECEIVED,
            "Payment from {customer}",
            Decimal("0"), Decimal("0"),
            probability=0.3,
        ),
    ],
    "chen": [
        # Dental Practice
        TransactionPattern(
            TransactionType.INVOICE,
            "Dental cleaning and exam - {patient}",
            Decimal("150.00"), Decimal("350.00"),
            probability=0.8,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.INVOICE,
            "Dental procedure - {procedure}",
            Decimal("300.00"), Decimal("2500.00"),
            probability=0.4,
            weekday_only=True,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Dental supplies - {supplier}",
            Decimal("200.00"), Decimal("1200.00"),
            probability=0.3,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Lab services - {lab}",
            Decimal("100.00"), Decimal("600.00"),
            probability=0.2,
        ),
        TransactionPattern(
            TransactionType.PAYMENT_RECEIVED,
            "Insurance payment - {payer}",
            Decimal("0"), Decimal("0"),
            probability=0.6,
        ),
        TransactionPattern(
            TransactionType.PAYMENT_RECEIVED,
            "Patient payment - {patient}",
            Decimal("0"), Decimal("0"),
            probability=0.4,
        ),
    ],
    "marcus": [
        # Real Estate - low volume, high value
        TransactionPattern(
            TransactionType.INVOICE,
            "Commission - {property_address}",
            Decimal("5000.00"), Decimal("25000.00"),
            probability=0.15,  # Closings are infrequent
        ),
        TransactionPattern(
            TransactionType.INVOICE,
            "Referral fee",
            Decimal("500.00"), Decimal("2000.00"),
            probability=0.1,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "MLS subscription",
            Decimal("299.00"), Decimal("299.00"),
            probability=0.03,  # Monthly
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Marketing materials",
            Decimal("200.00"), Decimal("1500.00"),
            probability=0.2,
        ),
        TransactionPattern(
            TransactionType.BILL,
            "Professional photography",
            Decimal("150.00"), Decimal("400.00"),
            probability=0.25,
        ),
        TransactionPattern(
            TransactionType.PAYMENT_RECEIVED,
            "Commission payment",
            Decimal("0"), Decimal("0"),
            probability=0.2,
        ),
    ],
}

# ============================================================================
# BUSINESS SEASONALITY
# ============================================================================
# Maps business key to month-specific multipliers.
# Months not listed default to 1.0 (no change).
# Values > 1.0 = busier than average, < 1.0 = slower than average.

BUSINESS_SEASONALITY: dict[str, dict[int, float]] = {
    "craig": {
        # Peak: April-September (landscaping high season)
        4: 1.5, 5: 1.8, 6: 2.0, 7: 2.0, 8: 1.8, 9: 1.5,
        # Shoulder: March, October, November
        3: 1.0, 10: 0.8, 11: 0.6,
        # Slow: December-February (winter dormancy)
        12: 0.3, 1: 0.2, 2: 0.25,
    },
    "tony": {
        # Low seasonality - slight holiday boost
        11: 1.1, 12: 1.15, 2: 1.1,  # Thanksgiving, Christmas, Valentine's
    },
    "maya": {
        # Q4 budget spending, Q1 new initiatives
        1: 1.5, 2: 1.4, 10: 1.6, 11: 1.8,
        12: 0.7,  # Holiday freeze
    },
    "chen": {
        # Summer breaks (families scheduling), year-end insurance rush
        6: 1.5, 7: 1.6, 11: 1.7, 12: 1.8,
        1: 0.5, 2: 0.6,  # Post-holiday slow
    },
    "marcus": {
        # Spring/summer home-buying season
        4: 1.4, 5: 1.8, 6: 2.0, 7: 1.8, 8: 1.5,
        3: 1.0, 9: 1.0, 10: 0.8,
        # Winter slowdown
        11: 0.4, 12: 0.3, 1: 0.25, 2: 0.3,
    },
}

# ============================================================================
# BUSINESS DAY-OF-WEEK PATTERNS
# ============================================================================
# Maps business key to day-of-week multipliers (defaults).
# Persona YAML `day_patterns` can override these values.
# Days: 0=Monday, 1=Tuesday, ..., 6=Sunday
# Days not listed default to 1.0 (no change).
# Values > 1.0 = busier than average, < 1.0 = slower than average.

DEFAULT_BUSINESS_DAY_PATTERNS: dict[str, dict[int, float]] = {
    "tony": {
        # Restaurant: Thu-Sat peaks, Mon-Wed slower
        0: 0.7,  # Monday
        1: 0.8,  # Tuesday
        2: 0.9,  # Wednesday
        3: 1.2,  # Thursday
        4: 1.3,  # Friday
        5: 1.5,  # Saturday
        6: 0.9,  # Sunday
    },
    "chen": {
        # Dental: Tue-Thu peak, weekends closed/slow
        0: 0.9,  # Monday
        1: 1.1,  # Tuesday
        2: 1.2,  # Wednesday
        3: 1.1,  # Thursday
        4: 0.9,  # Friday
        5: 0.3,  # Saturday (limited hours)
        6: 0.0,  # Sunday (closed)
    },
    "marcus": {
        # Real Estate: Thu-Fri closings, Sat-Sun showings
        0: 0.7,  # Monday
        1: 0.9,  # Tuesday
        2: 1.0,  # Wednesday
        3: 1.2,  # Thursday (closings)
        4: 1.3,  # Friday (closings)
        5: 1.4,  # Saturday (showings)
        6: 1.2,  # Sunday (showings)
    },
    "craig": {
        # Landscaping: Tue-Thu peak, weekends slow
        0: 0.9,  # Monday
        1: 1.1,  # Tuesday
        2: 1.2,  # Wednesday
        3: 1.1,  # Thursday
        4: 1.0,  # Friday
        5: 0.4,  # Saturday
        6: 0.3,  # Sunday
    },
    "maya": {
        # Tech Consulting: Mon-Thu busy, Fri lighter
        0: 1.1,  # Monday
        1: 1.2,  # Tuesday
        2: 1.2,  # Wednesday
        3: 1.1,  # Thursday
        4: 0.8,  # Friday
        5: 0.2,  # Saturday
        6: 0.1,  # Sunday
    },
}


def get_business_day_patterns() -> dict[str, dict[int, float]]:
    """Get business day-of-week multipliers, merged with persona overrides."""
    merged = {key: days.copy() for key, days in DEFAULT_BUSINESS_DAY_PATTERNS.items()}
    overrides = load_persona_day_patterns()

    for business_key, days in overrides.items():
        if business_key in merged:
            merged[business_key] = {**merged[business_key], **days}
        else:
            merged[business_key] = days.copy()

    return merged

# Sample data for template substitution
TEMPLATE_DATA = {
    "location": [
        "Front yard",
        "Backyard",
        "Commercial property",
        "Apartment complex",
        "HOA common areas",
    ],
    "project_type": [
        "Spring cleanup",
        "Mulching",
        "Tree trimming",
        "Irrigation install",
        "Patio installation",
    ],
    "supplier": ["Green Valley Nursery", "Home Depot", "Local supplier"],
    "event_type": ["Birthday party", "Corporate lunch", "School event", "Sports team"],
    "hours": ["8", "16", "24", "32", "40"],
    "client": ["Local business", "Startup", "Healthcare client", "Retail store"],
    "patient": ["Smith family", "Garcia family", "New patient"],
    "procedure": ["Filling", "Crown", "Root canal", "Extraction", "Whitening"],
    "lab": ["Atlas Dental Lab", "Quality Dental Lab"],
    "payer": ["BlueCross", "Delta Dental", "Aetna"],
    "property_address": [
        "123 Oak St",
        "456 Maple Ave",
        "789 Pine Rd",
        "321 Cedar Ln",
    ],
    "customer": ["Customer payment"],  # Generic
}


class TransactionGenerator:
    """Generates realistic daily transactions for each business."""

    _AGING_BUCKETS: tuple[tuple[int, int | None, float], ...] = (
        (0, 30, 0.80),
        (31, 60, 0.60),
        (61, 90, 0.40),
        (91, 120, 0.20),
        (121, None, 0.05),
    )

    def __init__(
        self,
        seed: int | None = None,
        inflation: InflationModel | None = None,
    ):
        """Initialize with optional random seed for reproducibility."""
        self._rng = random.Random(seed)
        self._logger = logger.bind(component="transaction_generator")
        self._day_patterns = get_business_day_patterns()
        self._inflation = inflation or get_inflation_model()
        self._holiday_calendar = load_holiday_calendar()
        self._recurring_scheduler = RecurringTransactionScheduler(
            self._load_recurring_transactions()
        )
        self._payroll_generator = PayrollGenerator(
            self._load_employee_configs(),
            self._load_payroll_configs(),
            self._load_industries(),
            inflation=self._inflation,
        )
        self._quarterly_tax_scheduler = QuarterlyTaxScheduler(
            self._load_tax_configs()
        )
        financing = self._load_financing_configs()
        self._financing_scheduler = FinancingScheduler(
            financing["term_loans"],
            financing["lines_of_credit"],
            financing["equipment_financing"],
            rng=self._rng,
        )

    def _load_recurring_transactions(
        self,
    ) -> dict[str, list[RecurringTransactionSpec]]:
        """Load and normalize recurring transactions from persona configs."""
        raw = load_persona_recurring_transactions()
        recurring: dict[str, list[RecurringTransactionSpec]] = {}

        for business_key, items in raw.items():
            specs: list[RecurringTransactionSpec] = []
            for item in items:
                try:
                    amount = Decimal(str(item["amount"]))
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Recurring amount invalid for {business_key}: {item!r}"
                    ) from exc

                day_of_month = int(item["day_of_month"])
                anniversary_date = item.get("anniversary_date")
                interval_months = int(item.get("interval_months", 1))

                specs.append(
                    RecurringTransactionSpec(
                        name=item["name"],
                        vendor=item["vendor"],
                        amount=amount,
                        day_of_month=day_of_month,
                        anniversary_date=anniversary_date,
                        category=item.get("category"),
                        interval_months=interval_months,
                    )
                )

            if specs:
                recurring[business_key] = specs

        return recurring

    def _load_employee_configs(self) -> dict[str, list[EmployeeSpec]]:
        """Load and normalize employee configs from persona files."""
        raw = load_persona_employees()
        employees_by_business: dict[str, list[EmployeeSpec]] = {}

        for business_key, items in raw.items():
            specs: list[EmployeeSpec] = []
            for item in items:
                try:
                    pay_rate = Decimal(str(item["pay_rate"]))
                    hours = Decimal(str(item["hours_per_week"]))
                    count = int(item["count"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Employee config invalid for {business_key}: {item!r}"
                    ) from exc

                specs.append(
                    EmployeeSpec(
                        role=str(item["role"]),
                        count=count,
                        pay_rate=pay_rate,
                        hours_per_week=hours,
                    )
                )

            if specs:
                employees_by_business[business_key] = specs

        return employees_by_business

    def _load_payroll_configs(self) -> dict[str, PayrollConfig]:
        """Load payroll configs, defaulting where employees exist."""
        raw = load_persona_payroll_configs()
        employees = load_persona_employees()
        payroll_by_business: dict[str, PayrollConfig] = {}

        for business_key in set(employees.keys()) | set(raw.keys()):
            config = raw.get(business_key, {})
            frequency = str(config.get("frequency", "bi-weekly"))
            pay_day = config.get("pay_day", "friday")
            payroll_vendor = config.get("payroll_vendor")
            tax_authority = config.get("tax_authority")

            payroll_by_business[business_key] = PayrollConfig(
                frequency=frequency,
                pay_day=pay_day,
                payroll_vendor=str(payroll_vendor) if payroll_vendor is not None else None,
                tax_authority=str(tax_authority) if tax_authority is not None else None,
            )

        return payroll_by_business

    def _load_industries(self) -> dict[str, str]:
        """Load industries from persona files."""
        return load_persona_industries()

    def _load_tax_configs(self) -> dict[str, QuarterlyTaxConfig]:
        """Load quarterly tax configs from persona files."""
        raw = load_persona_tax_configs()
        tax_by_business: dict[str, QuarterlyTaxConfig] = {}

        for business_key, config in raw.items():
            try:
                annual_income = Decimal(str(config["estimated_annual_income"]))
                tax_rate = Decimal(str(config["estimated_tax_rate"]))
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(
                    f"Tax config invalid for {business_key}: {config!r}"
                ) from exc

            entity_type = str(config.get("entity_type", "sole_proprietor"))
            tax_vendor = config.get("tax_vendor") or "IRS Estimated Taxes"

            tax_by_business[business_key] = QuarterlyTaxConfig(
                entity_type=entity_type,
                estimated_annual_income=annual_income,
                estimated_tax_rate=tax_rate,
                tax_vendor=str(tax_vendor) if tax_vendor is not None else None,
            )

        return tax_by_business

    def _load_financing_configs(self) -> dict[str, dict[str, list[Any]]]:
        """Load financing configs from persona files."""
        raw = load_persona_financing_configs()
        term_loans: dict[str, list[LoanSpec]] = {}
        lines_of_credit: dict[str, list[LineOfCreditSpec]] = {}
        equipment_financing: dict[str, list[EquipmentFinancingSpec]] = {}

        for business_key, config in raw.items():
            term_specs: list[LoanSpec] = []
            for item in config.get("term_loans", []):
                try:
                    principal = Decimal(str(item["principal"]))
                    rate = Decimal(str(item["rate"]))
                    term_months = int(item["term_months"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Financing term_loan invalid for {business_key}: {item!r}"
                    ) from exc
                if term_months < 1:
                    raise ValueError(
                        f"Financing term_loan term_months must be >= 1 for {business_key}: {item!r}"
                    )
                payment_day = int(item.get("payment_day", 1))
                if not (1 <= payment_day <= 31):
                    raise ValueError(
                        f"Financing term_loan payment_day must be 1-31 for {business_key}: {item!r}"
                    )
                lender = str(item.get("lender") or "Bank")
                name = str(item.get("name") or "Term Loan")
                start_date = item.get("start_date")

                adjustments = []
                for adj in item.get("rate_adjustments", []):
                    try:
                        effective_date = adj["effective_date"]
                        rate_adj = Decimal(str(adj["rate"]))
                    except (KeyError, ValueError, TypeError) as exc:
                        raise ValueError(
                            "Financing term_loan rate adjustment invalid for "
                            f"{business_key}: {adj!r}"
                        ) from exc
                    adjustments.append(
                        FinancingRateAdjustment(
                            effective_date=effective_date,
                            rate=rate_adj,
                        )
                    )
                adjustments.sort(key=lambda entry: entry.effective_date)

                term_specs.append(
                    LoanSpec(
                        name=name,
                        principal=principal,
                        annual_rate=rate,
                        term_months=term_months,
                        payment_day=payment_day,
                        lender=lender,
                        loan_type="term_loan",
                        start_date=start_date,
                        rate_adjustments=tuple(adjustments),
                    )
                )

            loc_specs: list[LineOfCreditSpec] = []
            for item in config.get("lines_of_credit", []):
                try:
                    balance = Decimal(str(item["balance"]))
                    rate = Decimal(str(item["rate"]))
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Financing line_of_credit invalid for {business_key}: {item!r}"
                    ) from exc
                billing_day = int(item.get("billing_day", 1))
                if not (1 <= billing_day <= 31):
                    raise ValueError(
                        "Financing line_of_credit billing_day must be 1-31 "
                        f"for {business_key}: {item!r}"
                    )
                lender = str(item.get("lender") or "Bank")
                name = str(item.get("name") or "Line of Credit")
                start_date = item.get("start_date")

                adjustments = []
                for adj in item.get("rate_adjustments", []):
                    try:
                        effective_date = adj["effective_date"]
                        rate_adj = Decimal(str(adj["rate"]))
                    except (KeyError, ValueError, TypeError) as exc:
                        raise ValueError(
                            "Financing line_of_credit rate adjustment invalid "
                            f"for {business_key}: {adj!r}"
                        ) from exc
                    adjustments.append(
                        FinancingRateAdjustment(
                            effective_date=effective_date,
                            rate=rate_adj,
                        )
                    )
                adjustments.sort(key=lambda entry: entry.effective_date)

                balance_events = []
                for event in item.get("balance_events", []):
                    try:
                        effective_date = event["effective_date"]
                        event_balance = Decimal(str(event["balance"]))
                    except (KeyError, ValueError, TypeError) as exc:
                        raise ValueError(
                            "Financing line_of_credit balance event invalid for "
                            f"{business_key}: {event!r}"
                        ) from exc
                    balance_events.append(
                        BalanceEvent(
                            effective_date=effective_date,
                            balance=event_balance,
                        )
                    )
                balance_events.sort(key=lambda entry: entry.effective_date)

                loc_specs.append(
                    LineOfCreditSpec(
                        name=name,
                        annual_rate=rate,
                        balance=balance,
                        billing_day=billing_day,
                        lender=lender,
                        start_date=start_date,
                        rate_adjustments=tuple(adjustments),
                        balance_events=tuple(balance_events),
                    )
                )

            equip_specs: list[EquipmentFinancingSpec] = []
            for item in config.get("equipment_financing", []):
                try:
                    principal = Decimal(str(item["principal"]))
                    rate = Decimal(str(item["rate"]))
                    term_months = int(item["term_months"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Financing equipment invalid for {business_key}: {item!r}"
                    ) from exc
                if term_months < 1:
                    raise ValueError(
                        f"Financing equipment term_months must be >= 1 for {business_key}: {item!r}"
                    )
                payment_day = int(item.get("payment_day", 1))
                if not (1 <= payment_day <= 31):
                    raise ValueError(
                        f"Financing equipment payment_day must be 1-31 for {business_key}: {item!r}"
                    )
                lender = str(item.get("lender") or "Equipment Lender")
                name = str(item.get("name") or "Equipment Financing")
                start_date = item.get("start_date")
                decision = str(item.get("decision", "auto")).strip().lower()
                decision_rate_threshold = item.get("decision_rate_threshold")
                decision_principal_threshold = item.get("decision_principal_threshold")
                lease_probability = item.get("lease_probability")
                purchase_probability = item.get("purchase_probability")

                adjustments = []
                for adj in item.get("rate_adjustments", []):
                    try:
                        effective_date = adj["effective_date"]
                        rate_adj = Decimal(str(adj["rate"]))
                    except (KeyError, ValueError, TypeError) as exc:
                        raise ValueError(
                            "Financing equipment rate adjustment invalid for "
                            f"{business_key}: {adj!r}"
                        ) from exc
                    adjustments.append(
                        FinancingRateAdjustment(
                            effective_date=effective_date,
                            rate=rate_adj,
                        )
                    )
                adjustments.sort(key=lambda entry: entry.effective_date)

                equip_specs.append(
                    EquipmentFinancingSpec(
                        name=name,
                        principal=principal,
                        annual_rate=rate,
                        term_months=term_months,
                        payment_day=payment_day,
                        lender=lender,
                        start_date=start_date,
                        rate_adjustments=tuple(adjustments),
                        decision=decision or "auto",
                        decision_rate_threshold=Decimal(str(decision_rate_threshold))
                        if decision_rate_threshold is not None
                        else None,
                        decision_principal_threshold=Decimal(str(decision_principal_threshold))
                        if decision_principal_threshold is not None
                        else None,
                        lease_probability=float(lease_probability)
                        if lease_probability is not None
                        else None,
                        purchase_probability=float(purchase_probability)
                        if purchase_probability is not None
                        else None,
                    )
                )

            if term_specs:
                term_loans[business_key] = term_specs
            if loc_specs:
                lines_of_credit[business_key] = loc_specs
            if equip_specs:
                equipment_financing[business_key] = equip_specs

        return {
            "term_loans": term_loans,
            "lines_of_credit": lines_of_credit,
            "equipment_financing": equipment_financing,
        }

    def generate_recurring_transactions(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
    ) -> list[GeneratedTransaction]:
        """Generate recurring transactions for a business on the given date."""
        transactions = self._recurring_scheduler.get_due_transactions(
            business_key=business_key,
            current_date=current_date,
            vendors=vendors,
        )
        for tx in transactions:
            tx.amount = self._inflation.apply(tx.amount, current_date)
        return transactions

    def generate_payroll_transactions(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
    ) -> list[GeneratedTransaction]:
        """Generate payroll and tax deposit transactions for a business."""
        return self._payroll_generator.get_due_transactions(
            business_key=business_key,
            current_date=current_date,
            vendors=vendors,
        )

    def generate_financing_transactions(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
    ) -> list[GeneratedTransaction]:
        """Generate financing interest transactions for a business."""
        return self._financing_scheduler.get_due_transactions(
            business_key=business_key,
            current_date=current_date,
            vendors=vendors,
        )

    def generate_quarterly_tax_actions(
        self,
        business_key: str,
        current_date: date,
    ) -> list[QuarterlyTaxAction]:
        """Generate quarterly estimated tax actions for a business."""
        return self._quarterly_tax_scheduler.get_actions(
            business_key=business_key,
            current_date=current_date,
        )

    def mark_quarterly_tax_created(
        self,
        business_key: str,
        tax_year: int,
        quarter: int,
    ) -> None:
        """Mark a quarterly tax estimate as created."""
        self._quarterly_tax_scheduler.mark_created(business_key, tax_year, quarter)

    def mark_quarterly_tax_paid(
        self,
        business_key: str,
        tax_year: int,
        quarter: int,
    ) -> None:
        """Mark a quarterly tax estimate as paid."""
        self._quarterly_tax_scheduler.mark_paid(business_key, tax_year, quarter)

    def _fill_template(self, template: str) -> str:
        """Fill in template placeholders with random data."""
        result = template
        for key, values in TEMPLATE_DATA.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, self._rng.choice(values))
        return result

    def _get_seasonal_multiplier(
        self,
        business_key: str,
        month: int,
        pattern: TransactionPattern,
    ) -> float:
        """Get seasonal multiplier for a business/pattern in a given month.

        Pattern-specific seasonal_multipliers override business-wide seasonality.
        Returns 1.0 if no seasonality is defined (backward-compatible).

        Args:
            business_key: The business identifier (craig, tony, etc.)
            month: Month number (1-12)
            pattern: The transaction pattern (may have its own seasonal_multipliers)

        Returns:
            Multiplier to apply to base probability (1.0 = no change)
        """
        # Pattern-specific override takes precedence
        if pattern.seasonal_multipliers and month in pattern.seasonal_multipliers:
            return pattern.seasonal_multipliers[month]

        # Fall back to business-wide seasonality
        return BUSINESS_SEASONALITY.get(business_key, {}).get(month, 1.0)

    def _get_holiday_multiplier(self, business_key: str, current_date: date) -> float:
        """Get holiday/event multiplier for a business on a given date."""
        multiplier, _ = self.get_holiday_context(business_key, current_date)
        return multiplier

    def get_holiday_context(
        self,
        business_key: str,
        current_date: date,
    ) -> tuple[float, list[str]]:
        """Return holiday multiplier and active holiday names for a date."""
        multiplier = 1.0
        names: list[str] = []
        for holiday in self._holiday_calendar:
            if not holiday.matches(current_date):
                continue
            names.append(holiday.name)
            value = holiday.modifier_for(business_key)
            if value <= 0:
                return 0.0, names
            multiplier *= value
        return multiplier, names

    def _get_day_multiplier(self, business_key: str, weekday: int) -> float:
        """Get day-of-week multiplier for a business.

        Args:
            business_key: Business identifier (craig, tony, etc.)
            weekday: Day of week (0=Monday, 6=Sunday)

        Returns:
            Multiplier (1.0 = no change, default for unknown business/day)
        """
        return self._day_patterns.get(business_key, {}).get(weekday, 1.0)

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    def _invoice_days_overdue(
        self,
        invoice: dict[str, Any],
        current_date: date,
    ) -> int | None:
        due_date = self._parse_date(invoice.get("due_date")) or self._parse_date(
            invoice.get("invoice_date")
        )
        if not due_date:
            return None
        return (current_date - due_date).days

    def _payment_probability_for_invoice(
        self,
        invoice: dict[str, Any],
        current_date: date,
    ) -> float:
        days_overdue = self._invoice_days_overdue(invoice, current_date)
        if days_overdue is None:
            return 0.0
        if days_overdue < 0:
            days_overdue = 0
        for minimum, maximum, probability in self._AGING_BUCKETS:
            if maximum is None:
                return probability
            if minimum <= days_overdue <= maximum:
                return probability
        return 0.0

    def _should_generate(
        self,
        pattern: TransactionPattern,
        current_date: date,
        current_hour: int | None = None,
        current_phase: str | None = None,
        business_key: str | None = None,
        base_probability: float | None = None,
    ) -> bool:
        """Determine if a transaction should be generated based on probability.

        Args:
            pattern: The transaction pattern to evaluate
            current_date: The simulation date
            current_hour: Optional hour (0-23) for time-based filtering
            current_phase: Optional phase name for phase multipliers
            business_key: Optional business identifier for seasonal multipliers
        """
        weekday = current_date.weekday()
        is_weekend = weekday >= 5

        # Skip weekday-only transactions on weekends
        if pattern.weekday_only and is_weekend:
            return False

        # Check active hours constraint
        if current_hour is not None and pattern.active_hours:
            start_h, end_h = pattern.active_hours
            if start_h <= end_h:
                # Normal range (e.g., 9-17)
                if not (start_h <= current_hour < end_h):
                    return False
            else:
                # Wraps midnight (e.g., 20-2)
                if not (current_hour >= start_h or current_hour < end_h):
                    return False

        # Calculate probability with modifiers
        probability = base_probability if base_probability is not None else pattern.probability

        # Apply day-of-week multiplier (business-wide pattern)
        if business_key:
            probability *= self._get_day_multiplier(business_key, weekday)

        # Apply weekend boost (pattern-specific override)
        if is_weekend:
            probability *= pattern.weekend_boost

        # Apply phase multiplier
        if current_phase and pattern.phase_multipliers:
            probability *= pattern.phase_multipliers.get(current_phase, 1.0)

        # Apply seasonal multiplier
        if business_key:
            seasonal_mult = self._get_seasonal_multiplier(
                business_key, current_date.month, pattern
            )
            probability *= seasonal_mult

        # Apply holiday/event multiplier
        if business_key and self._holiday_calendar:
            holiday_multiplier = self._get_holiday_multiplier(business_key, current_date)
            if holiday_multiplier <= 0:
                return False
            probability *= holiday_multiplier

        return self._rng.random() < probability

    @staticmethod
    def _is_hour_active(hour: int, active_hours: tuple[int, int]) -> bool:
        start_h, end_h = active_hours
        if start_h <= end_h:
            return start_h <= hour < end_h
        return hour >= start_h or hour < end_h

    @staticmethod
    def _get_phase_hours(phase_name: str | None) -> list[int]:
        if not phase_name:
            return []
        try:
            phase = DayPhase(phase_name)
        except ValueError:
            return []
        start_h, end_h = PHASE_TIMES[phase]
        if start_h <= end_h:
            return list(range(start_h, end_h))
        return list(range(start_h, 24)) + list(range(0, end_h))

    def _generate_amount(self, pattern: TransactionPattern, current_date: date) -> Decimal:
        """Generate a random amount within the pattern's range."""
        min_val = float(pattern.min_amount)
        max_val = float(pattern.max_amount)

        if min_val == max_val:
            return self._inflation.apply(pattern.min_amount, current_date)

        # Use triangular distribution (mode at lower end for realistic pricing)
        amount = self._rng.triangular(
            min_val, max_val, min_val + (max_val - min_val) * 0.3
        )
        # Round to 2 decimal places, nearest 0.05 for realism
        amount = round(amount / 0.05) * 0.05
        base_amount = Decimal(str(round(amount, 2)))
        return self._inflation.apply(base_amount, current_date)

    def generate_daily_transactions(
        self,
        business_key: str,
        current_date: date,
        customers: list[dict[str, Any]],
        vendors: list[dict[str, Any]],
        pending_invoices: list[dict[str, Any]] | None = None,
        current_hour: int | None = None,
        current_phase: str | None = None,
        hourly: bool = False,
    ) -> list[GeneratedTransaction]:
        """Generate transactions for a business for one day.

        Args:
            business_key: The business identifier (craig, tony, maya, chen, marcus)
            current_date: The simulation date
            customers: List of customer records from the API
            vendors: List of vendor records from the API
            pending_invoices: Optional list of unpaid invoices for payment generation
            current_hour: Optional hour (0-23) for time-based transaction patterns
            current_phase: Optional phase name (e.g., "evening") for phase multipliers
            hourly: If true, generate transactions per hour across the phase

        Returns:
            List of transactions to create
        """
        patterns = BUSINESS_PATTERNS.get(business_key, [])
        transactions: list[GeneratedTransaction] = []
        pending_pool = list(pending_invoices) if pending_invoices else []
        payable_pool: list[dict[str, Any]] = []

        if pending_pool:
            for invoice in pending_pool:
                probability = self._payment_probability_for_invoice(
                    invoice, current_date
                )
                if probability <= 0:
                    continue
                if self._rng.random() < probability:
                    payable_pool.append(invoice)

        def pop_pending_invoice() -> dict[str, Any] | None:
            if not payable_pool:
                return None
            idx = self._rng.randrange(len(payable_pool))
            invoice = payable_pool.pop(idx)
            if invoice in pending_pool:
                pending_pool.remove(invoice)
            return invoice

        def invoice_amount(invoice: dict[str, Any]) -> Decimal | None:
            for key in ("amount_due", "balance", "total_amount", "total"):
                if key in invoice and invoice.get(key) is not None:
                    try:
                        amount = Decimal(str(invoice[key]))
                    except (ValueError, TypeError):
                        continue
                    if amount > 0:
                        return amount
            return None

        if hourly:
            hours = self._get_phase_hours(current_phase)
            if not hours and current_hour is not None:
                hours = [current_hour]
            if not hours:
                return transactions

            pattern_hour_sets: list[tuple[TransactionPattern, set[int], float]] = []
            for pattern in patterns:
                if pattern.active_hours:
                    active_hours = [
                        hour
                        for hour in hours
                        if self._is_hour_active(hour, pattern.active_hours)
                    ]
                else:
                    active_hours = hours
                if not active_hours:
                    continue
                base_probability = pattern.probability / len(active_hours)
                pattern_hour_sets.append((pattern, set(active_hours), base_probability))

            for hour in hours:
                self._logger.debug(
                    "generating_transactions",
                    business=business_key,
                    date=current_date.isoformat(),
                    pattern_count=len(patterns),
                    hour=hour,
                    phase=current_phase,
                )

                hour_transactions: list[GeneratedTransaction] = []
                for pattern, active_hour_set, base_probability in pattern_hour_sets:
                    if hour not in active_hour_set:
                        continue
                    if not self._should_generate(
                        pattern,
                        current_date,
                        hour,
                        current_phase,
                        business_key,
                        base_probability=base_probability,
                    ):
                        continue

                    # Handle payment transactions specially
                    if pattern.transaction_type == TransactionType.PAYMENT_RECEIVED:
                        selected_invoice = pop_pending_invoice()
                        if selected_invoice:
                            amount = invoice_amount(selected_invoice)
                            invoice_id = selected_invoice.get("id")
                            if amount and invoice_id:
                                invoice_number = selected_invoice.get("invoice_number", "N/A")
                                customer_id_value = (
                                    UUID(selected_invoice["customer_id"])
                                    if selected_invoice.get("customer_id")
                                    else None
                                )
                                hour_transactions.append(
                                    GeneratedTransaction(
                                        transaction_type=pattern.transaction_type,
                                        description=f"Payment received - Invoice #{invoice_number}",
                                        amount=amount,
                                        customer_id=customer_id_value,
                                        metadata={"invoice_id": invoice_id},
                                    )
                                )
                        continue

                    # Generate regular transaction
                    description = self._fill_template(pattern.description_template)
                    amount = self._generate_amount(pattern, current_date)

                    # Assign customer or vendor
                    customer_id = None
                    vendor_id = None

                    if pattern.transaction_type in [
                        TransactionType.INVOICE,
                        TransactionType.CASH_SALE,
                    ]:
                        if customers:
                            customer = self._rng.choice(customers)
                            customer_id = UUID(customer["id"])
                    elif pattern.transaction_type == TransactionType.BILL and vendors:
                        vendor = self._rng.choice(vendors)
                        vendor_id = UUID(vendor["id"])

                    hour_transactions.append(
                        GeneratedTransaction(
                            transaction_type=pattern.transaction_type,
                            description=description,
                            amount=amount,
                            customer_id=customer_id,
                            vendor_id=vendor_id,
                        )
                    )

                self._logger.info(
                    "transactions_generated",
                    business=business_key,
                    count=len(hour_transactions),
                    hour=hour,
                    phase=current_phase,
                )
                transactions.extend(hour_transactions)

            return transactions

        self._logger.debug(
            "generating_transactions",
            business=business_key,
            date=current_date.isoformat(),
            pattern_count=len(patterns),
            hour=current_hour,
            phase=current_phase,
        )

        for pattern in patterns:
            if not self._should_generate(
                pattern, current_date, current_hour, current_phase, business_key
            ):
                continue

            # Handle payment transactions specially
            if pattern.transaction_type == TransactionType.PAYMENT_RECEIVED:
                selected_invoice = pop_pending_invoice()
                if selected_invoice:
                    amount = invoice_amount(selected_invoice)
                    invoice_id = selected_invoice.get("id")
                    if amount and invoice_id:
                        invoice_number = selected_invoice.get("invoice_number", "N/A")
                        customer_id_value = (
                            UUID(selected_invoice["customer_id"])
                            if selected_invoice.get("customer_id")
                            else None
                        )
                        transactions.append(
                            GeneratedTransaction(
                                transaction_type=pattern.transaction_type,
                                description=f"Payment received - Invoice #{invoice_number}",
                                amount=amount,
                                customer_id=customer_id_value,
                                metadata={"invoice_id": invoice_id},
                            )
                        )
                continue

            # Generate regular transaction
            description = self._fill_template(pattern.description_template)
            amount = self._generate_amount(pattern, current_date)

            # Assign customer or vendor
            customer_id = None
            vendor_id = None

            if pattern.transaction_type in [
                TransactionType.INVOICE,
                TransactionType.CASH_SALE,
            ]:
                if customers:
                    customer = self._rng.choice(customers)
                    customer_id = UUID(customer["id"])
            elif pattern.transaction_type == TransactionType.BILL and vendors:
                vendor = self._rng.choice(vendors)
                vendor_id = UUID(vendor["id"])

            transactions.append(GeneratedTransaction(
                transaction_type=pattern.transaction_type,
                description=description,
                amount=amount,
                customer_id=customer_id,
                vendor_id=vendor_id,
            ))

        self._logger.info(
            "transactions_generated",
            business=business_key,
            count=len(transactions),
        )

        return transactions

    def get_transaction_summary(
        self,
        transactions: list[GeneratedTransaction],
    ) -> dict[str, Any]:
        """Get a summary of generated transactions."""
        by_type: dict[str, int] = {}
        total_revenue = Decimal("0")
        total_expenses = Decimal("0")

        for tx in transactions:
            tx_type = tx.transaction_type.value
            by_type[tx_type] = by_type.get(tx_type, 0) + 1

            if tx.transaction_type in [
                TransactionType.INVOICE,
                TransactionType.CASH_SALE,
                TransactionType.PAYMENT_RECEIVED,
            ]:
                total_revenue += tx.amount
            elif tx.transaction_type in [
                TransactionType.BILL,
                TransactionType.BILL_PAYMENT,
            ]:
                total_expenses += tx.amount

        return {
            "count": len(transactions),
            "by_type": by_type,
            "total_revenue": str(total_revenue),
            "total_expenses": str(total_expenses),
        }


def create_transaction_generator(
    seed: int | None = None,
    inflation: InflationModel | None = None,
) -> TransactionGenerator:
    """Create a transaction generator instance."""
    return TransactionGenerator(seed=seed, inflation=inflation)
