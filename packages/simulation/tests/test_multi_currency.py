"""Tests for multi-currency support in AccountingWorkflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from atlas_town.accounting_workflow import (
    AccountingWorkflow,
    ExchangeRateSimulator,
    InternationalClientConfig,
    MultiCurrencyConfig,
)
from atlas_town.config.personas_loader import load_persona_multi_currency_configs


@dataclass
class FakeAPI:
    """Minimal fake API for testing multi-currency features."""

    accounts: list[dict[str, Any]] = field(default_factory=list)
    invoices: list[dict[str, Any]] = field(default_factory=list)
    bills: list[dict[str, Any]] = field(default_factory=list)
    journal_entries: list[dict[str, Any]] = field(default_factory=list)
    customers: list[dict[str, Any]] = field(default_factory=list)
    vendors: list[dict[str, Any]] = field(default_factory=list)
    trial_balance: dict[str, Any] = field(default_factory=dict)
    ar_aging: dict[str, Any] = field(default_factory=dict)
    ap_aging: dict[str, Any] = field(default_factory=dict)
    bank_transactions: list[dict[str, Any]] = field(default_factory=list)
    bank_accounts: list[dict[str, Any]] = field(default_factory=list)
    payments: list[dict[str, Any]] = field(default_factory=list)
    payments_made: list[dict[str, Any]] = field(default_factory=list)
    budgets: list[dict[str, Any]] = field(default_factory=list)
    current_company_id: UUID | None = None

    async def switch_organization(self, org_id: UUID) -> None:  # noqa: ARG002
        return None

    async def list_accounts(self, limit: int = 200) -> list[dict[str, Any]]:  # noqa: ARG002
        return self.accounts

    async def list_invoices(
        self, offset: int = 0, limit: int = 100, status: str | None = None  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        if status is None:
            return self.invoices
        return [inv for inv in self.invoices if inv.get("status") == status]

    async def list_bills(
        self, offset: int = 0, limit: int = 100, status: str | None = None  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.bills

    async def list_customers(self) -> list[dict[str, Any]]:
        return self.customers

    async def list_vendors(self) -> list[dict[str, Any]]:
        return self.vendors

    async def list_bank_transactions(
        self,
        bank_account_id: UUID,  # noqa: ARG002
        offset: int = 0,  # noqa: ARG002
        limit: int = 200,  # noqa: ARG002
        status_filter: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.bank_transactions

    async def list_bank_accounts(
        self, include_inactive: bool = False  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.bank_accounts

    async def list_payments(
        self, offset: int = 0, limit: int = 100  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.payments

    async def list_payments_made(
        self, offset: int = 0, limit: int = 100  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.payments_made

    async def list_budgets(
        self,
        offset: int = 0,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
        fiscal_year: int | None = None,  # noqa: ARG002
        status: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.budgets

    async def get_trial_balance(
        self, as_of_date: str | None = None  # noqa: ARG002
    ) -> dict[str, Any]:
        return self.trial_balance

    async def get_ar_aging(self) -> dict[str, Any]:
        return self.ar_aging

    async def get_ap_aging(self) -> dict[str, Any]:
        return self.ap_aging

    async def create_journal_entry(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        entry_id = str(uuid4())
        entry = {"id": entry_id, **payload}
        self.journal_entries.append(entry)
        return entry


# =============================================================================
# EXCHANGE RATE SIMULATOR TESTS
# =============================================================================


class TestExchangeRateSimulator:
    """Tests for ExchangeRateSimulator."""

    def test_deterministic_rates(self):
        """Same date/currency/run_id should always produce same rate."""
        sim1 = ExchangeRateSimulator(run_id="test-run-1")
        sim2 = ExchangeRateSimulator(run_id="test-run-1")

        test_date = date(2024, 6, 15)
        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        rate1 = sim1.get_rate("GBP", test_date, base_rate, volatility)
        rate2 = sim2.get_rate("GBP", test_date, base_rate, volatility)

        assert rate1 == rate2

    def test_different_run_ids_produce_different_rates(self):
        """Different run_ids should produce different rates."""
        sim1 = ExchangeRateSimulator(run_id="test-run-1")
        sim2 = ExchangeRateSimulator(run_id="test-run-2")

        test_date = date(2024, 6, 15)
        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        rate1 = sim1.get_rate("GBP", test_date, base_rate, volatility)
        rate2 = sim2.get_rate("GBP", test_date, base_rate, volatility)

        # Different run_ids should (almost certainly) produce different rates
        # There's a tiny chance they could be equal, but it's negligible
        assert rate1 != rate2

    def test_different_currencies_produce_different_rates(self):
        """Different currencies should produce different rates."""
        sim = ExchangeRateSimulator(run_id="test-run")

        test_date = date(2024, 6, 15)

        rate_gbp = sim.get_rate("GBP", test_date, Decimal("1.27"), Decimal("0.005"))
        rate_eur = sim.get_rate("EUR", test_date, Decimal("1.08"), Decimal("0.004"))

        assert rate_gbp != rate_eur

    def test_rate_varies_over_time(self):
        """Rates should vary day to day."""
        sim = ExchangeRateSimulator(run_id="test-run")

        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        rate_jan = sim.get_rate("GBP", date(2024, 1, 1), base_rate, volatility)
        rate_jun = sim.get_rate("GBP", date(2024, 6, 1), base_rate, volatility)
        rate_dec = sim.get_rate("GBP", date(2024, 12, 1), base_rate, volatility)

        # Rates should differ across the year
        assert len({rate_jan, rate_jun, rate_dec}) == 3

    def test_rate_stays_reasonable(self):
        """Rates should stay within reasonable bounds of base rate."""
        sim = ExchangeRateSimulator(run_id="stability-test")

        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        # Check rates over a year
        for day in range(365):
            test_date = date(2024, 1, 1) + timedelta(days=day)
            rate = sim.get_rate("GBP", test_date, base_rate, volatility)

            # Rate should be within ±30% of base rate (very generous bounds)
            assert rate > base_rate * Decimal("0.7"), f"Rate too low on {test_date}: {rate}"
            assert rate < base_rate * Decimal("1.3"), f"Rate too high on {test_date}: {rate}"

    def test_convert_to_usd(self):
        """Test currency conversion to USD."""
        sim = ExchangeRateSimulator(run_id="convert-test")

        foreign_amount = Decimal("1000.00")
        test_date = date(2024, 6, 15)
        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        usd_amount = sim.convert_to_usd(
            foreign_amount, "GBP", test_date, base_rate, volatility
        )

        # Should be roughly base_rate * foreign_amount (with some variation)
        expected_approx = foreign_amount * base_rate
        assert usd_amount > expected_approx * Decimal("0.7")
        assert usd_amount < expected_approx * Decimal("1.3")

    def test_calculate_fx_gain_loss(self):
        """Test FX gain/loss calculation."""
        sim = ExchangeRateSimulator(run_id="fx-gain-test")

        foreign_amount = Decimal("10000.00")
        invoice_date = date(2024, 1, 15)
        payment_date = date(2024, 2, 15)
        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        gain_loss = sim.calculate_fx_gain_loss(
            foreign_amount,
            "GBP",
            invoice_date,
            payment_date,
            base_rate,
            volatility,
        )

        # The gain/loss should be the difference in USD values
        invoice_usd = sim.convert_to_usd(
            foreign_amount, "GBP", invoice_date, base_rate, volatility
        )
        payment_usd = sim.convert_to_usd(
            foreign_amount, "GBP", payment_date, base_rate, volatility
        )

        assert gain_loss == payment_usd - invoice_usd

    def test_caching(self):
        """Test that rates are cached for efficiency."""
        sim = ExchangeRateSimulator(run_id="cache-test")

        test_date = date(2024, 6, 15)
        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        # First call should compute and cache
        rate1 = sim.get_rate("GBP", test_date, base_rate, volatility)

        # Check cache was populated
        cache_key = ("GBP", test_date)
        assert cache_key in sim._rate_cache

        # Second call should return cached value
        rate2 = sim.get_rate("GBP", test_date, base_rate, volatility)
        assert rate1 == rate2


# =============================================================================
# CONFIG LOADING TESTS
# =============================================================================


class TestMultiCurrencyConfigLoading:
    """Tests for multi-currency config loading from YAML."""

    def test_load_maya_config(self):
        """Test that Maya's multi-currency config loads correctly."""
        configs = load_persona_multi_currency_configs()

        assert "maya" in configs
        maya_config = configs["maya"]

        assert maya_config["enabled"] is True
        assert maya_config["base_currency"] == "USD"
        assert maya_config["revaluation_enabled"] is True
        assert maya_config["fx_gain_loss_account_name"] == "Foreign Exchange Gain/Loss"

        clients = maya_config["clients"]
        assert len(clients) == 3

        # Check each client
        client_names = {c["name"] for c in clients}
        assert "TechCorp UK Ltd" in client_names
        assert "EuroSoft GmbH" in client_names
        assert "Maple Tech Solutions" in client_names

    def test_client_config_values(self):
        """Test that client config values are correct types."""
        configs = load_persona_multi_currency_configs()
        maya_config = configs["maya"]

        for client in maya_config["clients"]:
            assert isinstance(client["name"], str)
            assert isinstance(client["currency"], str)
            assert isinstance(client["base_rate"], Decimal)
            assert isinstance(client["volatility"], Decimal)
            assert isinstance(client["invoice_probability"], float)
            assert isinstance(client["min_amount"], Decimal)
            assert isinstance(client["max_amount"], Decimal)
            assert isinstance(client["payment_terms_days"], int)
            assert isinstance(client["payment_reliability"], float)

            # Validate ranges
            assert 0 <= client["invoice_probability"] <= 1
            assert 0 <= client["payment_reliability"] <= 1
            assert client["min_amount"] < client["max_amount"]
            assert client["payment_terms_days"] > 0

    def test_only_maya_has_config(self):
        """Test that only Maya has multi-currency config (as designed)."""
        configs = load_persona_multi_currency_configs()

        # Maya should be the only one with multi-currency enabled
        assert "maya" in configs
        # Other businesses shouldn't have multi-currency
        assert "craig" not in configs
        assert "tony" not in configs
        assert "chen" not in configs
        assert "marcus" not in configs


