"""Deterministic accounting workflow - Non-LLM alternative to Sarah agent.

This module provides rule-based accounting operations that can replace
the LLM-driven AccountantAgent for scenarios where:
- You need faster execution (no API latency)
- You want deterministic, reproducible results
- You're generating bulk data
- You don't need natural language interaction

The LLM agent is still valuable for:
- Interactive Q&A with users
- Handling unexpected edge cases
- Generating insights and analysis
- Demo/showcase scenarios
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict
from uuid import UUID, uuid4

import structlog

from atlas_town.config.personas_loader import (
    load_persona_industries,
    load_persona_sales_tax_configs,
    load_persona_tax_configs,
    load_persona_year_end_configs,
)
from atlas_town.tools.atlas_api import AtlasAPIClient, AtlasAPIError
from atlas_town.transactions import (
    GeneratedTransaction,
    TransactionGenerator,
    TransactionType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class DailySummary:
    """Summary of a day's accounting activity."""

    org_name: str
    date: date
    invoices_created: int
    invoices_total: Decimal
    bills_created: int
    bills_total: Decimal
    payments_received: int
    payments_total: Decimal
    bills_paid: int
    bills_paid_total: Decimal
    trial_balance_ok: bool
    issues: list[str]

    def to_text(self) -> str:
        """Generate a text summary (replaces LLM-generated summaries)."""
        status = "✓ Balanced" if self.trial_balance_ok else "✗ UNBALANCED"

        issues_text = ""
        if self.issues:
            issues_text = "\n\nIssues requiring attention:\n" + "\n".join(
                f"  - {issue}" for issue in self.issues
            )

        return f"""
Daily Summary for {self.org_name} - {self.date}
{'=' * 50}

Revenue Activity:
  Invoices Created: {self.invoices_created} (${self.invoices_total:,.2f})
  Payments Received: {self.payments_received} (${self.payments_total:,.2f})

Expense Activity:
  Bills Entered: {self.bills_created} (${self.bills_total:,.2f})
  Bills Paid: {self.bills_paid} (${self.bills_paid_total:,.2f})

Books Status: {status}
{issues_text}
""".strip()


@dataclass(frozen=True)
class SalesTaxConfig:
    """Sales tax configuration for a business."""

    enabled: bool
    rate: Decimal
    jurisdiction: str
    tax_type: str
    name: str
    collect_on: tuple[str, ...]
    tax_authority: str | None
    remit_day: int

    @property
    def region(self) -> str:
        return self.jurisdiction.strip()

    @property
    def country(self) -> str | None:
        region = self.region
        if len(region) == 2 and region.isalpha():
            return "US"
        return None


@dataclass(frozen=True)
class YearEndConfig:
    """Year-end configuration for a business."""

    accrual_rate: Decimal
    tax_provision_rate: Decimal
    depreciation_rate: Decimal
    inventory_shrink_rate: Decimal
    fixed_asset_keywords: tuple[str, ...]
    accumulated_dep_keywords: tuple[str, ...]
    depreciation_expense_keywords: tuple[str, ...]
    inventory_keywords: tuple[str, ...]
    cogs_keywords: tuple[str, ...]
    tax_expense_keywords: tuple[str, ...]
    tax_payable_keywords: tuple[str, ...]
    retained_earnings_keywords: tuple[str, ...]
    income_summary_keywords: tuple[str, ...]

    @staticmethod
    def default() -> "YearEndConfig":
        return YearEndConfig(
            accrual_rate=Decimal("0.10"),
            tax_provision_rate=Decimal("0.25"),
            depreciation_rate=Decimal("0.10"),
            inventory_shrink_rate=Decimal("0.02"),
            fixed_asset_keywords=(
                "equipment",
                "furniture",
                "vehicle",
                "computer",
                "machinery",
                "leasehold",
                "fixtures",
            ),
            accumulated_dep_keywords=("accumulated depreciation", "accumulated"),
            depreciation_expense_keywords=("depreciation",),
            inventory_keywords=("inventory", "supplies"),
            cogs_keywords=("cost of goods", "cogs"),
            tax_expense_keywords=("income tax", "tax expense", "taxes"),
            tax_payable_keywords=("income tax payable", "tax payable"),
            retained_earnings_keywords=("retained earnings", "owner's equity"),
            income_summary_keywords=("income summary", "current year earnings", "profit and loss"),
        )


class WorkflowResults(TypedDict):
    """Typed results for deterministic transaction processing."""

    invoices_created: int
    invoices_total: Decimal
    bills_created: int
    bills_total: Decimal
    payments_received: int
    payments_total: Decimal
    bills_paid: int
    bills_paid_total: Decimal


# =============================================================================
# DETERMINISTIC ACCOUNTING WORKFLOW
# =============================================================================


