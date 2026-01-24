"""B2B transaction planning for cross-organization paired records."""

from __future__ import annotations

import calendar
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog

from atlas_town.config.personas_loader import load_persona_b2b_configs

logger = structlog.get_logger(__name__)

B2B_NAMESPACE = uuid5(NAMESPACE_URL, "atlas-town-b2b")

DEFAULT_FREQUENCY = "monthly"
DEFAULT_DAY_OF_MONTH = 10
DEFAULT_TERMS_DAYS = 30
DEFAULT_PAYMENT_FLOW = "same_day"  # "none" or "same_day"

DEFAULT_AMOUNT_RANGES_BY_OWNER = {
    "craig": (Decimal("300"), Decimal("2500")),
    "tony": (Decimal("150"), Decimal("1200")),
    "maya": (Decimal("1000"), Decimal("9000")),
    "chen": (Decimal("300"), Decimal("3500")),
    "marcus": (Decimal("800"), Decimal("12000")),
}


@dataclass(frozen=True)
class B2BCounterpartySpec:
    """Persona-configured B2B counterparty entry."""

    org_key: str
    relationship: str = "auto"  # vendor|customer|auto
    frequency: str = DEFAULT_FREQUENCY
    day_of_month: int | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    description: str | None = None
    invoice_terms_days: int = DEFAULT_TERMS_DAYS
    payment_flow: str = DEFAULT_PAYMENT_FLOW


@dataclass(frozen=True)
class B2BConfig:
    """Persona-level B2B configuration."""

    enabled: bool = True
    counterparties: tuple[B2BCounterpartySpec, ...] = ()


@dataclass(frozen=True)
class B2BPairSpec:
    """Resolved B2B relationship between seller and buyer."""

    seller_key: str
    buyer_key: str
    frequency: str = DEFAULT_FREQUENCY
    day_of_month: int = DEFAULT_DAY_OF_MONTH
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    description: str | None = None
    invoice_terms_days: int = DEFAULT_TERMS_DAYS
    payment_flow: str = DEFAULT_PAYMENT_FLOW


@dataclass(frozen=True)
class B2BPlannedPair:
    """Planned B2B transaction for a specific date."""

    pair_id: str
    seller_key: str
    buyer_key: str
    seller_org_id: UUID
    buyer_org_id: UUID
    seller_name: str
    buyer_name: str
    amount: Decimal
    description: str
    due_date: date
    payment_flow: str