# =============================================================================
# WORKFLOW INTEGRATION TESTS
# =============================================================================


class TestWorkflowMultiCurrencyIntegration:
    """Tests for multi-currency integration in AccountingWorkflow."""

    @pytest.fixture
    def fake_api(self):
        """Create a fake API with necessary accounts."""
        return FakeAPI(
            accounts=[
                {"id": str(uuid4()), "name": "Accounts Receivable", "account_type": "asset"},
                {"id": str(uuid4()), "name": "Service Revenue", "account_type": "revenue"},
                {"id": str(uuid4()), "name": "Foreign Exchange Gain/Loss", "account_type": "revenue"},
                {"id": str(uuid4()), "name": "Operating Expenses", "account_type": "expense"},
                {"id": str(uuid4()), "name": "Accrued Liabilities", "account_type": "liability"},
            ],
            trial_balance={"total_debit": "10000.00", "total_credit": "10000.00"},
        )

    @pytest.fixture
    def workflow(self, fake_api):
        """Create a workflow instance with fake API."""
        return AccountingWorkflow(api_client=fake_api, run_id="test-run-123")

    def test_workflow_loads_multi_currency_configs(self, workflow):
        """Test that workflow loads multi-currency configs on init."""
        maya_config = workflow.get_multi_currency_config("maya")
        assert maya_config is not None
        assert maya_config.enabled is True
        assert len(maya_config.clients) == 3

    def test_workflow_has_exchange_rate_simulator(self, workflow):
        """Test that workflow has exchange rate simulator."""
        assert workflow._exchange_rate_simulator is not None
        assert isinstance(workflow._exchange_rate_simulator, ExchangeRateSimulator)

    def test_track_foreign_ar(self, workflow):
        """Test tracking foreign AR invoices."""
        invoice_id = uuid4()
        currency = "GBP"
        foreign_amount = Decimal("5000.00")
        usd_amount = Decimal("6350.00")
        invoice_date = date(2024, 6, 15)
        base_rate = Decimal("1.27")
        volatility = Decimal("0.005")

        workflow.track_foreign_ar(
            invoice_id=invoice_id,
            currency=currency,
            foreign_amount=foreign_amount,
            usd_amount=usd_amount,
            invoice_date=invoice_date,
            base_rate=base_rate,
            volatility=volatility,
        )

        tracking_key = (invoice_id, currency)
        assert tracking_key in workflow._foreign_ar_tracking

        tracking = workflow._foreign_ar_tracking[tracking_key]
        assert tracking["foreign_amount"] == foreign_amount
        assert tracking["usd_amount"] == usd_amount
        assert tracking["invoice_date"] == invoice_date

    def test_no_config_for_non_multi_currency_businesses(self, workflow):
        """Test that businesses without multi-currency config return None."""
        assert workflow.get_multi_currency_config("craig") is None
        assert workflow.get_multi_currency_config("tony") is None
        assert workflow.get_multi_currency_config("chen") is None
        assert workflow.get_multi_currency_config("marcus") is None