class AccountingWorkflow:
    """Rule-based accounting workflow - no LLM required.

    This class handles all accounting operations through direct API calls
    with deterministic logic. It replaces the think-act-observe loop of
    the LLM agent with explicit, predictable code paths.
    """

    def __init__(
        self,
        api_client: AtlasAPIClient,
        transaction_generator: TransactionGenerator | None = None,
        run_id: str | None = None,
    ):
        self._api = api_client
        self._tx_gen = transaction_generator or TransactionGenerator()
        self._logger = logger.bind(component="accounting_workflow")
        # Cache accounts per org to avoid repeated API calls
        self._account_cache: dict[UUID, dict[str, Any]] = {}
        self._sales_tax_configs = self._load_sales_tax_configs()
        self._sales_tax_collected: dict[tuple[str, int, int], Decimal] = {}
        self._sales_tax_remitted: set[tuple[str, int, int]] = set()
        self._sales_tax_rate_cache: dict[tuple[UUID, str], dict[str, Any]] = {}
        self._year_end_configs = self._load_year_end_configs()
        self._month_end_closed: set[tuple[str, int, int]] = set()
        self._quarter_end_closed: set[tuple[str, int, int]] = set()
        self._year_end_closed: set[tuple[str, int]] = set()
        self._year_rollover_done: set[tuple[str, int]] = set()
        self._year_end_reporting_done: set[tuple[str, int]] = set()
        self._run_id = run_id
        self._run_id_short = run_id.split("-")[0] if run_id else None

    def _run_note(self) -> str | None:
        if not self._run_id:
            return None
        return f"sim_run_id={self._run_id}"

    def _run_suffix(self) -> str:
        if not self._run_id_short:
            return ""
        return f"-R{self._run_id_short}"

    def _load_sales_tax_configs(self) -> dict[str, SalesTaxConfig]:
        raw = load_persona_sales_tax_configs()
        configs: dict[str, SalesTaxConfig] = {}
        for business_key, config in raw.items():
            enabled = bool(config.get("enabled", False))
            if not enabled:
                continue

            try:
                rate = Decimal(str(config.get("rate", "0")))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Sales tax rate invalid for {business_key}: {config!r}"
                ) from exc

            jurisdiction = str(config.get("jurisdiction") or "US")
            tax_type = str(config.get("tax_type") or "sales")
            name = str(
                config.get("name") or f"{jurisdiction} {tax_type.title()} Tax"
            )
            collect_on = tuple(
                str(item).strip().lower()
                for item in (config.get("collect_on") or [])
                if str(item).strip()
            )
            tax_authority = config.get("tax_authority")
            remit_day = int(config.get("remit_day", 1))

            configs[business_key] = SalesTaxConfig(
                enabled=True,
                rate=rate,
                jurisdiction=jurisdiction,
                tax_type=tax_type,
                name=name,
                collect_on=collect_on,
                tax_authority=str(tax_authority) if tax_authority is not None else None,
                remit_day=remit_day,
            )

        return configs

    def _load_year_end_configs(self) -> dict[str, YearEndConfig]:
        industries = load_persona_industries()
        tax_configs = load_persona_tax_configs()
        overrides = load_persona_year_end_configs()

        def _with_rates(
            base: YearEndConfig,
            depreciation_rate: Decimal | None = None,
            inventory_shrink_rate: Decimal | None = None,
        ) -> YearEndConfig:
            return YearEndConfig(
                accrual_rate=base.accrual_rate,
                tax_provision_rate=base.tax_provision_rate,
                depreciation_rate=depreciation_rate
                if depreciation_rate is not None
                else base.depreciation_rate,
                inventory_shrink_rate=inventory_shrink_rate
                if inventory_shrink_rate is not None
                else base.inventory_shrink_rate,
                fixed_asset_keywords=base.fixed_asset_keywords,
                accumulated_dep_keywords=base.accumulated_dep_keywords,
                depreciation_expense_keywords=base.depreciation_expense_keywords,
                inventory_keywords=base.inventory_keywords,
                cogs_keywords=base.cogs_keywords,
                tax_expense_keywords=base.tax_expense_keywords,
                tax_payable_keywords=base.tax_payable_keywords,
                retained_earnings_keywords=base.retained_earnings_keywords,
                income_summary_keywords=base.income_summary_keywords,
            )

        defaults_by_industry: dict[str, YearEndConfig] = {
            "restaurant": _with_rates(
                YearEndConfig.default(),
                depreciation_rate=Decimal("0.12"),
                inventory_shrink_rate=Decimal("0.03"),
            ),
            "healthcare": _with_rates(
                YearEndConfig.default(),
                depreciation_rate=Decimal("0.10"),
                inventory_shrink_rate=Decimal("0.015"),
            ),
            "consulting": _with_rates(
                YearEndConfig.default(),
                depreciation_rate=Decimal("0.20"),
                inventory_shrink_rate=Decimal("0.00"),
            ),
            "service": _with_rates(
                YearEndConfig.default(),
                depreciation_rate=Decimal("0.15"),
                inventory_shrink_rate=Decimal("0.01"),
            ),
            "real_estate": _with_rates(
                YearEndConfig.default(),
                depreciation_rate=Decimal("0.08"),
                inventory_shrink_rate=Decimal("0.00"),
            ),
        }

        def _base_config(business_key: str) -> YearEndConfig:
            industry = industries.get(business_key, "")
            base = defaults_by_industry.get(industry, YearEndConfig.default())
            tax_config = tax_configs.get(business_key)
            tax_rate = None
            if isinstance(tax_config, dict):
                tax_rate = tax_config.get("estimated_tax_rate")
            if tax_rate is not None:
                try:
                    tax_rate_value = Decimal(str(tax_rate))
                    return YearEndConfig(
                        accrual_rate=base.accrual_rate,
                        tax_provision_rate=tax_rate_value,
                        depreciation_rate=base.depreciation_rate,
                        inventory_shrink_rate=base.inventory_shrink_rate,
                        fixed_asset_keywords=base.fixed_asset_keywords,
                        accumulated_dep_keywords=base.accumulated_dep_keywords,
                        depreciation_expense_keywords=base.depreciation_expense_keywords,
                        inventory_keywords=base.inventory_keywords,
                        cogs_keywords=base.cogs_keywords,
                        tax_expense_keywords=base.tax_expense_keywords,
                        tax_payable_keywords=base.tax_payable_keywords,
                        retained_earnings_keywords=base.retained_earnings_keywords,
                        income_summary_keywords=base.income_summary_keywords,
                    )
                except (ValueError, TypeError):
                    pass
            return base

        configs: dict[str, YearEndConfig] = {}
        keys = set(industries.keys()) | set(overrides.keys())
        for business_key in keys:
            base = _base_config(business_key)
            override = overrides.get(business_key, {})

            def _decimal_override(
                key: str,
                fallback: Decimal,
                override_map: dict[str, Any] = override,
            ) -> Decimal:
                value = override_map.get(key)
                if value is None:
                    return fallback
                try:
                    return Decimal(str(value))
                except (ValueError, TypeError):
                    return fallback

            def _keywords_override(
                key: str,
                fallback: tuple[str, ...],
                override_map: dict[str, Any] = override,
            ) -> tuple[str, ...]:
                raw = override_map.get(key)
                if not raw:
                    return fallback
                if isinstance(raw, list):
                    values = tuple(str(item).strip() for item in raw if str(item).strip())
                else:
                    values = (str(raw).strip(),)
                return tuple(dict.fromkeys(fallback + values))

            configs[business_key] = YearEndConfig(
                accrual_rate=_decimal_override("accrual_rate", base.accrual_rate),
                tax_provision_rate=_decimal_override(
                    "tax_provision_rate", base.tax_provision_rate
                ),
                depreciation_rate=_decimal_override(
                    "depreciation_rate", base.depreciation_rate
                ),
                inventory_shrink_rate=_decimal_override(
                    "inventory_shrink_rate", base.inventory_shrink_rate
                ),
                fixed_asset_keywords=_keywords_override(
                    "fixed_asset_keywords", base.fixed_asset_keywords
                ),
                accumulated_dep_keywords=_keywords_override(
                    "accumulated_dep_keywords", base.accumulated_dep_keywords
                ),
                depreciation_expense_keywords=_keywords_override(
                    "depreciation_expense_keywords", base.depreciation_expense_keywords
                ),
                inventory_keywords=_keywords_override(
                    "inventory_keywords", base.inventory_keywords
                ),
                cogs_keywords=_keywords_override("cogs_keywords", base.cogs_keywords),
                tax_expense_keywords=_keywords_override(
                    "tax_expense_keywords", base.tax_expense_keywords
                ),
                tax_payable_keywords=_keywords_override(
                    "tax_payable_keywords", base.tax_payable_keywords
                ),
                retained_earnings_keywords=_keywords_override(
                    "retained_earnings_keywords", base.retained_earnings_keywords
                ),
                income_summary_keywords=_keywords_override(
                    "income_summary_keywords", base.income_summary_keywords
                ),
            )

        return configs

    async def _get_accounts_for_org(self, org_id: UUID) -> dict[str, Any]:
        """Get cached account info for an organization."""
        if org_id not in self._account_cache:
            accounts = await self._api.list_accounts(limit=200)

            # Find default revenue account (prefer "Service Revenue" or first revenue account)
            revenue_accounts = [a for a in accounts if a.get("account_type") == "revenue"]
            revenue_account = next(
                (a for a in revenue_accounts if "service" in a.get("name", "").lower()),
                revenue_accounts[0] if revenue_accounts else None,
            )

            # Find default expense account (prefer "Supplies Expense" or "Cost of Goods Sold")
            expense_accounts = [a for a in accounts if a.get("account_type") == "expense"]
            expense_account = next(
                (a for a in expense_accounts if "supplies" in a.get("name", "").lower()),
                next(
                    (a for a in expense_accounts if "cost of goods" in a.get("name", "").lower()),
                    expense_accounts[0] if expense_accounts else None,
                ),
            )

            # Find AR account (type: accounts_receivable or asset with "receivable" in name)
            ar_accounts = [a for a in accounts if a.get("account_type") == "accounts_receivable"]
            if not ar_accounts:
                # Fallback: look for asset accounts with "receivable" in name
                ar_accounts = [
                    a for a in accounts
                    if a.get("account_type") == "asset"
                    and "receivable" in a.get("name", "").lower()
                ]
            ar_account = ar_accounts[0] if ar_accounts else None

            # Find AP account (type: accounts_payable or liability with "payable" in name)
            ap_accounts = [a for a in accounts if a.get("account_type") == "accounts_payable"]
            if not ap_accounts:
                ap_accounts = [
                    a for a in accounts
                    if a.get("account_type") == "liability"
                    and "payable" in a.get("name", "").lower()
                ]
            ap_account = ap_accounts[0] if ap_accounts else None

            # Find sales tax payable account (liability with "sales tax" or "tax payable")
            sales_tax_accounts = [
                a for a in accounts
                if a.get("account_type") == "liability"
                and (
                    "sales tax" in a.get("name", "").lower()
                    or "tax payable" in a.get("name", "").lower()
                )
            ]
            sales_tax_account = sales_tax_accounts[0] if sales_tax_accounts else None

            # Find deposit/cash account (bank or cash type)
            bank_accounts = [a for a in accounts if a.get("account_type") == "bank"]
            if not bank_accounts:
                bank_accounts = [
                    a for a in accounts
                    if a.get("account_type") == "asset"
                    and (
                        "cash" in a.get("name", "").lower()
                        or "checking" in a.get("name", "").lower()
                    )
                ]
            deposit_account = bank_accounts[0] if bank_accounts else None

            bank_account_id = None
            try:
                bank_accounts_feed = await self._api.list_bank_accounts()
                if bank_accounts_feed:
                    matched = None
                    if deposit_account:
                        matched = next(
                            (
                                acct
                                for acct in bank_accounts_feed
                                if str(acct.get("gl_account_id"))
                                == str(deposit_account.get("id"))
                            ),
                            None,
                        )
                    selected = matched or bank_accounts_feed[0]
                    bank_account_id = selected.get("id")
            except AtlasAPIError as exc:
                self._logger.warning(
                    "bank_accounts_list_failed",
                    org_id=str(org_id),
                    error=str(exc),
                )

            self._account_cache[org_id] = {
                "revenue_account_id": revenue_account["id"] if revenue_account else None,
                "expense_account_id": expense_account["id"] if expense_account else None,
                "ar_account_id": ar_account["id"] if ar_account else None,
                "ap_account_id": ap_account["id"] if ap_account else None,
                "deposit_account_id": deposit_account["id"] if deposit_account else None,
                "bank_account_id": bank_account_id,
                "sales_tax_payable_account_id": (
                    sales_tax_account["id"] if sales_tax_account else None
                ),
                "all_accounts": accounts,
            }

            if not revenue_account:
                self._logger.warning("no_revenue_account", org_id=str(org_id))
            if not expense_account:
                self._logger.warning("no_expense_account", org_id=str(org_id))
            if not ar_account:
                self._logger.warning("no_ar_account", org_id=str(org_id))
            if not ap_account:
                self._logger.warning("no_ap_account", org_id=str(org_id))
            if not deposit_account:
                self._logger.warning("no_deposit_account", org_id=str(org_id))
            if not sales_tax_account:
                self._logger.info("no_sales_tax_account", org_id=str(org_id))

        return self._account_cache[org_id]

    @staticmethod
    def _last_day_of_month(year: int, month: int) -> date:
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)

    @classmethod
    def _month_end_period(cls, current_date: date) -> tuple[date, date, int, int] | None:
        if current_date.day > 5:
            return None
        year = current_date.year
        month = current_date.month - 1
        if month == 0:
            month = 12
            year -= 1
        start = date(year, month, 1)
        end = cls._last_day_of_month(year, month)
        return start, end, year, month

    @classmethod
    def _quarter_end_period(cls, current_date: date) -> tuple[date, date, int, int] | None:
        if current_date.day > 10:
            return None
        if current_date.month not in (1, 4, 7, 10):
            return None
        year = current_date.year
        if current_date.month == 1:
            year -= 1
            quarter = 4
        elif current_date.month == 4:
            quarter = 1
        elif current_date.month == 7:
            quarter = 2
        else:
            quarter = 3
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end = cls._last_day_of_month(year, start_month + 2)
        return start, end, year, quarter

    @staticmethod
    def _find_account_by_keywords(
        accounts: list[dict[str, Any]],
        keywords: tuple[str, ...],
        account_type: str | None = None,
    ) -> dict[str, Any] | None:
        lowered_keywords = tuple(k.lower() for k in keywords)
        for account in accounts:
            if account_type and account.get("account_type") != account_type:
                continue
            name = str(account.get("name", "")).lower()
            if any(keyword in name for keyword in lowered_keywords):
                return account
        return None

    @classmethod
    def _find_account_with_fallback(
        cls,
        accounts: list[dict[str, Any]],
        keywords: tuple[str, ...],
        account_type: str | None,
    ) -> dict[str, Any] | None:
        account = cls._find_account_by_keywords(accounts, keywords, account_type)
        if account:
            return account
        return cls._find_account_by_keywords(accounts, keywords, None)

    @staticmethod
    def _extract_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, InvalidOperation):
            return None

    def _extract_net_income(self, report: dict[str, Any]) -> Decimal | None:
        for key in ("net_income", "net_profit", "net_income_amount", "net_profit_amount"):
            value = self._extract_decimal(report.get(key))
            if value is not None:
                return value

        for container_key in ("summary", "totals", "total", "result"):
            container = report.get(container_key)
            if isinstance(container, dict):
                for key in ("net_income", "net_profit", "net_income_amount", "net_profit_amount"):
                    value = self._extract_decimal(container.get(key))
                    if value is not None:
                        return value

        revenue = self._extract_decimal(report.get("total_revenue"))
        expenses = self._extract_decimal(report.get("total_expenses"))
        if revenue is None and isinstance(report.get("summary"), dict):
            revenue = self._extract_decimal(report["summary"].get("total_revenue"))
        if expenses is None and isinstance(report.get("summary"), dict):
            expenses = self._extract_decimal(report["summary"].get("total_expenses"))
        if revenue is not None and expenses is not None:
            return revenue - expenses
        return None

    def _extract_trial_balance_accounts(
        self, trial_balance: dict[str, Any]
    ) -> list[dict[str, Any]]:
        for key in ("accounts", "rows", "items", "data"):
            value = trial_balance.get(key)
            if isinstance(value, list):
                return value
        return []

    def _trial_balance_amount(self, entry: dict[str, Any]) -> Decimal | None:
        balance = self._extract_decimal(entry.get("balance"))
        if balance is not None:
            return balance
        debit = self._extract_decimal(entry.get("debit")) or Decimal("0")
        credit = self._extract_decimal(entry.get("credit")) or Decimal("0")
        if debit == Decimal("0") and credit == Decimal("0"):
            return None
        return debit - credit

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    async def _fetch_all_invoices(
        self, status: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        invoices: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = await self._api.list_invoices(offset=offset, limit=limit, status=status)
            if not batch:
                break
            invoices.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return invoices

    async def _fetch_all_bills(
        self, status: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        bills: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = await self._api.list_bills(offset=offset, limit=limit, status=status)
            if not batch:
                break
            bills.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return bills

    async def _fetch_all_payments(self, limit: int = 200) -> list[dict[str, Any]]:
        payments: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = await self._api.list_payments(offset=offset, limit=limit)
            if not batch:
                break
            payments.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return payments

    async def _fetch_all_payments_made(self, limit: int = 200) -> list[dict[str, Any]]:
        payments: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = await self._api.list_payments_made(offset=offset, limit=limit)
            if not batch:
                break
            payments.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return payments

    def _is_sales_taxable(self, config: SalesTaxConfig, tx: GeneratedTransaction) -> bool:
        if not config.collect_on:
            return True

        candidates: list[str] = []
        if tx.metadata:
            for key in ("category", "tax_category", "item_type", "line_item_type"):
                value = tx.metadata.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
                elif isinstance(value, list):
                    candidates.extend(
                        str(item) for item in value if str(item).strip()
                    )

        candidates.append(tx.description)

        for candidate in candidates:
            lowered = candidate.lower()
            for keyword in config.collect_on:
                if keyword in lowered:
                    return True

        return False

    async def _get_or_create_sales_tax_rate(
        self, org_id: UUID, config: SalesTaxConfig
    ) -> dict[str, Any] | None:
        cache_key = (org_id, config.name)
        if cache_key in self._sales_tax_rate_cache:
            return self._sales_tax_rate_cache[cache_key]

        try:
            rates = await self._api.list_tax_rates(
                tax_type=config.tax_type
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "sales_tax_rate_list_failed",
                org_id=str(org_id),
                error=str(exc),
            )
            return None

        match = None
        for rate in rates:
            name = str(rate.get("name", "")).strip()
            if name.lower() == config.name.lower():
                match = rate
                break
            try:
                rate_value = Decimal(str(rate.get("rate", "0")))
            except (ValueError, TypeError):
                rate_value = None
            if (
                rate_value is not None
                and rate_value == config.rate
                and str(rate.get("tax_type", "")).lower() == config.tax_type.lower()
                and str(rate.get("region", "")).lower()
                == config.region.lower()
            ):
                match = rate
                break

        if not match:
            region = config.region.upper()
            code = f"ST-{region}" if region else "SALES"
            payload = {
                "name": config.name,
                "rate": str(config.rate),
                "tax_type": config.tax_type,
                "code": code[:20],
                "country": config.country,
                "region": config.region,
                "is_compound": False,
                "is_recoverable": True,
            }
            try:
                match = await self._api.create_tax_rate(payload)
            except AtlasAPIError as exc:
                self._logger.warning(
                    "sales_tax_rate_create_failed",
                    org_id=str(org_id),
                    error=str(exc),
                )
                match = None

        if match:
            self._sales_tax_rate_cache[cache_key] = match

        return match

    async def _calculate_sales_tax(
        self,
        business_key: str,
        tx: GeneratedTransaction,
        org_id: UUID,
    ) -> Decimal:
        config = self._sales_tax_configs.get(business_key)
        if not config or not config.enabled:
            return Decimal("0")

        if tx.amount <= 0:
            return Decimal("0")

        if tx.metadata and tx.metadata.get("tax_exempt"):
            return Decimal("0")

        if not self._is_sales_taxable(config, tx):
            return Decimal("0")

        rate = config.rate
        tax_rate = await self._get_or_create_sales_tax_rate(org_id, config)
        if tax_rate:
            try:
                rate = Decimal(str(tax_rate.get("rate", str(rate))))
            except (ValueError, TypeError):
                rate = config.rate

        return (tx.amount * rate).quantize(Decimal("0.01"))

    def _record_sales_tax_collected(
        self, business_key: str, current_date: date, amount: Decimal
    ) -> None:
        period_key = (business_key, current_date.year, current_date.month)
        self._sales_tax_collected[period_key] = (
            self._sales_tax_collected.get(period_key, Decimal("0")) + amount
        )

    def _mark_sales_tax_remitted(
        self, business_key: str, metadata: dict[str, Any] | None
    ) -> None:
        if not metadata:
            return
        year = metadata.get("tax_period_year")
        month = metadata.get("tax_period_month")
        if year is None or month is None:
            return
        try:
            period_key = (business_key, int(year), int(month))
        except (TypeError, ValueError):
            return
        self._sales_tax_remitted.add(period_key)

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
                    return UUID(str(vendor.get("id")))
                except (TypeError, ValueError):
                    return None
        return None

    async def _generate_sales_tax_remittance(
        self,
        business_key: str,
        current_date: date,
        vendors: list[dict[str, Any]],
        org_id: UUID,
    ) -> GeneratedTransaction | None:
        config = self._sales_tax_configs.get(business_key)
        if not config or not config.enabled:
            return None

        if current_date.day != config.remit_day:
            return None

        prior_month = current_date.month - 1
        prior_year = current_date.year
        if prior_month == 0:
            prior_month = 12
            prior_year -= 1

        period_key = (business_key, prior_year, prior_month)
        if period_key in self._sales_tax_remitted:
            return None

        amount = self._sales_tax_collected.get(period_key, Decimal("0"))
        if amount <= 0:
            return None

        vendor_name = config.tax_authority or "State Tax Authority"
        vendor_id = self._find_vendor_id(vendor_name, vendors)
        if vendor_id is None and vendors:
            self._logger.warning(
                "sales_tax_vendor_missing",
                business=business_key,
                vendor=vendor_name,
            )
            return None

        account_info = await self._get_accounts_for_org(org_id)
        tax_account_id = (
            account_info.get("sales_tax_payable_account_id")
            or account_info.get("ap_account_id")
        )
        if not tax_account_id:
            self._logger.warning(
                "sales_tax_remittance_missing_account",
                business=business_key,
                org_id=str(org_id),
            )
            return None

        period_label = date(prior_year, prior_month, 1).strftime("%B %Y")
        return GeneratedTransaction(
            transaction_type=TransactionType.BILL,
            description=f"Sales tax remittance - {period_label}",
            amount=amount.quantize(Decimal("0.01")),
            vendor_id=vendor_id,
            metadata={
                "tax_remittance": "sales",
                "tax_period_year": prior_year,
                "tax_period_month": prior_month,
                "account_id_override": str(tax_account_id),
                "notes": f"Remit sales tax collected for {period_label}.",
            },
        )

    # =========================================================================
    # CORE WORKFLOWS (Replace LLM decision-making)
    # =========================================================================

    async def run_daily_workflow(
        self,
        business_key: str,
        org_id: UUID,
        current_date: date,
        current_hour: int | None = None,
        current_phase: str | None = None,
    ) -> DailySummary:
        """Run complete daily accounting workflow for a business.

        This replaces the LLM's "End of day" task with deterministic steps:
        1. Generate transactions (probabilistic - unchanged)
        2. Create invoices (deterministic)
        3. Record payments (deterministic)
        4. Enter bills (deterministic)
        5. Pay due bills (deterministic)
        6. Run trial balance (deterministic)
        7. Generate summary (template-based)
        """
        self._logger.info(
            "starting_daily_workflow",
            business=business_key,
            org_id=str(org_id),
            date=current_date.isoformat(),
        )

        # Set organization context
        await self._api.switch_organization(org_id)
        org_name = await self._get_org_name(org_id)

        # Step 1: Generate transactions (probabilistic layer - unchanged)
        customers = await self._api.list_customers()
        vendors = await self._api.list_vendors()
        pending_invoices = await self._api.list_invoices(status="sent")

        transactions = self._tx_gen.generate_daily_transactions(
            business_key=business_key,
            current_date=current_date,
            customers=customers,
            vendors=vendors,
            pending_invoices=pending_invoices,
            current_hour=current_hour,
            current_phase=current_phase,
            hourly=True,
        )
        recurring_transactions = self._tx_gen.generate_recurring_transactions(
            business_key=business_key,
            current_date=current_date,
            vendors=vendors,
        )
        if recurring_transactions:
            transactions.extend(recurring_transactions)

        financing_transactions = self._tx_gen.generate_financing_transactions(
            business_key=business_key,
            current_date=current_date,
            vendors=vendors,
        )
        if financing_transactions:
            transactions.extend(financing_transactions)

        sales_tax_remittance = await self._generate_sales_tax_remittance(
            business_key=business_key,
            current_date=current_date,
            vendors=vendors,
            org_id=org_id,
        )
        if sales_tax_remittance:
            transactions.append(sales_tax_remittance)

        # Step 2-5: Process transactions (deterministic)
        results = await self._process_transactions(
            transactions, current_date, org_id, business_key
        )

        # Step 6: Verify books are balanced
        trial_balance = await self._api.get_trial_balance(
            as_of_date=current_date.isoformat()
        )
        is_balanced = self._check_trial_balance(trial_balance)

        # Step 7: Identify any issues
        issues = await self._identify_issues(org_id, current_date)

        summary = DailySummary(
            org_name=org_name,
            date=current_date,
            invoices_created=results["invoices_created"],
            invoices_total=results["invoices_total"],
            bills_created=results["bills_created"],
            bills_total=results["bills_total"],
            payments_received=results["payments_received"],
            payments_total=results["payments_total"],
            bills_paid=results["bills_paid"],
            bills_paid_total=results["bills_paid_total"],
            trial_balance_ok=is_balanced,
            issues=issues,
        )

        self._logger.info(
            "daily_workflow_complete",
            business=business_key,
            invoices=summary.invoices_created,
            bills=summary.bills_created,
            balanced=is_balanced,
        )

        return summary

    async def run_period_end_workflow(
        self,
        business_key: str,
        org_id: UUID,
        current_date: date,
    ) -> dict[str, Any]:
        """Run month-end, quarter-end, and year-end workflows when due."""
        results: dict[str, Any] = {}

        month_period = self._month_end_period(current_date)
        if month_period:
            start, end, year, month = month_period
            month_key = (business_key, year, month)
            if month_key not in self._month_end_closed:
                results["month_end"] = await self._run_month_end_close(
                    business_key, org_id, start, end
                )
                self._month_end_closed.add(month_key)

        quarter_period = self._quarter_end_period(current_date)
        if quarter_period:
            start, end, year, quarter = quarter_period
            quarter_key = (business_key, year, quarter)
            if quarter_key not in self._quarter_end_closed:
                results["quarter_end"] = await self._run_quarter_end_close(
                    business_key, org_id, start, end, year, quarter
                )
                self._quarter_end_closed.add(quarter_key)

        if current_date.month == 12 and current_date.day == 31:
            year = current_date.year
            year_key = (business_key, year)
            if year_key not in self._year_end_closed:
                results["year_end"] = await self._run_year_end_close(
                    business_key, org_id, current_date
                )
                self._year_end_closed.add(year_key)

        if current_date.month == 1 and current_date.day == 1:
            prior_year = current_date.year - 1
            rollover_key = (business_key, prior_year)
            if rollover_key not in self._year_rollover_done:
                budget = await self._initialize_new_year_budget(current_date.year)
                results["new_year_setup"] = {
                    "year": current_date.year,
                    "notes": "Initialized new fiscal year (balances carried forward).",
                    "budget_initialized": bool(budget),
                    "budget_id": budget.get("id") if budget else None,
                }
                self._year_rollover_done.add(rollover_key)

        if current_date.month == 1 and current_date.day <= 31:
            prior_year = current_date.year - 1
            reporting_key = (business_key, prior_year)
            if reporting_key not in self._year_end_reporting_done:
                results["year_end_reporting"] = await self._run_year_end_reporting(
                    business_key, org_id, prior_year
                )
                self._year_end_reporting_done.add(reporting_key)

        return results

    async def _run_month_end_close(
        self,
        business_key: str,
        org_id: UUID,
        period_start: date,
        period_end: date,
    ) -> dict[str, Any]:
        config = self._year_end_configs.get(business_key, YearEndConfig.default())
        self._logger.info(
            "month_end_close_start",
            business=business_key,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
        )

        await self._api.switch_organization(org_id)
        ar_aging = await self._api.get_ar_aging()
        ap_aging = await self._api.get_ap_aging()
        trial_balance = await self._api.get_trial_balance(
            as_of_date=period_end.isoformat()
        )

        account_info = await self._get_accounts_for_org(org_id)
        bank_transactions: list[dict[str, Any]] = []
        bank_account_id = account_info.get("bank_account_id")
        if bank_account_id:
            try:
                bank_transactions = await self._api.list_bank_transactions(
                    bank_account_id=UUID(str(bank_account_id)),
                    limit=200,
                )
            except AtlasAPIError as exc:
                self._logger.warning(
                    "bank_transactions_list_failed",
                    business=business_key,
                    org_id=str(org_id),
                    error=str(exc),
                )
        unmatched = [
            tx for tx in bank_transactions
            if not tx.get("match_id") and not tx.get("matched") and not tx.get("is_matched")
        ]
        followups = await self._generate_overdue_followups(period_end)
        reconciliation = await self._reconcile_bank_transactions(
            bank_transactions, account_info, period_end
        )

        accrual_entry_id = None
        pending_bills = await self._api.list_bills(status="pending")
        accrual_base = sum(
            self._extract_decimal(bill.get("balance")) or Decimal("0")
            for bill in pending_bills
            if bill.get("due_date")
            and self._is_due_within_days(bill.get("due_date"), period_end, 30)
        )
        accrual_amount = (accrual_base * config.accrual_rate).quantize(Decimal("0.01"))
        if accrual_amount > 0:
            accounts = account_info.get("all_accounts", [])
            expense_account_id = account_info.get("expense_account_id")
            accrued_liability = self._find_account_with_fallback(
                accounts, ("accrued", "accrual", "payable"), "liability"
            )
            if expense_account_id and accrued_liability:
                entry = await self._api.create_journal_entry({
                    "entry_date": period_end.isoformat(),
                    "description": f"Month-end accrual adjustment{self._run_suffix()}",
                    "lines": [
                        {
                            "account_id": str(expense_account_id),
                            "entry_type": "debit",
                            "amount": str(accrual_amount),
                            "description": "Accrued expenses",
                        },
                        {
                            "account_id": str(accrued_liability["id"]),
                            "entry_type": "credit",
                            "amount": str(accrual_amount),
                            "description": "Accrued expenses payable",
                        },
                    ],
                })
                accrual_entry_id = entry.get("id")

        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "ar_aging": ar_aging,
            "ap_aging": ap_aging,
            "trial_balance_ok": self._check_trial_balance(trial_balance),
            "bank_transactions": len(bank_transactions),
            "unmatched_bank_transactions": len(unmatched),
            "reconciliation_summary": reconciliation,
            "overdue_followups": followups,
            "accrual_entry_id": accrual_entry_id,
        }

    async def _run_quarter_end_close(
        self,
        business_key: str,
        org_id: UUID,
        period_start: date,
        period_end: date,
        year: int,
        quarter: int,
    ) -> dict[str, Any]:
        config = self._year_end_configs.get(business_key, YearEndConfig.default())
        self._logger.info(
            "quarter_end_close_start",
            business=business_key,
            tax_year=year,
            quarter=quarter,
        )

        await self._api.switch_organization(org_id)
        profit_loss = await self._api.get_profit_loss(
            period_start.isoformat(), period_end.isoformat()
        )
        balance_sheet = await self._api.get_balance_sheet(period_end.isoformat())
        cash_flow = await self._api.get_cash_flow(
            period_start.isoformat(), period_end.isoformat()
        )
        management_reports = await self._generate_management_reports(
            period_start, period_end
        )

        tax_entry_id = None
        net_income = self._extract_net_income(profit_loss)
        if net_income is not None and net_income > Decimal("0"):
            tax_amount = (net_income * config.tax_provision_rate).quantize(
                Decimal("0.01")
            )
            account_info = await self._get_accounts_for_org(org_id)
            accounts = account_info.get("all_accounts", [])
            tax_expense = self._find_account_with_fallback(
                accounts, config.tax_expense_keywords, "expense"
            )
            tax_payable = self._find_account_with_fallback(
                accounts, config.tax_payable_keywords, "liability"
            )
            if tax_expense and tax_payable:
                entry = await self._api.create_journal_entry({
                    "entry_date": period_end.isoformat(),
                    "description": (
                        f"Quarter-end tax provision Q{quarter} {year}{self._run_suffix()}"
                    ),
                    "lines": [
                        {
                            "account_id": str(tax_expense["id"]),
                            "entry_type": "debit",
                            "amount": str(tax_amount),
                            "description": "Income tax provision",
                        },
                        {
                            "account_id": str(tax_payable["id"]),
                            "entry_type": "credit",
                            "amount": str(tax_amount),
                            "description": "Income tax payable",
                        },
                    ],
                })
                tax_entry_id = entry.get("id")

        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "quarter": quarter,
            "year": year,
            "profit_loss": profit_loss,
            "balance_sheet": balance_sheet,
            "cash_flow": cash_flow,
            "management_reports": management_reports,
            "tax_provision_entry_id": tax_entry_id,
        }

    async def _run_year_end_close(
        self,
        business_key: str,
        org_id: UUID,
        period_end: date,
    ) -> dict[str, Any]:
        config = self._year_end_configs.get(business_key, YearEndConfig.default())
        self._logger.info(
            "year_end_close_start",
            business=business_key,
            period_end=period_end.isoformat(),
        )

        await self._api.switch_organization(org_id)
        trial_balance = await self._api.get_trial_balance(
            as_of_date=period_end.isoformat()
        )
        accounts = (await self._get_accounts_for_org(org_id)).get("all_accounts", [])
        tb_accounts = self._extract_trial_balance_accounts(trial_balance)

        fixed_assets = [
            account for account in accounts
            if account.get("account_type") == "asset"
            and any(
                keyword in str(account.get("name", "")).lower()
                for keyword in config.fixed_asset_keywords
            )
        ]
        accumulated_dep = self._find_account_with_fallback(
            accounts, config.accumulated_dep_keywords, "asset"
        )
        depreciation_expense = self._find_account_with_fallback(
            accounts, config.depreciation_expense_keywords, "expense"
        )

        depreciation_entry_id = None
        total_fixed = Decimal("0")
        if fixed_assets:
            for account in fixed_assets:
                balance = None
                for entry in tb_accounts:
                    if str(entry.get("account_id") or entry.get("id")) == str(account.get("id")):
                        balance = self._trial_balance_amount(entry)
                        break
                if balance is None:
                    balance_info = await self._api.get_account_balance(
                        UUID(str(account["id"]))
                    )
                    balance = self._extract_decimal(balance_info.get("balance"))
                if balance and balance > 0:
                    total_fixed += balance

        if total_fixed > 0 and accumulated_dep and depreciation_expense:
            depreciation_amount = (total_fixed * config.depreciation_rate).quantize(
                Decimal("0.01")
            )
            if depreciation_amount > 0:
                entry = await self._api.create_journal_entry({
                    "entry_date": period_end.isoformat(),
                    "description": f"Year-end depreciation{self._run_suffix()}",
                    "lines": [
                        {
                            "account_id": str(depreciation_expense["id"]),
                            "entry_type": "debit",
                            "amount": str(depreciation_amount),
                            "description": "Depreciation expense",
                        },
                        {
                            "account_id": str(accumulated_dep["id"]),
                            "entry_type": "credit",
                            "amount": str(depreciation_amount),
                            "description": "Accumulated depreciation",
                        },
                    ],
                })
                depreciation_entry_id = entry.get("id")

        inventory_entry_id = None
        if business_key in {"tony", "chen"}:
            inventory_account = self._find_account_with_fallback(
                accounts, config.inventory_keywords, "asset"
            )
            cogs_account = self._find_account_with_fallback(
                accounts, config.cogs_keywords, "expense"
            )
            if inventory_account and cogs_account:
                inventory_balance = None
                for entry in tb_accounts:
                    if str(entry.get("account_id") or entry.get("id")) == str(
                        inventory_account.get("id")
                    ):
                        inventory_balance = self._trial_balance_amount(entry)
                        break
                if inventory_balance is None:
                    balance_info = await self._api.get_account_balance(
                        UUID(str(inventory_account["id"]))
                    )
                    inventory_balance = self._extract_decimal(balance_info.get("balance"))
                if inventory_balance and inventory_balance > 0:
                    adjustment = (inventory_balance * config.inventory_shrink_rate).quantize(
                        Decimal("0.01")
                    )
                    if adjustment > 0:
                        entry = await self._api.create_journal_entry({
                            "entry_date": period_end.isoformat(),
                            "description": f"Inventory adjustment{self._run_suffix()}",
                            "lines": [
                                {
                                    "account_id": str(cogs_account["id"]),
                                    "entry_type": "debit",
                                    "amount": str(adjustment),
                                    "description": "Inventory shrink adjustment",
                                },
                                {
                                    "account_id": str(inventory_account["id"]),
                                    "entry_type": "credit",
                                    "amount": str(adjustment),
                                    "description": "Inventory adjustment",
                                },
                            ],
                        })
                        inventory_entry_id = entry.get("id")

        closing_entry_id = None
        revenue_expense_close_entry_id = None
        year_start = date(period_end.year, 1, 1)
        profit_loss = await self._api.get_profit_loss(
            year_start.isoformat(), period_end.isoformat()
        )
        net_income = self._extract_net_income(profit_loss)
        retained_earnings = self._find_account_with_fallback(
            accounts, config.retained_earnings_keywords, "equity"
        )
        income_summary = self._find_account_with_fallback(
            accounts, config.income_summary_keywords, "equity"
        )

        tb_rows = self._extract_trial_balance_accounts(trial_balance)
        revenue_rows = [row for row in tb_rows if row.get("account_type") == "revenue"]
        expense_rows = [row for row in tb_rows if row.get("account_type") == "expense"]

        revenue_total = Decimal("0")
        expense_total = Decimal("0")
        closing_lines: list[dict[str, Any]] = []

        for row in revenue_rows:
            debit = self._extract_decimal(row.get("debit")) or Decimal("0")
            credit = self._extract_decimal(row.get("credit")) or Decimal("0")
            amount = (credit - debit).quantize(Decimal("0.01"))
            if amount <= 0 or not row.get("account_id"):
                continue
            revenue_total += amount
            closing_lines.append(
                {
                    "account_id": str(row.get("account_id")),
                    "entry_type": "debit",
                    "amount": str(amount),
                    "description": f"Close revenue - {row.get('account_name')}",
                }
            )

        for row in expense_rows:
            debit = self._extract_decimal(row.get("debit")) or Decimal("0")
            credit = self._extract_decimal(row.get("credit")) or Decimal("0")
            amount = (debit - credit).quantize(Decimal("0.01"))
            if amount <= 0 or not row.get("account_id"):
                continue
            expense_total += amount
            closing_lines.append(
                {
                    "account_id": str(row.get("account_id")),
                    "entry_type": "credit",
                    "amount": str(amount),
                    "description": f"Close expense - {row.get('account_name')}",
                }
            )

        if income_summary and (revenue_total > 0 or expense_total > 0):
            if revenue_total > 0:
                closing_lines.append(
                    {
                        "account_id": str(income_summary.get("id")),
                        "entry_type": "credit",
                        "amount": str(revenue_total.quantize(Decimal("0.01"))),
                        "description": "Close revenue to income summary",
                    }
                )
            if expense_total > 0:
                closing_lines.append(
                    {
                        "account_id": str(income_summary.get("id")),
                        "entry_type": "debit",
                        "amount": str(expense_total.quantize(Decimal("0.01"))),
                        "description": "Close expenses to income summary",
                    }
                )

        if closing_lines and income_summary:
            entry = await self._api.create_journal_entry({
                "entry_date": period_end.isoformat(),
                "description": f"Revenue & expense closing {period_end.year}{self._run_suffix()}",
                "lines": closing_lines,
            })
            revenue_expense_close_entry_id = entry.get("id")

        if net_income is None:
            net_income = revenue_total - expense_total

        if net_income is not None and retained_earnings and income_summary:
            amount = net_income.quantize(Decimal("0.01"))
            if amount != 0:
                if amount > 0:
                    debit_account = income_summary["id"]
                    credit_account = retained_earnings["id"]
                else:
                    debit_account = retained_earnings["id"]
                    credit_account = income_summary["id"]
                    amount = abs(amount)
                entry = await self._api.create_journal_entry({
                    "entry_date": period_end.isoformat(),
                    "description": f"Closing entry {period_end.year}{self._run_suffix()}",
                    "lines": [
                        {
                            "account_id": str(debit_account),
                            "entry_type": "debit",
                            "amount": str(amount),
                            "description": "Close income summary",
                        },
                        {
                            "account_id": str(credit_account),
                            "entry_type": "credit",
                            "amount": str(amount),
                            "description": "Transfer to retained earnings",
                        },
                    ],
                })
                closing_entry_id = entry.get("id")

        return {
            "trial_balance_ok": self._check_trial_balance(trial_balance),
            "depreciation_entry_id": depreciation_entry_id,
            "inventory_entry_id": inventory_entry_id,
            "revenue_expense_close_entry_id": revenue_expense_close_entry_id,
            "closing_entry_id": closing_entry_id,
        }

    async def _run_year_end_reporting(
        self,
        business_key: str,
        org_id: UUID,
        tax_year: int,
    ) -> dict[str, Any]:
        await self._api.switch_organization(org_id)
        report = await self._summarize_1099_activity(tax_year)
        return {"tax_year": tax_year, **report}

    async def _process_transactions(
        self,
        transactions: list[GeneratedTransaction],
        current_date: date,
        org_id: UUID,
        business_key: str,
    ) -> WorkflowResults:
        """Process generated transactions into accounting records.

        This is the deterministic replacement for LLM tool-calling.
        Instead of the LLM deciding what to do, we have explicit rules.
        """
        results: WorkflowResults = {
            "invoices_created": 0,
            "invoices_total": Decimal("0"),
            "bills_created": 0,
            "bills_total": Decimal("0"),
            "payments_received": 0,
            "payments_total": Decimal("0"),
            "bills_paid": 0,
            "bills_paid_total": Decimal("0"),
        }

        for tx in transactions:
            try:
                if tx.transaction_type == TransactionType.INVOICE:
                    tax_amount = await self._calculate_sales_tax(
                        business_key=business_key,
                        tx=tx,
                        org_id=org_id,
                    )
                    invoice = await self._create_invoice(
                        tx, current_date, org_id, business_key, tax_amount
                    )
                    if invoice:
                        results["invoices_created"] += 1
                        results["invoices_total"] += tx.amount + tax_amount
                        if tax_amount > 0:
                            self._record_sales_tax_collected(
                                business_key, current_date, tax_amount
                            )

                elif tx.transaction_type == TransactionType.CASH_SALE:
                    # Cash sales: create invoice + immediate payment
                    tax_amount = await self._calculate_sales_tax(
                        business_key=business_key,
                        tx=tx,
                        org_id=org_id,
                    )
                    invoice = await self._create_invoice(
                        tx, current_date, org_id, business_key, tax_amount
                    )
                    if invoice and tx.customer_id:
                        total_amount = tx.amount + tax_amount
                        await self._record_payment(
                            invoice_id=invoice["id"],
                            customer_id=tx.customer_id,
                            amount=total_amount,
                            payment_date=current_date,
                            org_id=org_id,
                        )
                        results["invoices_created"] += 1
                        results["invoices_total"] += total_amount
                        results["payments_received"] += 1
                        results["payments_total"] += total_amount
                        if tax_amount > 0:
                            self._record_sales_tax_collected(
                                business_key, current_date, tax_amount
                            )

                elif tx.transaction_type == TransactionType.BILL:
                    bill = await self._create_bill(tx, current_date, org_id)
                    if bill:
                        results["bills_created"] += 1
                        results["bills_total"] += tx.amount
                        if tx.metadata and tx.metadata.get("tax_remittance") == "sales":
                            self._mark_sales_tax_remitted(business_key, tx.metadata)

                elif tx.transaction_type == TransactionType.PAYMENT_RECEIVED:
                    # Payment for existing invoice
                    if tx.metadata and tx.metadata.get("invoice_id") and tx.customer_id:
                        await self._record_payment(
                            invoice_id=tx.metadata["invoice_id"],
                            customer_id=tx.customer_id,
                            amount=tx.amount,
                            payment_date=current_date,
                            org_id=org_id,
                        )
                        results["payments_received"] += 1
                        results["payments_total"] += tx.amount

                elif tx.transaction_type == TransactionType.BILL_PAYMENT:
                    if tx.metadata and tx.metadata.get("bill_id"):
                        await self._pay_bill(
                            bill_id=tx.metadata["bill_id"],
                            amount=tx.amount,
                            payment_date=current_date,
                        )
                        results["bills_paid"] += 1
                        results["bills_paid_total"] += tx.amount

            except Exception as e:
                self._logger.error(
                    "transaction_processing_error",
                    tx_type=tx.transaction_type.value,
                    error=str(e),
                )

        return results

    # =========================================================================
    # ACCOUNTING OPERATIONS (Direct API calls - no LLM)
    # =========================================================================

    async def _create_invoice(
        self,
        tx: GeneratedTransaction,
        invoice_date: date,
        org_id: UUID,
        business_key: str,
        tax_amount: Decimal,
    ) -> dict[str, Any] | None:
        """Create an invoice - deterministic, no LLM reasoning needed."""
        if not tx.customer_id:
            self._logger.warning("invoice_missing_customer", description=tx.description)
            return None

        # Get cached accounts
        account_info = await self._get_accounts_for_org(org_id)
        revenue_account_id = account_info.get("revenue_account_id")
        ar_account_id = account_info.get("ar_account_id")
        tax_account_id = (
            account_info.get("sales_tax_payable_account_id")
            or account_info.get("ap_account_id")
        )

        if not revenue_account_id:
            self._logger.warning(
                "invoice_skipped_no_revenue_account",
                description=tx.description,
                org_id=str(org_id),
            )
            return None

        if not ar_account_id:
            self._logger.warning(
                "invoice_skipped_no_ar_account",
                description=tx.description,
                org_id=str(org_id),
            )
            return None

        due_date = invoice_date + timedelta(days=30)  # Net 30 terms

        lines: list[dict[str, Any]] = [
            {
                "description": tx.description,
                "quantity": "1",
                "unit_price": str(tx.amount),
                "revenue_account_id": revenue_account_id,
            }
        ]

        if tax_amount > 0 and tax_account_id:
            sales_tax_config = self._sales_tax_configs.get(business_key)
            tax_label = sales_tax_config.name if sales_tax_config else "Sales Tax"
            lines.append(
                {
                    "description": f"{tax_label}",
                    "quantity": "1",
                    "unit_price": str(tax_amount),
                    "revenue_account_id": tax_account_id,
                }
            )
        elif tax_amount > 0:
            self._logger.warning(
                "sales_tax_skipped_missing_account",
                org_id=str(org_id),
                amount=str(tax_amount),
            )

        invoice_payload = {
            "customer_id": str(tx.customer_id),
            "invoice_date": invoice_date.isoformat(),
            "due_date": due_date.isoformat(),
            "lines": lines,
        }
        run_note = self._run_note()
        if run_note:
            invoice_payload["notes"] = run_note

        invoice = await self._api.create_invoice(invoice_payload)

        # Auto-send the invoice (creates AR journal entry)
        if invoice and invoice.get("id"):
            await self._api.send_invoice(UUID(invoice["id"]), UUID(ar_account_id))

        return invoice

    async def _create_bill(
        self,
        tx: GeneratedTransaction,
        bill_date: date,
        org_id: UUID,
    ) -> dict[str, Any] | None:
        """Create a bill - deterministic, no LLM reasoning needed."""
        if not tx.vendor_id:
            self._logger.warning("bill_missing_vendor", description=tx.description)
            return None

        # Get cached expense account
        account_info = await self._get_accounts_for_org(org_id)
        expense_account_id = account_info.get("expense_account_id")
        notes: str | None = None
        account_override: str | None = None

        if tx.metadata:
            override_value = tx.metadata.get("account_id_override")
            if isinstance(override_value, str) and override_value.strip():
                account_override = override_value.strip()
            notes_value = tx.metadata.get("notes")
            if isinstance(notes_value, str) and notes_value.strip():
                notes = notes_value.strip()

        if not expense_account_id:
            self._logger.warning(
                "bill_skipped_no_expense_account",
                description=tx.description,
                org_id=str(org_id),
            )
            return None

        due_date = bill_date + timedelta(days=30)  # Net 30 terms

        bill_number = f"BILL-{bill_date.strftime('%Y%m%d')}-{uuid4().hex[:4]}{self._run_suffix()}"
        vendor_bill_number = (
            f"SIMRUN-{self._run_id}"[:50] if self._run_id else None
        )
        line_account_id = account_override or expense_account_id
        bill_payload = {
            "vendor_id": str(tx.vendor_id),
            "bill_date": bill_date.isoformat(),
            "due_date": due_date.isoformat(),
            "bill_number": bill_number[:30],
            "lines": [
                {
                    "description": tx.description,
                    "quantity": "1",
                    "unit_price": str(tx.amount),
                    "expense_account_id": line_account_id,
                }
            ],
        }
        if notes:
            bill_payload["notes"] = notes
        if vendor_bill_number:
            bill_payload["vendor_bill_number"] = vendor_bill_number

        bill = await self._api.create_bill(bill_payload)

        return bill

    async def _record_payment(
        self,
        invoice_id: str,
        customer_id: UUID,
        amount: Decimal,
        payment_date: date,
        org_id: UUID,
    ) -> dict[str, Any] | None:
        """Record a customer payment - deterministic."""
        # Get cached accounts for AR and deposit
        account_info = await self._get_accounts_for_org(org_id)
        ar_account_id = account_info.get("ar_account_id")
        deposit_account_id = account_info.get("deposit_account_id")

        if not ar_account_id or not deposit_account_id:
            self._logger.warning(
                "payment_skipped_missing_accounts",
                ar_account=ar_account_id,
                deposit_account=deposit_account_id,
                org_id=str(org_id),
            )
            return None

        reference_number = f"PMT-{uuid4().hex[:6]}{self._run_suffix()}"
        payment = await self._api.create_payment(
            {
                "customer_id": str(customer_id),
                "amount": str(amount),
                "payment_date": payment_date.isoformat(),
                "payment_method": "check",
                "reference_number": reference_number[:100],
                "deposit_account_id": deposit_account_id,
            },
            ar_account_id=UUID(ar_account_id),
        )
        # Apply to invoice if payment was created
        if payment and payment.get("id"):
            try:
                await self._api.apply_payment_to_invoice(
                    UUID(payment["id"]),
                    UUID(invoice_id),
                    str(amount),
                )
            except Exception as e:
                details = e.details if isinstance(e, AtlasAPIError) else None
                self._logger.warning(
                    "payment_apply_failed",
                    error=str(e),
                    details=details,
                    invoice_id=str(invoice_id),
                    payment_id=str(payment.get("id")),
                    amount=str(amount),
                )
        return payment

    async def _pay_bill(
        self,
        bill_id: str,
        amount: Decimal,
        payment_date: date,
    ) -> dict[str, Any] | None:
        """Pay a vendor bill - deterministic."""
        payment = await self._api.create_bill_payment({
            "bill_id": bill_id,
            "amount": str(amount),
            "payment_date": payment_date.isoformat(),
            "payment_method": "check",
        })
        return payment

    # =========================================================================
    # VERIFICATION & REPORTING (Template-based - no LLM)
    # =========================================================================

    def _check_trial_balance(self, trial_balance: dict[str, Any]) -> bool:
        """Check if trial balance is balanced - simple comparison."""
        total_debits = Decimal(str(trial_balance.get("total_debits", 0)))
        total_credits = Decimal(str(trial_balance.get("total_credits", 0)))

        # Allow for small rounding differences
        return abs(total_debits - total_credits) < Decimal("0.01")

    async def _identify_issues(
        self,
        org_id: UUID,
        current_date: date,
    ) -> list[str]:
        """Identify accounting issues - rule-based, no LLM analysis."""
        issues = []

        # Check for overdue invoices
        overdue_invoices = await self._api.list_invoices(status="overdue")
        if overdue_invoices:
            total_overdue = sum(
                Decimal(str(inv.get("balance", 0))) for inv in overdue_invoices
            )
            issues.append(
                f"{len(overdue_invoices)} overdue invoices totaling ${total_overdue:,.2f}"
            )

        # Check for bills due soon
        upcoming_bills = await self._api.list_bills(status="pending")
        bills_due_soon = [
            b for b in upcoming_bills
            if self._is_due_within_days(b.get("due_date"), current_date, 7)
        ]
        if bills_due_soon:
            total_due = sum(
                Decimal(str(b.get("balance", 0))) for b in bills_due_soon
            )
            issues.append(
                f"{len(bills_due_soon)} bills due within 7 days totaling ${total_due:,.2f}"
            )

        # Check for large outstanding receivables
        ar_aging = await self._api.get_ar_aging()
        if ar_aging:
            over_90 = Decimal(str(ar_aging.get("over_90_days", 0)))
            if over_90 > Decimal("1000"):
                issues.append(f"${over_90:,.2f} in receivables over 90 days old")

        return issues

    def _is_due_within_days(
        self,
        due_date_str: str | None,
        current_date: date,
        days: int,
    ) -> bool:
        """Check if a date is within N days."""
        if not due_date_str:
            return False
        try:
            due_date = date.fromisoformat(due_date_str[:10])
            return current_date <= due_date <= current_date + timedelta(days=days)
        except (ValueError, TypeError):
            return False

    async def _generate_overdue_followups(
        self, period_end: date
    ) -> list[dict[str, Any]]:
        followups: list[dict[str, Any]] = []
        overdue_invoices = await self._api.list_invoices(status="overdue")
        for inv in overdue_invoices:
            due_date = self._parse_date(inv.get("due_date")) or self._parse_date(
                inv.get("invoice_date")
            )
            if not due_date or due_date > period_end:
                continue
            days_overdue = (period_end - due_date).days
            amount_due = (
                self._extract_decimal(inv.get("amount_due"))
                or self._extract_decimal(inv.get("balance"))
                or self._extract_decimal(inv.get("total_amount"))
                or Decimal("0")
            )
            if days_overdue >= 90:
                action = "Consider collection agency or write-off review"
            elif days_overdue >= 60:
                action = "Second notice + call customer"
            elif days_overdue >= 30:
                action = "Send payment reminder"
            else:
                action = "Friendly reminder"
            followups.append(
                {
                    "invoice_id": inv.get("id"),
                    "customer_id": inv.get("customer_id"),
                    "days_overdue": days_overdue,
                    "amount_due": str(amount_due),
                    "action": action,
                }
            )
        return followups

    async def _reconcile_bank_transactions(
        self,
        bank_transactions: list[dict[str, Any]],
        account_info: dict[str, Any],
        period_end: date,
    ) -> dict[str, Any]:
        summary = {
            "unmatched": 0,
            "matched": 0,
            "categorized": 0,
            "failed": 0,
        }
        if not bank_transactions:
            return summary

        payments_received = await self._fetch_all_payments()
        payments_made = await self._fetch_all_payments_made()

        def _index_by_amount(
            items: list[dict[str, Any]],
            date_key: str,
        ) -> dict[str, list[dict[str, Any]]]:
            index: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                amount = self._extract_decimal(item.get("amount"))
                if amount is None:
                    continue
                item_date = self._parse_date(item.get(date_key))
                if not item_date:
                    continue
                if abs((period_end - item_date).days) > 45:
                    continue
                key = str(amount.quantize(Decimal("0.01")))
                index.setdefault(key, []).append(item)
            return index

        payments_by_amount = _index_by_amount(payments_received, "payment_date")
        payments_made_by_amount = _index_by_amount(payments_made, "payment_date")
        used_payments: set[str] = set()

        for tx in bank_transactions:
            if tx.get("is_matched") or tx.get("matched") or tx.get("match_id"):
                continue

            summary["unmatched"] += 1
            tx_id = tx.get("id")
            if not tx_id:
                summary["failed"] += 1
                continue
            try:
                tx_uuid = UUID(str(tx_id))
            except (ValueError, TypeError):
                summary["failed"] += 1
                continue

            amount = self._extract_decimal(tx.get("absolute_amount")) or self._extract_decimal(
                tx.get("amount")
            )
            tx_date = self._parse_date(tx.get("transaction_date"))
            if amount is None or not tx_date:
                summary["failed"] += 1
                continue

            key = str(amount.quantize(Decimal("0.01")))
            if tx.get("is_deposit"):
                candidates = payments_by_amount.get(key, [])
                match_type = "payment"
                date_key = "payment_date"
            else:
                candidates = payments_made_by_amount.get(key, [])
                match_type = "bill_payment"
                date_key = "payment_date"

            matched = False
            for candidate in candidates:
                candidate_id = str(candidate.get("id"))
                if not candidate_id or candidate_id in used_payments:
                    continue
                candidate_date = self._parse_date(candidate.get(date_key))
                if not candidate_date:
                    continue
                if abs((candidate_date - tx_date).days) > 5:
                    continue
                try:
                    await self._api.match_bank_transaction(
                        tx_uuid,
                        UUID(candidate_id),
                        match_type,
                    )
                    used_payments.add(candidate_id)
                    summary["matched"] += 1
                    matched = True
                    break
                except AtlasAPIError:
                    summary["failed"] += 1
            if matched:
                continue

            account_id = (
                account_info.get("revenue_account_id")
                if tx.get("is_deposit")
                else account_info.get("expense_account_id")
            )
            if not account_id:
                summary["failed"] += 1
                continue
            try:
                await self._api.categorize_bank_transaction(
                    tx_uuid, UUID(str(account_id))
                )
                summary["categorized"] += 1
            except AtlasAPIError:
                summary["failed"] += 1

        return summary

    async def _generate_management_reports(
        self,
        period_start: date,
        period_end: date,
    ) -> dict[str, Any]:
        customers = await self._api.list_customers()
        vendors = await self._api.list_vendors()
        accounts = await self._api.list_accounts(limit=200)

        customer_map = {str(c.get("id")): c.get("display_name") for c in customers}
        vendor_map = {str(v.get("id")): v.get("display_name") for v in vendors}
        account_map = {str(a.get("id")): a.get("name") for a in accounts}

        invoices = await self._fetch_all_invoices()
        bills = await self._fetch_all_bills()

        revenue_by_customer: dict[str, Decimal] = {}
        for inv in invoices:
            inv_date = self._parse_date(inv.get("invoice_date"))
            if not inv_date or not (period_start <= inv_date <= period_end):
                continue
            amount = (
                self._extract_decimal(inv.get("total_amount"))
                or self._extract_decimal(inv.get("subtotal"))
                or Decimal("0")
            )
            customer_id = str(inv.get("customer_id") or "")
            customer_name = customer_map.get(customer_id) or customer_id or "Unknown"
            customer_name = str(customer_name)
            revenue_by_customer[customer_name] = revenue_by_customer.get(
                customer_name, Decimal("0")
            ) + amount

        expenses_by_category: dict[str, Decimal] = {}
        for bill in bills:
            bill_date = self._parse_date(bill.get("bill_date"))
            if not bill_date or not (period_start <= bill_date <= period_end):
                continue
            bill_id = bill.get("id")
            if not bill_id:
                continue
            try:
                detail = await self._api.get_bill(UUID(str(bill_id)))
            except AtlasAPIError:
                continue
            for line in detail.get("lines", []):
                account_id = line.get("expense_account_id") or line.get("account_id")
                category = account_map.get(str(account_id)) or "Uncategorized"
                category = str(category)
                qty = self._extract_decimal(line.get("quantity")) or Decimal("1")
                unit_price = (
                    self._extract_decimal(line.get("unit_price"))
                    or self._extract_decimal(line.get("amount"))
                    or Decimal("0")
                )
                line_amount = (qty * unit_price).quantize(Decimal("0.01"))
                expenses_by_category[category] = expenses_by_category.get(
                    category, Decimal("0")
                ) + line_amount

        def _top_n(values: dict[str, Decimal], count: int = 5) -> list[dict[str, Any]]:
            items = sorted(values.items(), key=lambda x: x[1], reverse=True)
            return [
                {"name": name, "amount": str(amount.quantize(Decimal("0.01")))}
                for name, amount in items[:count]
            ]

        revenue_total = sum(revenue_by_customer.values(), Decimal("0"))
        expense_total = sum(expenses_by_category.values(), Decimal("0"))

        top_vendors: dict[str, Decimal] = {}
        for bill in bills:
            vendor_id = bill.get("vendor_id")
            if not vendor_id:
                continue
            vendor_name = vendor_map.get(str(vendor_id)) or str(vendor_id)
            amount = (
                self._extract_decimal(bill.get("amount_due"))
                or self._extract_decimal(bill.get("amount"))
                or Decimal("0")
            )
            top_vendors[str(vendor_name)] = top_vendors.get(
                str(vendor_name), Decimal("0")
            ) + amount

        return {
            "revenue_by_customer": _top_n(revenue_by_customer),
            "expenses_by_category": _top_n(expenses_by_category),
            "revenue_total": str(revenue_total.quantize(Decimal("0.01"))),
            "expense_total": str(expense_total.quantize(Decimal("0.01"))),
            "top_vendors": _top_n(top_vendors),
        }

    async def _initialize_new_year_budget(self, year: int) -> dict[str, Any] | None:
        try:
            existing = await self._api.list_budgets(fiscal_year=year)
        except AtlasAPIError:
            existing = []
        if existing:
            return existing[0]
        payload = {
            "name": f"FY{year} Operating Budget",
            "fiscal_year": year,
            "period_type": "monthly",
            "start_date": date(year, 1, 1).isoformat(),
            "end_date": date(year, 12, 31).isoformat(),
            "description": "Auto-generated budget for new fiscal year",
        }
        try:
            return await self._api.create_budget(payload)
        except AtlasAPIError as exc:
            self._logger.warning("budget_create_failed", year=year, error=str(exc))
        return None

    async def _summarize_1099_activity(
        self, tax_year: int
    ) -> dict[str, Any]:
        payments_made = await self._fetch_all_payments_made()
        vendors = await self._api.list_vendors()
        vendor_map = {str(v.get("id")): v for v in vendors}

        totals: dict[str, Decimal] = {}
        for payment in payments_made:
            payment_date = self._parse_date(payment.get("payment_date"))
            if not payment_date or payment_date.year != tax_year:
                continue
            vendor_id = payment.get("vendor_id")
            if not vendor_id:
                continue
            amount = self._extract_decimal(payment.get("amount")) or Decimal("0")
            totals[str(vendor_id)] = totals.get(str(vendor_id), Decimal("0")) + amount

        threshold = Decimal("600")
        reportable_vendors: list[dict[str, Any]] = []
        missing_w9: list[str] = []
        for vendor_id, total in totals.items():
            if total < threshold:
                continue
            vendor = vendor_map.get(vendor_id, {})
            vendor_name = vendor.get("display_name") or vendor_id
            tax_profile = {}
            try:
                tax_profile = await self._api.get_vendor_tax_profile(UUID(vendor_id))
            except AtlasAPIError:
                tax_profile = {}
            tax_form_on_file = bool(tax_profile.get("tax_form_on_file"))
            is_tax_reportable = tax_profile.get("is_tax_reportable", True)
            reportable_vendors.append(
                {
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_name,
                    "total_paid": str(total.quantize(Decimal("0.01"))),
                    "tax_form_on_file": tax_form_on_file,
                    "is_tax_reportable": is_tax_reportable,
                }
            )
            if not tax_form_on_file:
                missing_w9.append(vendor_name)

        return {
            "vendors_over_threshold": len(reportable_vendors),
            "vendors_missing_w9": len(missing_w9),
            "missing_w9_vendors": missing_w9,
            "reportable_vendors": reportable_vendors,
        }

    async def _get_org_name(self, org_id: UUID) -> str:
        """Get organization name."""
        try:
            org = await self._api.get_organization(org_id)
        except Exception:
            return f"Organization {org_id}"

        name = org.get("name")
        if isinstance(name, str) and name.strip():
            return name
        return f"Org {org_id}"

    # =========================================================================
    # BATCH OPERATIONS (Efficient bulk processing)
    # =========================================================================

    async def run_month(
        self,
        business_key: str,
        org_id: UUID,
        year: int,
        month: int,
    ) -> list[DailySummary]:
        """Run accounting for an entire month - much faster without LLM.

        With LLM: ~30 seconds per day = ~15 minutes for a month
        Without LLM: ~1 second per day = ~30 seconds for a month
        """
        from calendar import monthrange

        _, num_days = monthrange(year, month)
        summaries = []

        for day in range(1, num_days + 1):
            current_date = date(year, month, day)

            # Skip weekends for some businesses
            if current_date.weekday() >= 5 and business_key in ["chen", "maya"]:
                continue

            summary = await self.run_daily_workflow(
                business_key=business_key,
                org_id=org_id,
                current_date=current_date,
            )
            summaries.append(summary)

        return summaries

    def generate_monthly_report(
        self,
        summaries: list[DailySummary],
    ) -> str:
        """Generate monthly report from daily summaries - template-based."""
        if not summaries:
            return "No data for this period."

        org_name = summaries[0].org_name
        month_start = summaries[0].date
        month_end = summaries[-1].date

        total_invoices = sum(s.invoices_created for s in summaries)
        total_invoice_amount = sum(s.invoices_total for s in summaries)
        total_payments = sum(s.payments_received for s in summaries)
        total_payment_amount = sum(s.payments_total for s in summaries)
        total_bills = sum(s.bills_created for s in summaries)
        total_bill_amount = sum(s.bills_total for s in summaries)
        total_bills_paid = sum(s.bills_paid for s in summaries)
        total_bills_paid_amount = sum(s.bills_paid_total for s in summaries)

        unbalanced_days = [s.date for s in summaries if not s.trial_balance_ok]
        all_issues = []
        for s in summaries:
            all_issues.extend(s.issues)

        collection_rate = (
            (total_payment_amount / total_invoice_amount * 100)
            if total_invoice_amount
            else 0
        )

        return f"""
Monthly Report: {org_name}
Period: {month_start} to {month_end}
{'=' * 60}

REVENUE SUMMARY
  Invoices Created: {total_invoices}
  Total Invoiced: ${total_invoice_amount:,.2f}
  Payments Received: {total_payments}
  Total Collected: ${total_payment_amount:,.2f}
  Collection Rate: {collection_rate:.1f}%

EXPENSE SUMMARY
  Bills Entered: {total_bills}
  Total Billed: ${total_bill_amount:,.2f}
  Bills Paid: {total_bills_paid}
  Total Paid: ${total_bills_paid_amount:,.2f}

NET ACTIVITY
  Net Revenue: ${total_payment_amount - total_bills_paid_amount:,.2f}

BOOKS STATUS
  Days with balanced books: {len(summaries) - len(unbalanced_days)}/{len(summaries)}
  {f"Unbalanced days: {unbalanced_days}" if unbalanced_days else "All days balanced ✓"}

{f"ISSUES IDENTIFIED ({len(all_issues)}):" if all_issues else "No issues identified."}
{chr(10).join(f"  - {issue}" for issue in all_issues[:10])}
{f"  ... and {len(all_issues) - 10} more" if len(all_issues) > 10 else ""}
""".strip()


