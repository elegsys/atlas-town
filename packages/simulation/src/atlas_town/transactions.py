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
        # Pizzeria - high volume, low margin
        TransactionPattern(
            TransactionType.CASH_SALE,
            "Daily pizza sales",
            Decimal("800.00"), Decimal("2500.00"),
            probability=0.95,
            weekend_boost=1.3,  # Busier weekends
        ),
        TransactionPattern(
            TransactionType.INVOICE,
            "Catering order - {event_type}",
            Decimal("200.00"), Decimal("1200.00"),
            probability=0.4,
        ),
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

    def _should_generate(
        self,
        pattern: TransactionPattern,
        current_date: date,
    ) -> bool:
        """Determine if a transaction should be generated based on probability."""
        weekday = current_date.weekday()
        is_weekend = weekday >= 5

        # Skip weekday-only transactions on weekends
        if pattern.weekday_only and is_weekend:
            return False

        # Adjust probability for weekends
        probability = pattern.probability
        if is_weekend:
            probability *= pattern.weekend_boost

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
    ) -> list[GeneratedTransaction]:
        """Generate transactions for a business for one day.

        Args:
            business_key: The business identifier (craig, tony, maya, chen, marcus)
            current_date: The simulation date
            customers: List of customer records from the API
            vendors: List of vendor records from the API
            pending_invoices: Optional list of unpaid invoices for payment generation

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
        )

        for pattern in patterns:
            if not self._should_generate(pattern, current_date):
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