# =============================================================================
# DATACLASS TESTS
# =============================================================================


class TestDataclasses:
    """Tests for multi-currency dataclasses."""

    def test_international_client_config_frozen(self):
        """Test that InternationalClientConfig is immutable."""
        config = InternationalClientConfig(
            name="Test Client",
            currency="GBP",
            base_rate=Decimal("1.27"),
            volatility=Decimal("0.005"),
            invoice_probability=0.15,
            min_amount=Decimal("3000"),
            max_amount=Decimal("25000"),
            payment_terms_days=30,
            payment_reliability=0.90,
        )

        with pytest.raises(AttributeError):
            config.name = "Changed Name"  # type: ignore

    def test_multi_currency_config_frozen(self):
        """Test that MultiCurrencyConfig is immutable."""
        client = InternationalClientConfig(
            name="Test Client",
            currency="GBP",
            base_rate=Decimal("1.27"),
            volatility=Decimal("0.005"),
            invoice_probability=0.15,
            min_amount=Decimal("3000"),
            max_amount=Decimal("25000"),
            payment_terms_days=30,
            payment_reliability=0.90,
        )

        config = MultiCurrencyConfig(
            enabled=True,
            base_currency="USD",
            clients=(client,),
            revaluation_enabled=True,
            fx_gain_loss_account_name="Foreign Exchange Gain/Loss",
        )

        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore

    def test_multi_currency_config_clients_tuple(self):
        """Test that clients in MultiCurrencyConfig is a tuple (immutable)."""
        client = InternationalClientConfig(
            name="Test Client",
            currency="GBP",
            base_rate=Decimal("1.27"),
            volatility=Decimal("0.005"),
            invoice_probability=0.15,
            min_amount=Decimal("3000"),
            max_amount=Decimal("25000"),
            payment_terms_days=30,
            payment_reliability=0.90,
        )

        config = MultiCurrencyConfig(
            enabled=True,
            base_currency="USD",
            clients=(client,),
            revaluation_enabled=True,
            fx_gain_loss_account_name="Foreign Exchange Gain/Loss",
        )

        assert isinstance(config.clients, tuple)
