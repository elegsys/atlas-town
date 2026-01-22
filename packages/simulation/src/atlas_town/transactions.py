"""Transaction generator for realistic daily business activity.

This module generates realistic transactions based on business type,
day of week, and seasonal patterns.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

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
    phase_multipliers: dict[str, float] | None = None  # e.g., {"evening": 2.5, "night": 1.5}
    active_hours: tuple[int, int] | None = None  # (start_hour, end_hour) - restricts when pattern is active
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
# Maps business key to day-of-week multipliers.
# Days: 0=Monday, 1=Tuesday, ..., 6=Sunday
# Days not listed default to 1.0 (no change).
# Values > 1.0 = busier than average, < 1.0 = slower than average.

BUSINESS_DAY_PATTERNS: dict[str, dict[int, float]] = {
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

# Sample data for template substitution
TEMPLATE_DATA = {
    "location": ["Front yard", "Backyard", "Commercial property", "Apartment complex", "HOA common areas"],
    "project_type": ["Spring cleanup", "Mulching", "Tree trimming", "Irrigation install", "Patio installation"],
    "supplier": ["Green Valley Nursery", "Home Depot", "Local supplier"],
    "event_type": ["Birthday party", "Corporate lunch", "School event", "Sports team"],
    "hours": ["8", "16", "24", "32", "40"],
    "client": ["Local business", "Startup", "Healthcare client", "Retail store"],
    "patient": ["Smith family", "Garcia family", "New patient"],
    "procedure": ["Filling", "Crown", "Root canal", "Extraction", "Whitening"],
    "lab": ["Atlas Dental Lab", "Quality Dental Lab"],
    "payer": ["BlueCross", "Delta Dental", "Aetna"],
    "property_address": ["123 Oak St", "456 Maple Ave", "789 Pine Rd", "321 Cedar Ln"],
    "customer": ["Customer payment"],  # Generic
}


class TransactionGenerator:
    """Generates realistic daily transactions for each business."""

    def __init__(self, seed: int | None = None):
        """Initialize with optional random seed for reproducibility."""
        self._rng = random.Random(seed)
        self._logger = logger.bind(component="transaction_generator")

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

    def _get_day_multiplier(self, business_key: str, weekday: int) -> float:
        """Get day-of-week multiplier for a business.

        Args:
            business_key: Business identifier (craig, tony, etc.)
            weekday: Day of week (0=Monday, 6=Sunday)

        Returns:
            Multiplier (1.0 = no change, default for unknown business/day)
        """
        return BUSINESS_DAY_PATTERNS.get(business_key, {}).get(weekday, 1.0)

    def _should_generate(
        self,
        pattern: TransactionPattern,
        current_date: date,
        current_hour: int | None = None,
        current_phase: str | None = None,
        business_key: str | None = None,
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
        probability = pattern.probability

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

        return self._rng.random() < probability

    def _generate_amount(self, pattern: TransactionPattern) -> Decimal:
        """Generate a random amount within the pattern's range."""
        min_val = float(pattern.min_amount)
        max_val = float(pattern.max_amount)

        if min_val == max_val:
            return pattern.min_amount

        # Use triangular distribution (mode at lower end for realistic pricing)
        amount = self._rng.triangular(min_val, max_val, min_val + (max_val - min_val) * 0.3)
        # Round to 2 decimal places, nearest 0.05 for realism
        amount = round(amount / 0.05) * 0.05
        return Decimal(str(round(amount, 2)))

    def generate_daily_transactions(
        self,
        business_key: str,
        current_date: date,
        customers: list[dict[str, Any]],
        vendors: list[dict[str, Any]],
        pending_invoices: list[dict[str, Any]] | None = None,
        current_hour: int | None = None,
        current_phase: str | None = None,
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

        Returns:
            List of transactions to create
        """
        patterns = BUSINESS_PATTERNS.get(business_key, [])
        transactions = []

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
                if pending_invoices:
                    # Pick a random invoice to pay
                    invoice = self._rng.choice(pending_invoices)
                    amount = Decimal(str(invoice.get("balance", invoice.get("total", "100.00"))))
                    transactions.append(GeneratedTransaction(
                        transaction_type=pattern.transaction_type,
                        description=f"Payment received - Invoice #{invoice.get('invoice_number', 'N/A')}",
                        amount=amount,
                        customer_id=UUID(invoice["customer_id"]) if invoice.get("customer_id") else None,
                        metadata={"invoice_id": invoice.get("id")},
                    ))
                continue

            # Generate regular transaction
            description = self._fill_template(pattern.description_template)
            amount = self._generate_amount(pattern)

            # Assign customer or vendor
            customer_id = None
            vendor_id = None

            if pattern.transaction_type in [TransactionType.INVOICE, TransactionType.CASH_SALE]:
                if customers:
                    customer = self._rng.choice(customers)
                    customer_id = UUID(customer["id"])
            elif pattern.transaction_type == TransactionType.BILL:
                if vendors:
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
        by_type = {}
        total_revenue = Decimal("0")
        total_expenses = Decimal("0")

        for tx in transactions:
            tx_type = tx.transaction_type.value
            by_type[tx_type] = by_type.get(tx_type, 0) + 1

            if tx.transaction_type in [TransactionType.INVOICE, TransactionType.CASH_SALE, TransactionType.PAYMENT_RECEIVED]:
                total_revenue += tx.amount
            elif tx.transaction_type in [TransactionType.BILL, TransactionType.BILL_PAYMENT]:
                total_expenses += tx.amount

        return {
            "count": len(transactions),
            "by_type": by_type,
            "total_revenue": str(total_revenue),
            "total_expenses": str(total_expenses),
        }


def create_transaction_generator(seed: int | None = None) -> TransactionGenerator:
    """Create a transaction generator instance."""
    return TransactionGenerator(seed)