def load_business_credentials() -> dict[str, dict[str, Any]]:
    """Load business credentials to map org keys to canonical names."""
    base_dir = Path(__file__).resolve().parents[2]
    creds_path = base_dir / "business_credentials.json"
    if not creds_path.exists():
        return {}
    try:
        data = json.loads(creds_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _normalize_name(name: str) -> str:
    return " ".join(name.replace("'", "").split()).strip().lower()


def _names_match(left: str, right: str) -> bool:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    return left_norm in right_norm or right_norm in left_norm


def build_b2b_note(
    pair_id: str,
    counterparty_org_id: UUID,
    counterparty_doc_id: str | None = None,
) -> str:
    """Build a metadata note string for B2B linkage."""
    parts = [
        f"b2b_pair_id={pair_id}",
        f"counterparty_org_id={counterparty_org_id}",
    ]
    if counterparty_doc_id:
        parts.append(f"counterparty_doc_id={counterparty_doc_id}")
    return "; ".join(parts)


class B2BCoordinator:
    """Resolve and plan cross-org B2B paired transactions."""

    def __init__(
        self,
        orgs_by_key: dict[str, Any],
        configs: dict[str, Any] | None = None,
        org_reference: dict[str, Any] | None = None,
    ) -> None:
        self._orgs_by_key = orgs_by_key
        raw_configs = configs if configs is not None else load_persona_b2b_configs()
        self._configs = self._parse_configs(raw_configs)
        self._org_reference = (
            org_reference if org_reference is not None else load_business_credentials()
        )
        self._seen_pairs: set[str] = set()
        self._logger = logger.bind(component="b2b_coordinator")

    def mark_pair_seen(self, pair_id: str) -> None:
        self._seen_pairs.add(pair_id)

    def plan_pairs(
        self,
        current_date: date,
        customers_by_org: dict[str, list[dict[str, Any]]],
    ) -> list[B2BPlannedPair]:
        """Plan B2B pairs due on the current date."""
        pair_specs = self._resolve_pair_specs(customers_by_org)
        planned: list[B2BPlannedPair] = []

        for spec in pair_specs:
            if not self._is_due(spec, current_date):
                continue

            seller_ctx = self._orgs_by_key.get(spec.seller_key)
            buyer_ctx = self._orgs_by_key.get(spec.buyer_key)
            if not seller_ctx or not buyer_ctx:
                continue

            pair_id = self._pair_id(
                UUID(str(seller_ctx.id)),
                UUID(str(buyer_ctx.id)),
                current_date,
            )
            if pair_id in self._seen_pairs:
                continue

            amount = self._amount_for_pair(spec, current_date)
            seller_name = str(getattr(seller_ctx, "name", spec.seller_key))
            buyer_name = str(getattr(buyer_ctx, "name", spec.buyer_key))
            description = spec.description or f"B2B services - {seller_name} to {buyer_name}"
            due_date = current_date + timedelta(days=spec.invoice_terms_days)

            planned.append(
                B2BPlannedPair(
                    pair_id=pair_id,
                    seller_key=spec.seller_key,
                    buyer_key=spec.buyer_key,
                    seller_org_id=UUID(str(seller_ctx.id)),
                    buyer_org_id=UUID(str(buyer_ctx.id)),
                    seller_name=seller_name,
                    buyer_name=buyer_name,
                    amount=amount,
                    description=description,
                    due_date=due_date,
                    payment_flow=spec.payment_flow,
                )
            )

        return planned

    def _resolve_pair_specs(
        self,
        customers_by_org: dict[str, list[dict[str, Any]]],
    ) -> list[B2BPairSpec]:
        pair_specs: dict[tuple[str, str], B2BPairSpec] = {}

        # Explicit config-driven pairs
        for org_key, config in self._configs.items():
            if not config.enabled:
                continue
            for counterparty in config.counterparties:
                seller_key, buyer_key = self._resolve_direction(
                    org_key, counterparty, customers_by_org
                )
                if not seller_key or not buyer_key:
                    continue
                spec_key = (seller_key, buyer_key)
                pair_specs[spec_key] = B2BPairSpec(
                    seller_key=seller_key,
                    buyer_key=buyer_key,
                    frequency=counterparty.frequency,
                    day_of_month=counterparty.day_of_month or DEFAULT_DAY_OF_MONTH,
                    amount_min=counterparty.amount_min,
                    amount_max=counterparty.amount_max,
                    description=counterparty.description,
                    invoice_terms_days=counterparty.invoice_terms_days,
                    payment_flow=counterparty.payment_flow,
                )

        # Auto-discover pairs based on customers
        for seller_key, customers in customers_by_org.items():
            seller_name = self._org_name_for_key(seller_key)
            if not seller_name:
                continue
            for buyer_key in self._orgs_by_key:
                if buyer_key == seller_key:
                    continue
                buyer_name = self._org_name_for_key(buyer_key)
                if not buyer_name:
                    continue
                if not self._customers_match_org(customers, buyer_name):
                    continue
                spec_key = (seller_key, buyer_key)
                if spec_key in pair_specs:
                    continue
                pair_specs[spec_key] = B2BPairSpec(
                    seller_key=seller_key,
                    buyer_key=buyer_key,
                    frequency=DEFAULT_FREQUENCY,
                    day_of_month=DEFAULT_DAY_OF_MONTH,
                    payment_flow=DEFAULT_PAYMENT_FLOW,
                )

        return list(pair_specs.values())

    def _parse_configs(self, raw: dict[str, Any]) -> dict[str, B2BConfig]:
        configs: dict[str, B2BConfig] = {}
        for org_key, data in raw.items():
            enabled = bool(data.get("enabled", True))
            counterparties_raw = data.get("counterparties", [])
            counterparties: list[B2BCounterpartySpec] = []
            if isinstance(counterparties_raw, list):
                for item in counterparties_raw:
                    if not isinstance(item, dict):
                        continue
                    org_key_value = item.get("org_key")
                    if not org_key_value:
                        continue
                    amount_min = item.get("amount_min") or item.get("amount")
                    amount_max = item.get("amount_max") or item.get("amount")
                    counterparties.append(
                        B2BCounterpartySpec(
                            org_key=str(org_key_value),
                            relationship=str(item.get("relationship", "auto")),
                            frequency=str(item.get("frequency", DEFAULT_FREQUENCY)),
                            day_of_month=item.get("day_of_month"),
                            amount_min=Decimal(str(amount_min)) if amount_min is not None else None,
                            amount_max=Decimal(str(amount_max)) if amount_max is not None else None,
                            description=item.get("description"),
                            invoice_terms_days=int(
                                item.get("invoice_terms_days", DEFAULT_TERMS_DAYS)
                            ),
                            payment_flow=str(item.get("payment_flow", DEFAULT_PAYMENT_FLOW)),
                        )
                    )
            configs[org_key] = B2BConfig(
                enabled=enabled,
                counterparties=tuple(counterparties),
            )
        return configs

    def _resolve_direction(
        self,
        org_key: str,
        counterparty: B2BCounterpartySpec,
        customers_by_org: dict[str, list[dict[str, Any]]],
    ) -> tuple[str | None, str | None]:
        relationship = counterparty.relationship.strip().lower()
        counterparty_key = counterparty.org_key
        if relationship in {"vendor", "seller"}:
            return org_key, counterparty_key
        if relationship in {"customer", "buyer"}:
            return counterparty_key, org_key

        # Auto: infer from customer list, fallback to org as seller
        org_customers = customers_by_org.get(org_key, [])
        if self._customers_match_org(org_customers, self._org_name_for_key(counterparty_key)):
            return org_key, counterparty_key
        counterparty_customers = customers_by_org.get(counterparty_key, [])
        if self._customers_match_org(counterparty_customers, self._org_name_for_key(org_key)):
            return counterparty_key, org_key
        return org_key, counterparty_key

    def _org_name_for_key(self, org_key: str) -> str | None:
        ctx = self._orgs_by_key.get(org_key)
        if ctx and getattr(ctx, "name", None):
            return str(ctx.name)
        if org_key in self._org_reference:
            name = self._org_reference[org_key].get("organization_name")
            if name:
                return str(name)
        return None

    @staticmethod
    def _customers_match_org(customers: list[dict[str, Any]], org_name: str | None) -> bool:
        if not org_name:
            return False
        for customer in customers:
            display = customer.get("display_name") or customer.get("name", "")
            if _names_match(str(display), org_name):
                return True
        return False

    def _pair_id(self, seller_org_id: UUID, buyer_org_id: UUID, current_date: date) -> str:
        seed = f"{seller_org_id}:{buyer_org_id}:{current_date.isoformat()}"
        return str(uuid5(B2B_NAMESPACE, seed))

    def _amount_for_pair(self, spec: B2BPairSpec, current_date: date) -> Decimal:
        amount_min, amount_max = self._default_amount_range(spec)
        if amount_min is None or amount_max is None:
            amount_min, amount_max = Decimal("250"), Decimal("2500")

        seed = uuid5(
            B2B_NAMESPACE,
            f"{spec.seller_key}:{spec.buyer_key}:{current_date.isoformat()}",
        ).int
        rng = random.Random(seed)
        amount_float = rng.triangular(
            float(amount_min),
            float(amount_max),
            float(amount_min) + (float(amount_max) - float(amount_min)) * 0.3,
        )
        amount_float = round(amount_float / 0.05) * 0.05
        return Decimal(str(round(amount_float, 2)))

    def _default_amount_range(self, spec: B2BPairSpec) -> tuple[Decimal | None, Decimal | None]:
        if spec.amount_min is not None or spec.amount_max is not None:
            return spec.amount_min, spec.amount_max
        return DEFAULT_AMOUNT_RANGES_BY_OWNER.get(spec.seller_key, (None, None))

    @staticmethod
    def _is_due(spec: B2BPairSpec, current_date: date) -> bool:
        frequency = spec.frequency.strip().lower()
        if frequency == "daily":
            return True
        if frequency == "weekly":
            return current_date.weekday() == 0  # Monday
        if frequency == "quarterly" and current_date.month not in (1, 4, 7, 10):
            return False
        day = spec.day_of_month
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        target_day = min(day, last_day)
        return current_date.day == target_day