# =============================================================================
# COMPARISON: LLM vs Non-LLM
# =============================================================================

"""
PERFORMANCE COMPARISON:

| Operation              | LLM-Based         | Rule-Based        |
|------------------------|-------------------|-------------------|
| Daily workflow         | ~20-30 seconds    | ~1-2 seconds      |
| Monthly workflow       | ~15 minutes       | ~30 seconds       |
| Create invoice         | ~2-3 seconds      | ~100ms            |
| Generate summary       | ~3-5 seconds      | ~1ms              |
| API cost               | $0.01-0.05/day    | $0                |

WHEN TO USE EACH:

LLM-Based (AccountantAgent):
  - Interactive demos where "thinking" adds value
  - User Q&A ("Why did expenses increase?")
  - Handling edge cases not covered by rules
  - Generating insights and analysis
  - When personality/narrative matters

Rule-Based (AccountingWorkflow):
  - Bulk data generation
  - Automated testing
  - Performance-critical paths
  - Reproducible simulations
  - Cost-sensitive environments

HYBRID APPROACH:
  # Use rule-based for transactions
  workflow = AccountingWorkflow(api_client)
  summary = await workflow.run_daily_workflow(...)

  # Use LLM only for analysis/Q&A
  if user_has_question:
      agent = AccountantAgent()
      response = await agent.run_task(
          f"Analyze this summary and answer: {user_question}\n{summary.to_text()}"
      )
"""
