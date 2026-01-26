"""Orchestrator - coordinates agents and simulation lifecycle.

The orchestrator is the main coordinator for the Atlas Town simulation.
It manages:
- Multiple organizations and their owner agents
- The accountant agent (Sarah) who visits each business
- Customer and vendor agents for generating transactions
- Event publishing for real-time frontend updates
- Daily simulation cycles with phase transitions

Supports three modes:
- LLM: Full agent reasoning with Claude/GPT/Gemini (default)
- FAST: Rule-based workflow, no LLM calls (15x faster, $0 cost)
- HYBRID: Rule-based operations + LLM for analysis
"""

import asyncio
import json
import os
import random
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from atlas_town.accounting_workflow import AccountingWorkflow, CollectionSummary
from atlas_town.agents import (
    AccountantAgent,
    CustomerAgent,
    OwnerAgent,
    VendorAgent,
    create_all_owners,
    create_customers_for_industry,
    create_vendors_for_industry,
)
from atlas_town.agents.vendor import VENDOR_ARCHETYPES, VendorType
from atlas_town.b2b import B2BCoordinator, B2BPlannedPair, build_b2b_note
from atlas_town.clients import ClaudeClient, GeminiClient, OpenAIClient
from atlas_town.config import get_settings
from atlas_town.config.personas_loader import (
    load_persona_payroll_configs,
    load_persona_sales_tax_configs,
    load_persona_tax_configs,
)
from atlas_town.economics import InflationModel, get_inflation_model
from atlas_town.events import (
    EventPublisher,
    agent_moving,
    agent_speaking,
    agent_thinking,
    day_completed,
    day_started,
    error_event,
    get_publisher,
    org_visited,
    phase_completed,
    phase_started,
    simulation_started,
    simulation_stopped,
    transaction_created,
)
from atlas_town.scheduler import DayPhase, Scheduler
from atlas_town.tools import AtlasAPIClient, AtlasAPIError, ToolExecutor
from atlas_town.transactions import (
    GeneratedTransaction,
    QuarterlyTaxAction,
    TransactionType,
    create_transaction_generator,
)

logger = structlog.get_logger(__name__)


class SimulationMode(str, Enum):
    """Simulation mode determining how accounting operations are handled."""

    LLM = "llm"  # Full LLM agent reasoning (default, slower, costs money)
    FAST = "fast"  # Rule-based workflow (15x faster, no API cost)
    HYBRID = "hybrid"  # Rule-based ops + LLM for analysis when issues detected


@dataclass
class OrganizationContext:
    """Context for a single organization in the simulation."""

    id: UUID
    name: str
    industry: str
    owner_key: str  # Key in OWNER_PERSONAS (craig, tony, maya, chen, marcus)
    owner: OwnerAgent | None = None
    customers: list[CustomerAgent] = field(default_factory=list)
    vendors: list[VendorAgent] = field(default_factory=list)


class Orchestrator:
    """Main coordinator for the Atlas Town simulation.

    The orchestrator:
    1. Manages the Atlas API connection and tool execution
    2. Creates and coordinates all agent types
    3. Tracks simulation state (day, phase, events)
    4. Publishes events via WebSocket for the frontend
    5. Runs the daily simulation cycle

    Usage:
        async with Orchestrator() as orch:
            # Run a single day
            await orch.run_daily_cycle()

            # Or run continuously
            await orch.run_simulation(max_days=30)
    """

    def __init__(
        self,
        event_publisher: EventPublisher | None = None,
        start_websocket: bool = True,
        mode: SimulationMode = SimulationMode.LLM,
    ):
        settings = get_settings()

        # Simulation mode
        self._mode = mode

        # API client and tools
        self._api_client: AtlasAPIClient | None = None
        self._tool_executor: ToolExecutor | None = None

        # LLM clients (created on demand, not needed for FAST mode)
        self._claude_client: ClaudeClient | None = None
        self._openai_client: OpenAIClient | None = None
        self._gemini_client: GeminiClient | None = None

        # Agents (not needed for FAST mode)
        self._accountant: AccountantAgent | None = None
        self._owners: dict[str, OwnerAgent] = {}

        # Rule-based workflow (for FAST and HYBRID modes)
        self._accounting_workflow: AccountingWorkflow | None = None
        self._accounting_workflows: dict[UUID, AccountingWorkflow] = {}

        # Organizations
        self._organizations: dict[UUID, OrganizationContext] = {}
        self._org_by_owner: dict[str, UUID] = {}  # owner_key -> org_id
        self._org_clients_by_id: dict[UUID, AtlasAPIClient] = {}
        self._multi_org_enabled = False

        # Scheduler - use very high speed for fast mode (effectively no delays)
        speed = settings.simulation_speed
        if mode == SimulationMode.FAST:
            speed = 10000.0  # Effectively instant phase transitions
        self._scheduler = Scheduler(speed_multiplier=speed)

        # Event publishing
        self._event_publisher = event_publisher or get_publisher()
        self._start_websocket = start_websocket

        # Transaction generator for realistic daily activity
        self._inflation: InflationModel = get_inflation_model()
        self._tx_generator = create_transaction_generator(inflation=self._inflation)

        # State
        self._is_initialized = False
        self._current_org_id: UUID | None = None
        self._run_id = settings.simulation_run_id or str(uuid4())
        self._run_id_short = self._run_id.split("-")[0]

        # Account cache per org (for payment endpoints that need AR, AP, deposit accounts)
        self._account_cache: dict[UUID, dict[str, Any]] = {}

        # Quarterly tax tracking per org (estimate_id, bill_id)
        self._quarterly_tax_records: dict[tuple[UUID, int, int], dict[str, str]] = {}

        # Period-end tracking for LLM mode
        self._month_end_llm_done: set[tuple[UUID, int, int]] = set()

        # Vendor price increase notifications (per org/vendor/year)
        self._vendor_price_increase_sent: set[tuple[UUID, str, int]] = set()
        self._quarter_end_llm_done: set[tuple[UUID, int, int]] = set()
        self._year_end_llm_done: set[tuple[UUID, int]] = set()
        self._year_end_reporting_done: set[tuple[UUID, int]] = set()

        # B2B paired transaction coordinator
        self._b2b_coordinator: B2BCoordinator | None = None
        self._b2b_pairs_created: set[str] = set()

        # Logging
        self._logger = logger.bind(
            component="orchestrator", mode=mode.value, sim_run_id=self._run_id
        )

    async def __aenter__(self) -> "Orchestrator":
        """Initialize the orchestrator."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Cleanup resources."""
        await self.shutdown()

    async def initialize(self) -> None:
        """Initialize API client, tools, agents, and event publisher."""
        if self._is_initialized:
            return

        self._logger.info("initializing_orchestrator")

        # Start WebSocket server
        if self._start_websocket and not self._event_publisher.is_running:
            await self._event_publisher.start()

        # Create and authenticate API client(s)
        self._multi_org_enabled = self._should_use_multi_org()
        if self._multi_org_enabled:
            await self._setup_multi_orgs_from_credentials()
            if not self._organizations:
                self._logger.warning("multi_org_fallback_to_single")
                self._multi_org_enabled = False
        if not self._multi_org_enabled:
            self._api_client = AtlasAPIClient()
            await self._api_client.login()
            await self._setup_organizations()

        if self._multi_org_enabled and not self._api_client:
            raise RuntimeError("Multi-org setup failed: no API client available")

        # Create tool executor
        if self._api_client:
            self._tool_executor = ToolExecutor(self._api_client)

        # Create accounting workflow(s) (used across all modes for shared logic)
        if self._multi_org_enabled:
            for org_id, client in self._org_clients_by_id.items():
                self._accounting_workflows[org_id] = AccountingWorkflow(
                    api_client=client,
                    transaction_generator=self._tx_generator,
                    run_id=self._run_id,
                )
        else:
            assert self._api_client is not None
            self._accounting_workflow = AccountingWorkflow(
                api_client=self._api_client,
                transaction_generator=self._tx_generator,
                run_id=self._run_id,
            )
        self._logger.info("accounting_workflow_initialized", mode=self._mode.value)

        # Initialize B2B coordinator and seed vendors
        self._initialize_b2b()
        await self._ensure_payroll_vendors()
        await self._ensure_tax_vendors()
        await self._ensure_sales_tax_vendors()
        await self._ensure_1099_vendors()

        # Only create LLM agents if not in FAST mode
        if self._mode != SimulationMode.FAST:
            self._create_agents()
        else:
            self._logger.info("skipping_agent_creation", reason="fast_mode")

        # Register scheduler phase handlers
        self._register_phase_handlers()

        self._is_initialized = True

        self._logger.info(
            "orchestrator_initialized",
            org_count=len(self._organizations),
            owner_count=len(self._owners),
        )

    async def shutdown(self) -> None:
        """Cleanup and shutdown."""
        self._logger.info("shutting_down_orchestrator")

        self._scheduler.stop()

        if self._org_clients_by_id:
            for client in self._org_clients_by_id.values():
                await client.close()
        elif self._api_client:
            await self._api_client.close()

        if self._start_websocket and self._event_publisher.is_running:
            await self._event_publisher.stop()

        self._is_initialized = False

    @staticmethod
    def _parse_bool(value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None

    def _multi_org_credentials_path(self) -> Path:
        override = os.getenv("SIM_MULTI_ORG_CREDENTIALS")
        if override:
            return Path(override).expanduser()
        return Path(__file__).resolve().parents[2] / "business_credentials.json"

    def _should_use_multi_org(self) -> bool:
        flag = self._parse_bool(os.getenv("SIM_MULTI_ORG"))
        if flag is not None:
            return flag
        return self._multi_org_credentials_path().exists()

    async def _setup_multi_orgs_from_credentials(self) -> None:
        """Load organizations using per-org credentials (multi-org mode)."""
        path = self._multi_org_credentials_path()
        if not path.exists():
            self._logger.warning("multi_org_credentials_missing", path=str(path))
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._logger.warning("multi_org_credentials_invalid", path=str(path))
            return

        if not isinstance(raw, dict):
            self._logger.warning("multi_org_credentials_not_mapping", path=str(path))
            return

        for owner_key, info in raw.items():
            if not isinstance(info, dict):
                continue
            email = info.get("email")
            password = info.get("password")
            if not email or not password:
                self._logger.warning(
                    "multi_org_credentials_incomplete",
                    owner_key=owner_key,
                )
                continue

            client = AtlasAPIClient(username=str(email), password=str(password))
            try:
                await client.login()
            except AtlasAPIError as exc:
                self._logger.warning(
                    "multi_org_login_failed",
                    owner_key=owner_key,
                    error=str(exc),
                )
                continue

            org_data = client.organizations[0] if client.organizations else {}
            org_id_raw = org_data.get("id") or info.get("organization_id")
            if not org_id_raw:
                self._logger.warning(
                    "multi_org_missing_org_id",
                    owner_key=owner_key,
                )
                continue

            try:
                org_id = UUID(str(org_id_raw))
            except ValueError:
                self._logger.warning(
                    "multi_org_invalid_org_id",
                    owner_key=owner_key,
                    org_id=str(org_id_raw),
                )
                continue

            name = (
                org_data.get("name")
                or info.get("organization_name")
                or owner_key
            )
            industry = org_data.get("industry", "general")

            ctx = OrganizationContext(
                id=org_id,
                name=str(name),
                industry=str(industry),
                owner_key=str(owner_key),
            )
            self._organizations[org_id] = ctx
            self._org_by_owner[str(owner_key)] = org_id
            self._org_clients_by_id[org_id] = client

            if self._api_client is None:
                self._api_client = client
                self._current_org_id = org_id

        self._logger.info(
            "multi_orgs_loaded",
            count=len(self._organizations),
        )

    async def _setup_organizations(self) -> None:
        """Load organizations from API and map to owner personas."""
        if not self._api_client:
            return

        # Owner persona mapping by business name keywords
        owner_mapping = {
            "landscaping": "craig",
            "craig": "craig",
            "pizza": "tony",
            "pizzeria": "tony",
            "tony": "tony",
            "nexus": "maya",
            "tech": "maya",
            "consulting": "maya",
            "dental": "chen",
            "dentist": "chen",
            "main street": "chen",
            "realty": "marcus",
            "harbor": "marcus",
            "real estate": "marcus",
        }

        for org_data in self._api_client.organizations:
            org_id = UUID(org_data["id"])
            name = org_data.get("name", "Unknown")
            industry = org_data.get("industry", "general")

            # Determine owner based on name/industry
            owner_key = "craig"  # Default
            name_lower = name.lower()
            industry_lower = industry.lower()

            for keyword, key in owner_mapping.items():
                if keyword in name_lower or keyword in industry_lower:
                    owner_key = key
                    break

            ctx = OrganizationContext(
                id=org_id,
                name=name,
                industry=industry,
                owner_key=owner_key,
            )
            self._organizations[org_id] = ctx
            self._org_by_owner[owner_key] = org_id

        self._logger.info("organizations_loaded", count=len(self._organizations))

    def _initialize_b2b(self) -> None:
        orgs_by_key = {ctx.owner_key: ctx for ctx in self._organizations.values()}
        if not orgs_by_key:
            return
        self._b2b_coordinator = B2BCoordinator(orgs_by_key, inflation=self._inflation)

    @staticmethod
    def _normalize_vendor_name(name: str) -> str:
        return " ".join(name.split()).strip().lower()

    @staticmethod
    def _vendor_email_from_name(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "", name.lower()) or "vendor"
        return f"{slug}@atlastown.example.com"

    @staticmethod
    def _normalize_customer_name(name: str) -> str:
        return " ".join(name.split()).strip().lower()

    @staticmethod
    def _customer_email_from_name(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "", name.lower()) or "customer"
        return f"{slug}@atlastown.example.com"

    @staticmethod
    def _find_customer_id_by_name(
        customer_name: str | None,
        customers: list[dict[str, Any]],
    ) -> UUID | None:
        if not customers:
            return None
        if customer_name:
            normalized = Orchestrator._normalize_customer_name(customer_name)
            for customer in customers:
                name = str(
                    customer.get("display_name") or customer.get("name", "")
                ).strip().lower()
                if name == normalized or name in normalized or normalized in name:
                    try:
                        return UUID(customer["id"])
                    except (KeyError, ValueError, TypeError):
                        continue
        return None

    async def _ensure_vendor_present(
        self,
        vendors: list[dict[str, Any]],
        vendor_name: str,
    ) -> None:
        if not self._api_client:
            return

        normalized = self._normalize_vendor_name(vendor_name)
        for vendor in vendors:
            existing_name = (
                vendor.get("display_name")
                or vendor.get("name", "")
            )
            if normalized == self._normalize_vendor_name(str(existing_name)):
                return

        payload = {
            "display_name": vendor_name,
            "email": self._vendor_email_from_name(vendor_name),
            "payment_terms": "net_15",
        }
        try:
            created = await self._api_client.create_vendor(payload)
            if created:
                vendors.append(created)
            self._logger.info(
                "payroll_vendor_created",
                vendor=vendor_name,
            )
        except AtlasAPIError as exc:
            if exc.status_code == 422:
                fallback_payload = payload.copy()
                fallback_payload.pop("email", None)
                try:
                    created = await self._api_client.create_vendor(fallback_payload)
                    if created:
                        vendors.append(created)
                    self._logger.info(
                        "payroll_vendor_created",
                        vendor=vendor_name,
                    )
                    return
                except AtlasAPIError:
                    pass
            self._logger.warning(
                "payroll_vendor_create_failed",
                vendor=vendor_name,
                error=str(exc),
            )

    async def _ensure_customer_present(
        self,
        customers: list[dict[str, Any]],
        customer_name: str,
    ) -> None:
        if not self._api_client:
            return

        normalized = self._normalize_customer_name(customer_name)
        for customer in customers:
            existing_name = (
                customer.get("display_name")
                or customer.get("name", "")
            )
            if normalized == self._normalize_customer_name(str(existing_name)):
                return

        payload = {
            "display_name": customer_name,
            "email": self._customer_email_from_name(customer_name),
            "payment_terms": "net_30",
        }
        try:
            created = await self._api_client.create_customer(payload)
            if created:
                customers.append(created)
            self._logger.info(
                "b2b_customer_created",
                customer=customer_name,
            )
        except AtlasAPIError as exc:
            if exc.status_code == 422:
                fallback_payload = payload.copy()
                fallback_payload.pop("email", None)
                try:
                    created = await self._api_client.create_customer(fallback_payload)
                    if created:
                        customers.append(created)
                    self._logger.info(
                        "b2b_customer_created",
                        customer=customer_name,
                    )
                    return
                except AtlasAPIError:
                    pass
            self._logger.warning(
                "b2b_customer_create_failed",
                customer=customer_name,
                error=str(exc),
            )

    async def _ensure_payroll_vendors(self) -> None:
        if not self._api_client:
            return

        payroll_configs = load_persona_payroll_configs()
        if not payroll_configs:
            return

        for org_id, ctx in self._organizations.items():
            config = payroll_configs.get(ctx.owner_key)
            if not config:
                continue

            raw_vendor_names = [
                config.get("payroll_vendor"),
                config.get("tax_authority"),
            ]
            vendor_names: list[str] = [str(name) for name in raw_vendor_names if name]
            if not vendor_names:
                continue

            try:
                await self.switch_organization(org_id)
                vendors = await self._api_client.list_vendors()
            except AtlasAPIError as exc:
                self._logger.warning(
                    "payroll_vendor_list_failed",
                    org=ctx.name,
                    error=str(exc),
                )
                continue

            for vendor_name in vendor_names:
                await self._ensure_vendor_present(vendors, vendor_name)

    async def _ensure_tax_vendors(self) -> None:
        if not self._api_client:
            return

        tax_configs = load_persona_tax_configs()
        if not tax_configs:
            return

        for org_id, ctx in self._organizations.items():
            config = tax_configs.get(ctx.owner_key)
            if not config:
                continue

            tax_vendor = config.get("tax_vendor")
            vendor_name = str(tax_vendor) if tax_vendor else None
            if not vendor_name:
                continue

            try:
                await self.switch_organization(org_id)
                vendors = await self._api_client.list_vendors()
            except AtlasAPIError as exc:
                self._logger.warning(
                    "tax_vendor_list_failed",
                    org=ctx.name,
                    error=str(exc),
                )
                continue

            await self._ensure_vendor_present(vendors, vendor_name)

    async def _ensure_sales_tax_vendors(self) -> None:
        if not self._api_client:
            return

        tax_configs = load_persona_sales_tax_configs()
        if not tax_configs:
            return

        for org_id, ctx in self._organizations.items():
            config = tax_configs.get(ctx.owner_key)
            if not config or not config.get("enabled"):
                continue

            tax_authority = config.get("tax_authority") or "State Tax Authority"
            vendor_name = str(tax_authority).strip()
            if not vendor_name:
                continue

            try:
                await self.switch_organization(org_id)
                vendors = await self._api_client.list_vendors()
            except AtlasAPIError as exc:
                self._logger.warning(
                    "sales_tax_vendor_list_failed",
                    org=ctx.name,
                    error=str(exc),
                )
                continue

            await self._ensure_vendor_present(vendors, vendor_name)

    async def _ensure_1099_vendors(self) -> None:
        if not self._api_client:
            return

        for org_id, ctx in self._organizations.items():
            profiles = VENDOR_ARCHETYPES.get(ctx.industry, [])
            vendor_names = [
                profile.name
                for profile in profiles
                if profile.vendor_type == VendorType.SERVICE
            ]
            if not vendor_names:
                continue

            try:
                await self.switch_organization(org_id)
                vendors = await self._api_client.list_vendors()
            except AtlasAPIError as exc:
                self._logger.warning(
                    "vendor_list_failed",
                    org=ctx.name,
                    error=str(exc),
                )
                continue

            for vendor_name in vendor_names:
                await self._ensure_vendor_present(vendors, vendor_name)

    def _create_agents(self) -> None:
        """Create all agent instances."""
        # Create accountant (Sarah)
        self._accountant = AccountantAgent()
        if self._tool_executor:
            self._accountant.set_tool_executor(self._tool_executor)

        # Create owners for each organization
        self._owners = create_all_owners(self._org_by_owner)

        # Assign owners to organizations and create customers/vendors
        for _org_id, ctx in self._organizations.items():
            # Assign owner
            if ctx.owner_key in self._owners:
                ctx.owner = self._owners[ctx.owner_key]

            # Create industry-specific customers and vendors
            ctx.customers = create_customers_for_industry(ctx.industry)
            ctx.vendors = create_vendors_for_industry(ctx.industry)

        self._logger.info(
            "agents_created",
            accountant=self._accountant.name if self._accountant else None,
            owners=list(self._owners.keys()),
        )

    def _register_phase_handlers(self) -> None:
        """Register handlers for each simulation phase."""
        self._scheduler.register_phase_handler(
            DayPhase.EARLY_MORNING, self._handle_early_morning
        )
        self._scheduler.register_phase_handler(
            DayPhase.MORNING, self._handle_morning
        )
        self._scheduler.register_phase_handler(
            DayPhase.LUNCH, self._handle_lunch
        )
        self._scheduler.register_phase_handler(
            DayPhase.AFTERNOON, self._handle_afternoon
        )
        self._scheduler.register_phase_handler(
            DayPhase.EVENING, self._handle_evening
        )
        self._scheduler.register_phase_handler(
            DayPhase.NIGHT, self._handle_night
        )

    # === Properties ===

    @property
    def scheduler(self) -> Scheduler:
        """Get the scheduler."""
        return self._scheduler

    @property
    def accountant(self) -> AccountantAgent | None:
        """Get the accountant agent."""
        return self._accountant

    @property
    def owners(self) -> dict[str, OwnerAgent]:
        """Get all owner agents."""
        return self._owners.copy()

    @property
    def organizations(self) -> list[OrganizationContext]:
        """Get all organizations."""
        return list(self._organizations.values())

    @property
    def current_org(self) -> OrganizationContext | None:
        """Get the current organization context."""
        if self._current_org_id:
            return self._organizations.get(self._current_org_id)
        return None

    # === Organization Management ===

    async def switch_organization(self, org_id: UUID) -> None:
        """Switch to a different organization context."""
        if org_id not in self._organizations:
            raise ValueError(f"Unknown organization: {org_id}")

        if not self._api_client:
            raise RuntimeError("Orchestrator not initialized")

        ctx = self._organizations[org_id]
        previous_org = self.current_org

        # Switch API context
        if self._org_clients_by_id:
            client = self._org_clients_by_id.get(org_id)
            if not client:
                raise RuntimeError(f"No API client for org {org_id}")
            self._api_client = client
            if self._tool_executor:
                self._tool_executor.client = client
            if client.current_org_id != org_id:
                await client.switch_organization(org_id)
        else:
            await self._api_client.switch_organization(org_id)
        self._current_org_id = org_id

        # Update accountant context
        if self._accountant:
            self._accountant.set_organization(org_id)

        # Publish movement event (Sarah walks to new building)
        if self._accountant and previous_org:
            self._event_publisher.publish(
                agent_moving(
                    agent_id=self._accountant.id,
                    agent_name=self._accountant.name,
                    from_location=previous_org.name,
                    to_location=ctx.name,
                    reason="Visiting for accounting duties",
                )
            )

        # Publish visit event
        if self._accountant:
            self._event_publisher.publish(
                org_visited(
                    agent_id=self._accountant.id,
                    agent_name=self._accountant.name,
                    org_id=org_id,
                    org_name=ctx.name,
                )
            )

        self._logger.info("organization_switched", org_id=str(org_id), name=ctx.name)

    # === Helper Methods for Transaction Generation ===

    def _find_revenue_account(self, accounts: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Find a revenue account using multiple strategies.

        Tries in order:
        1. account_type == "revenue" (most correct)
        2. account_number starting with "4" (US GAAP revenue accounts)
        3. name containing "revenue" (fallback)
        """
        # Strategy 1: By account_type (most reliable if available)
        account = next(
            (a for a in accounts if a.get("account_type") == "revenue"),
            None
        )
        if account:
            return account

        # Strategy 2: By account_number (US GAAP: 4xxx = Revenue)
        account = next(
            (a for a in accounts if str(a.get("account_number", "")).startswith("4")),
            None
        )
        if account:
            return account

        # Strategy 3: By name containing "revenue" (last resort)
        account = next(
            (a for a in accounts if "revenue" in a.get("name", "").lower()),
            None
        )
        return account

    def _find_expense_account(
        self,
        accounts: list[dict[str, Any]],
        hint: str | None = None,
    ) -> dict[str, Any] | None:
        """Find an expense account using multiple strategies.

        Tries in order:
        1. name matching hint (if provided)
        2. account_type == "expense" (most correct)
        3. account_number starting with "5" or "6" (US GAAP expense accounts)
        4. name containing "expense" (fallback)
        """
        if hint:
            normalized = hint.strip().lower()
            preferred_names = [normalized]
            terms = [normalized]

            if "payroll" in normalized:
                if "tax" in normalized:
                    preferred_names = [
                        "payroll tax expense",
                        "payroll taxes",
                        "payroll tax",
                        "employment taxes",
                        "employer payroll taxes",
                    ]
                    terms = [
                        "payroll tax",
                        "payroll taxes",
                        "employment tax",
                        "withholding",
                    ]
                else:
                    preferred_names = [
                        "wages and salaries",
                        "salaries and wages",
                        "wages & salaries",
                        "salaries & wages",
                        "payroll expense",
                        "wages expense",
                        "salary expense",
                        "compensation expense",
                    ]
                    terms = [
                        "payroll",
                        "wages",
                        "salaries",
                        "compensation",
                    ]
            elif "tax" in normalized:
                preferred_names = [
                    "income tax expense",
                    "income taxes",
                    "tax expense",
                    "estimated taxes",
                    "taxes and licenses",
                    "taxes & licenses",
                ]
                terms = [
                    "income tax",
                    "estimated tax",
                    "taxes",
                ]

            normalized_preferred = {name.strip().lower() for name in preferred_names}
            for account in accounts:
                name = str(account.get("name", "")).strip().lower()
                if name not in normalized_preferred:
                    continue
                account_type = account.get("account_type")
                if account_type and account_type != "expense":
                    continue
                return account

            for term in terms:
                for account in accounts:
                    name = str(account.get("name", "")).lower()
                    if term not in name:
                        continue
                    account_type = account.get("account_type")
                    if account_type and account_type != "expense":
                        continue
                    return account

        # Strategy 1: By account_type (most reliable if available)
        for account in accounts:
            if account.get("account_type") == "expense":
                return account

        # Strategy 2: By account_number (US GAAP: 5xxx/6xxx = Expenses)
        for account in accounts:
            if str(account.get("account_number", "")).startswith(("5", "6")):
                return account

        # Strategy 3: By name containing "expense" (last resort)
        for account in accounts:
            if "expense" in str(account.get("name", "")).lower():
                return account
        return None

    def _get_simulation_date(self) -> date:
        """Get the current simulation date based on day number."""
        base_date = date.today() - timedelta(days=30)  # Start 30 days ago
        return base_date + timedelta(days=self._scheduler.current_time.day - 1)

    def _maybe_publish_vendor_price_increases(self, sim_date: date) -> None:
        """Publish annual vendor price increase notifications."""
        if self._inflation.annual_rate <= 0:
            return
        if not self._inflation.is_anniversary(sim_date):
            return

        rate_pct = (self._inflation.annual_rate * Decimal("100")).quantize(
            Decimal("0.1")
        )
        multiplier = float(self._inflation.annual_increase_multiplier())

        for org_id, ctx in self._organizations.items():
            profiles = VENDOR_ARCHETYPES.get(ctx.industry, [])
            if not profiles:
                continue

            vendor_agents_by_name = {
                vendor.profile.name.strip().lower(): vendor for vendor in ctx.vendors
            }

            for profile in profiles:
                key = (org_id, profile.name, sim_date.year)
                if key in self._vendor_price_increase_sent:
                    continue

                agent = vendor_agents_by_name.get(profile.name.strip().lower())
                if agent is not None:
                    agent_id = agent.id
                    agent_name = agent.name
                    agent.profile.typical_amount = round(
                        agent.profile.typical_amount * multiplier, 2
                    )
                else:
                    agent_id = UUID(int=0)
                    agent_name = profile.name

                self._event_publisher.publish(
                    agent_speaking(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=(
                            f"{agent_name} notified {ctx.name} of a "
                            f"{rate_pct}% price increase effective {sim_date.isoformat()}."
                        ),
                        org_id=org_id,
                    )
                )
                self._vendor_price_increase_sent.add(key)

    def _run_note(self) -> str | None:
        if not self._run_id:
            return None
        return f"sim_run_id={self._run_id}"

    def _run_suffix(self) -> str:
        if not self._run_id_short:
            return ""
        return f"-R{self._run_id_short}"

    @staticmethod
    def _merge_notes(primary: str | None, extra: str | None) -> str | None:
        parts = [value.strip() for value in (primary, extra) if value and value.strip()]
        if not parts:
            return None
        return "\n".join(parts)

    @staticmethod
    def _extract_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_event_metadata(
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not metadata:
            return None
        keys = ("b2b_pair_id", "counterparty_org_id", "counterparty_doc_id")
        event_meta = {
            key: metadata.get(key)
            for key in keys
            if metadata.get(key) is not None
        }
        return event_meta or None

    @staticmethod
    def _quarterly_tax_key(
        org_id: UUID,
        tax_year: int,
        quarter: int,
    ) -> tuple[UUID, int, int]:
        return (org_id, tax_year, quarter)

    def _get_quarterly_tax_record(
        self,
        org_id: UUID,
        tax_year: int,
        quarter: int,
    ) -> dict[str, str]:
        return self._quarterly_tax_records.get(
            self._quarterly_tax_key(org_id, tax_year, quarter),
            {},
        )

    def _set_quarterly_tax_record(
        self,
        org_id: UUID,
        tax_year: int,
        quarter: int,
        estimate_id: str | None = None,
        bill_id: str | None = None,
    ) -> None:
        key = self._quarterly_tax_key(org_id, tax_year, quarter)
        record = self._quarterly_tax_records.get(key, {})
        if estimate_id:
            record["estimate_id"] = estimate_id
        if bill_id:
            record["bill_id"] = bill_id
        if record:
            self._quarterly_tax_records[key] = record

    @staticmethod
    def _find_vendor_id_by_name(
        vendor_name: str | None,
        vendors: list[dict[str, Any]],
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
        return None

    async def _ensure_tax_year_id(self, tax_year: int) -> UUID | None:
        if not self._api_client:
            return None

        company_id = self._api_client.current_company_id
        if not company_id:
            self._logger.warning(
                "tax_year_missing_company",
                tax_year=tax_year,
            )
            return None

        try:
            tax_years = await self._api_client.list_tax_years(company_id=company_id)
        except AtlasAPIError as exc:
            self._logger.warning(
                "tax_year_list_failed",
                tax_year=tax_year,
                error=str(exc),
            )
            return None

        for item in tax_years:
            try:
                if int(item.get("year", 0)) == tax_year:
                    return UUID(item["id"])
            except (KeyError, ValueError, TypeError):
                continue

        try:
            created = await self._api_client.create_tax_year(
                company_id=company_id,
                year=tax_year,
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "tax_year_create_failed",
                tax_year=tax_year,
                error=str(exc),
            )
            return None

        created_id = created.get("id") if isinstance(created, dict) else None
        if created_id:
            return UUID(created_id)
        return None

    async def _ensure_quarterly_estimate(
        self,
        tax_year_id: UUID,
        tax_year: int,
        quarter: int,
        estimated_income: Decimal,
    ) -> dict[str, Any] | None:
        if not self._api_client:
            return None

        try:
            estimates = await self._api_client.list_quarterly_estimates(
                tax_year_id=tax_year_id
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "quarterly_estimate_list_failed",
                tax_year=tax_year,
                quarter=quarter,
                error=str(exc),
            )
            return None

        for estimate in estimates:
            try:
                if int(estimate.get("quarter", 0)) == quarter:
                    return estimate
            except (ValueError, TypeError):
                continue

        try:
            created = await self._api_client.create_quarterly_estimate(
                tax_year_id=tax_year_id,
                quarter=quarter,
                estimated_income=str(estimated_income),
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "quarterly_estimate_create_failed",
                tax_year=tax_year,
                quarter=quarter,
                error=str(exc),
            )
            return None

        return created if isinstance(created, dict) else None

    async def _create_invoice(
        self,
        ctx: OrganizationContext,
        tx: GeneratedTransaction,
        sim_date: date,
    ) -> dict[str, Any] | None:
        """Create an invoice from a generated transaction."""
        if not self._api_client or not tx.customer_id:
            return None

        try:
            # Get revenue account - required for invoice creation
            accounts = await self._api_client.list_accounts()
            revenue_account = self._find_revenue_account(accounts)

            if not revenue_account:
                self._logger.warning(
                    "no_revenue_account_found",
                    org=ctx.name,
                    account_count=len(accounts),
                    msg="Cannot create invoice - no revenue account in chart of accounts",
                )
                return None

            due_date: date | None = None
            notes: str | None = None
            if tx.metadata:
                due_value = tx.metadata.get("due_date")
                if isinstance(due_value, str):
                    with suppress(ValueError):
                        due_date = date.fromisoformat(due_value)
                notes_value = tx.metadata.get("notes")
                if isinstance(notes_value, str) and notes_value.strip():
                    notes = notes_value.strip()

            invoice_data: dict[str, Any] = {
                "customer_id": str(tx.customer_id),
                "invoice_date": sim_date.isoformat(),
                "lines": [{
                    "description": tx.description,
                    "quantity": "1",
                    "unit_price": str(tx.amount),
                    "revenue_account_id": revenue_account["id"],
                }],
            }
            if due_date:
                invoice_data["due_date"] = due_date.isoformat()
            run_note = self._run_note()
            merged_notes = self._merge_notes(run_note, notes)
            if merged_notes:
                invoice_data["notes"] = merged_notes
            if tx.metadata:
                discount_percent = tx.metadata.get("discount_percent")
                discount_days = tx.metadata.get("discount_days")
                if discount_percent is not None and discount_days is not None:
                    invoice_data["discount_percent"] = str(discount_percent)
                    invoice_data["discount_days"] = int(discount_days)

            result = await self._api_client.create_invoice(invoice_data)

            # Publish event
            counterparty = (
                tx.description.split(" - ")[0]
                if " - " in tx.description
                else "Customer"
            )
            event_metadata = self._extract_event_metadata(tx.metadata if tx.metadata else None)
            self._event_publisher.publish(
                transaction_created(
                    org_id=ctx.id,
                    org_name=ctx.name,
                    transaction_type="invoice",
                    amount=float(tx.amount),
                    counterparty=counterparty,
                    description=tx.description,
                    metadata=event_metadata,
                )
            )

            self._logger.info("invoice_created", org=ctx.name, amount=str(tx.amount))
            return result

        except Exception as e:
            self._logger.error("invoice_creation_failed", error=str(e))
            return None

    async def _create_bill(
        self,
        ctx: OrganizationContext,
        tx: GeneratedTransaction,
        sim_date: date,
    ) -> dict[str, Any] | None:
        """Create a bill from a generated transaction."""
        if not self._api_client or not tx.vendor_id:
            return None

        try:
            # Get expense account - required for bill creation
            accounts = await self._api_client.list_accounts()
            hint = None
            if tx.metadata:
                hint_value = tx.metadata.get("expense_account_hint")
                if hint_value:
                    hint = str(hint_value)
            expense_account = self._find_expense_account(accounts, hint=hint)

            if not expense_account:
                self._logger.warning(
                    "no_expense_account_found",
                    org=ctx.name,
                    account_count=len(accounts),
                    msg="Cannot create bill - no expense account in chart of accounts",
                )
                return None

            due_date = sim_date + timedelta(days=30)
            notes: str | None = None
            vendor_bill_number: str | None = None
            if tx.metadata:
                due_value = tx.metadata.get("due_date")
                if isinstance(due_value, str):
                    with suppress(ValueError):
                        due_date = date.fromisoformat(due_value)
                notes_value = tx.metadata.get("notes")
                if isinstance(notes_value, str) and notes_value.strip():
                    notes = notes_value.strip()
                vendor_bill_value = tx.metadata.get("vendor_bill_number")
                if isinstance(vendor_bill_value, str) and vendor_bill_value.strip():
                    vendor_bill_number = vendor_bill_value.strip()

            bill_data = {
                "vendor_id": str(tx.vendor_id),
                "bill_date": sim_date.isoformat(),
                "due_date": due_date.isoformat(),
                "bill_number": (
                    f"BILL-{sim_date.strftime('%Y%m%d')}-"
                    f"{random.randint(100, 999)}{self._run_suffix()}"
                )[:30],
                "lines": [{
                    "description": tx.description,
                    "quantity": "1",
                    "unit_price": str(tx.amount),
                    "expense_account_id": expense_account["id"],
                }],
            }
            if notes:
                bill_data["notes"] = notes
            if vendor_bill_number:
                bill_data["vendor_bill_number"] = vendor_bill_number[:50]
            elif self._run_id:
                bill_data["vendor_bill_number"] = f"SIMRUN-{self._run_id}"[:50]

            result = await self._api_client.create_bill(bill_data)

            # Publish event
            counterparty = (
                tx.description.split(" - ")[0]
                if " - " in tx.description
                else "Vendor"
            )
            event_metadata = self._extract_event_metadata(tx.metadata if tx.metadata else None)
            self._event_publisher.publish(
                transaction_created(
                    org_id=ctx.id,
                    org_name=ctx.name,
                    transaction_type="bill",
                    amount=float(tx.amount),
                    counterparty=counterparty,
                    description=tx.description,
                    metadata=event_metadata,
                )
            )

            self._logger.info("bill_created", org=ctx.name, amount=str(tx.amount))
            return result

        except Exception as e:
            self._logger.error("bill_creation_failed", error=str(e))
            return None

    async def _get_accounts_for_org(self, org_id: UUID) -> dict[str, Any]:
        """Get cached account info for an organization."""
        if org_id not in self._account_cache and self._api_client:
            accounts = await self._api_client.list_accounts(limit=200)

            # Find AR account
            ar_accounts = [
                a for a in accounts if a.get("account_type") == "accounts_receivable"
            ]
            if not ar_accounts:
                ar_accounts = [
                    a for a in accounts
                    if a.get("account_type") == "asset"
                    and "receivable" in a.get("name", "").lower()
                ]
            ar_account = ar_accounts[0] if ar_accounts else None

            # Find deposit/bank account
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

            self._account_cache[org_id] = {
                "ar_account_id": ar_account["id"] if ar_account else None,
                "deposit_account_id": deposit_account["id"] if deposit_account else None,
            }

        return self._account_cache.get(org_id, {})

    async def _record_payment(
        self,
        ctx: OrganizationContext,
        tx: GeneratedTransaction,
    ) -> dict[str, Any] | None:
        """Record a payment received for an invoice."""
        if not self._api_client or not tx.metadata or not tx.customer_id:
            return None

        invoice_id = tx.metadata.get("invoice_id")
        if not invoice_id:
            return None

        # Get cached accounts
        account_info = await self._get_accounts_for_org(ctx.id)
        ar_account_id = account_info.get("ar_account_id")
        deposit_account_id = account_info.get("deposit_account_id")

        if not ar_account_id or not deposit_account_id:
            self._logger.warning(
                "payment_skipped_missing_accounts",
                org=ctx.name,
                ar_account=ar_account_id,
                deposit_account=deposit_account_id,
            )
            return None

        # Create payment with all required fields
        payment_data = {
            "customer_id": str(tx.customer_id),
            "amount": str(tx.amount),
            "payment_date": self._get_simulation_date().isoformat(),
            "payment_method": "check",
            "deposit_account_id": deposit_account_id,
            "reference_number": (
                f"PMT-{random.randint(10000, 99999)}{self._run_suffix()}"
            )[:100],
        }

        try:
            result = await self._api_client.create_payment(
                payment_data, ar_account_id=UUID(ar_account_id)
            )
        except Exception as e:
            details = e.details if isinstance(e, AtlasAPIError) else None
            self._logger.error(
                "payment_failed",
                error=str(e),
                details=details,
                org=ctx.name,
            )
            return None

        if result and result.get("id"):
            try:
                # Apply to invoice
                take_discount = False
                if tx.metadata:
                    take_discount = bool(tx.metadata.get("take_discount"))
                await self._api_client.apply_payment_to_invoice(
                    UUID(result["id"]),
                    UUID(invoice_id),
                    str(tx.amount),
                    take_discount=take_discount,
                )
            except Exception as e:
                details = e.details if isinstance(e, AtlasAPIError) else None
                self._logger.warning(
                    "payment_apply_failed",
                    error=str(e),
                    details=details,
                    org=ctx.name,
                    invoice_id=str(invoice_id),
                    payment_id=str(result.get("id")),
                    amount=str(tx.amount),
                )

        # Publish event
        counterparty = (
            tx.description.split(" - ")[0]
            if " - " in tx.description
            else "Customer"
        )
        event_metadata = self._extract_event_metadata(tx.metadata if tx.metadata else None)
        self._event_publisher.publish(
            transaction_created(
                org_id=ctx.id,
                org_name=ctx.name,
                transaction_type="payment_received",
                amount=float(tx.amount),
                counterparty=counterparty,
                description=tx.description,
                metadata=event_metadata,
            )
        )

        self._logger.info("payment_received", org=ctx.name, amount=str(tx.amount))
        return result

    async def _get_cash_position(
        self, org_id: UUID
    ) -> tuple[Decimal, list[dict[str, Any]]]:
        if not self._api_client:
            return Decimal("0"), []
        accounts = await self._api_client.list_accounts(limit=200)
        bank_accounts = [a for a in accounts if a.get("account_type") == "bank"]
        if not bank_accounts:
            bank_accounts = [
                a
                for a in accounts
                if a.get("account_type") == "asset"
                and (
                    "cash" in str(a.get("name", "")).lower()
                    or "checking" in str(a.get("name", "")).lower()
                )
            ]
        total = Decimal("0")
        for account in bank_accounts:
            try:
                balance_info = await self._api_client.get_account_balance(
                    UUID(str(account["id"]))
                )
            except Exception:
                continue
            balance = self._extract_decimal(balance_info.get("balance"))
            if balance is not None:
                total += balance
        return total, bank_accounts

    async def _maybe_draw_loc(
        self,
        ctx: OrganizationContext,
        current_date: date,
        cash_position: Decimal,
        reserve_target: Decimal,
        policy: dict[str, Any],
    ) -> Decimal:
        auto_draw_threshold = policy.get("auto_draw_threshold")
        if auto_draw_threshold is None:
            auto_draw_threshold = Decimal("0")
        if cash_position >= auto_draw_threshold:
            return cash_position
        if not self._api_client:
            return cash_position

        loc_specs = self._tx_generator.get_line_of_credit_specs(ctx.owner_key)
        if not loc_specs:
            return cash_position
        primary_loc = loc_specs[0]
        if primary_loc.limit is None or primary_loc.limit <= Decimal("0"):
            return cash_position

        current_balance = self._tx_generator.get_line_of_credit_balance(
            ctx.owner_key, primary_loc.name
        )
        available = primary_loc.limit - current_balance
        if available <= Decimal("0"):
            return cash_position

        target = reserve_target if reserve_target > 0 else auto_draw_threshold
        if target <= cash_position:
            return cash_position

        draw_amount = (target - cash_position).quantize(Decimal("0.01"))
        if draw_amount <= 0:
            return cash_position
        if draw_amount > available:
            draw_amount = available.quantize(Decimal("0.01"))

        accounts = await self._api_client.list_accounts(limit=200)
        bank_account = next(
            (a for a in accounts if a.get("account_type") == "bank"),
            None,
        )
        if bank_account is None:
            bank_account = next(
                (
                    a
                    for a in accounts
                    if a.get("account_type") == "asset"
                    and (
                        "cash" in str(a.get("name", "")).lower()
                        or "checking" in str(a.get("name", "")).lower()
                    )
                ),
                None,
            )
        loc_account = next(
            (
                a
                for a in accounts
                if a.get("account_type") in {"liability", "accounts_payable"}
                and (
                    "line of credit" in str(a.get("name", "")).lower()
                    or "credit line" in str(a.get("name", "")).lower()
                    or primary_loc.name.lower() in str(a.get("name", "")).lower()
                    or "loc" in str(a.get("name", "")).lower()
                )
            ),
            None,
        )

        if not bank_account or not loc_account:
            self._logger.warning(
                "loc_draw_skipped_missing_accounts",
                org=ctx.name,
            )
            return cash_position

        await self._api_client.create_journal_entry(
            {
                "entry_date": current_date.isoformat(),
                "description": f"LOC draw - {primary_loc.name}{self._run_suffix()}",
                "lines": [
                    {
                        "account_id": str(bank_account["id"]),
                        "entry_type": "debit",
                        "amount": str(draw_amount),
                        "description": "LOC draw deposit",
                    },
                    {
                        "account_id": str(loc_account["id"]),
                        "entry_type": "credit",
                        "amount": str(draw_amount),
                        "description": "LOC liability",
                    },
                ],
            }
        )
        self._tx_generator.set_line_of_credit_balance(
            ctx.owner_key, primary_loc.name, current_balance + draw_amount
        )
        self._logger.info(
            "loc_draw_recorded",
            org=ctx.name,
            amount=str(draw_amount),
            loc_name=primary_loc.name,
        )
        self._event_publisher.publish(
            agent_speaking(
                agent_id=ctx.owner.id if ctx.owner else UUID(int=0),
                agent_name=ctx.owner.name if ctx.owner else "Owner",
                message=(
                    f"{ctx.name}: Drew ${draw_amount:,.2f} from {primary_loc.name} "
                    f"to maintain cash reserves."
                ),
                org_id=ctx.id,
            )
        )
        return cash_position + draw_amount

    async def _maybe_build_reserve(
        self,
        ctx: OrganizationContext,
        current_date: date,
        cash_position: Decimal,
        reserve_target: Decimal,
    ) -> Decimal:
        if reserve_target <= 0 or cash_position <= reserve_target:
            return cash_position
        if not self._api_client:
            return cash_position

        accounts = await self._api_client.list_accounts(limit=200)
        bank_account = next(
            (a for a in accounts if a.get("account_type") == "bank"),
            None,
        )
        if bank_account is None:
            bank_account = next(
                (
                    a
                    for a in accounts
                    if a.get("account_type") == "asset"
                    and (
                        "cash" in str(a.get("name", "")).lower()
                        or "checking" in str(a.get("name", "")).lower()
                    )
                ),
                None,
            )
        reserve_account = next(
            (
                a
                for a in accounts
                if a.get("account_type") in {"asset", "bank"}
                and "reserve" in str(a.get("name", "")).lower()
            ),
            None,
        )

        if not bank_account or not reserve_account:
            return cash_position

        transfer_amount = (cash_position - reserve_target).quantize(Decimal("0.01"))
        if transfer_amount <= 0:
            return cash_position

        await self._api_client.create_journal_entry(
            {
                "entry_date": current_date.isoformat(),
                "description": f"Transfer to cash reserve{self._run_suffix()}",
                "lines": [
                    {
                        "account_id": str(reserve_account["id"]),
                        "entry_type": "debit",
                        "amount": str(transfer_amount),
                        "description": "Increase cash reserve",
                    },
                    {
                        "account_id": str(bank_account["id"]),
                        "entry_type": "credit",
                        "amount": str(transfer_amount),
                        "description": "Transfer from operating cash",
                    },
                ],
            }
        )
        self._logger.info(
            "cash_reserve_transfer",
            org=ctx.name,
            amount=str(transfer_amount),
        )
        self._event_publisher.publish(
            agent_speaking(
                agent_id=ctx.owner.id if ctx.owner else UUID(int=0),
                agent_name=ctx.owner.name if ctx.owner else "Owner",
                message=(
                    f"{ctx.name}: Set aside ${transfer_amount:,.2f} into cash reserves "
                    f"to stay near the target ${reserve_target:,.2f}."
                ),
                org_id=ctx.id,
            )
        )
        return cash_position - transfer_amount

    async def _should_pay_bill(
        self,
        ctx: OrganizationContext,
        bill_id: str,
        cash_position: Decimal,
        reserve_target: Decimal,
        policy: dict[str, Any],
    ) -> bool:
        defer_nonessential = policy.get("defer_nonessential", True)
        if not defer_nonessential:
            return True

        min_cash = policy.get("min_cash") or Decimal("0")
        effective_min = max(min_cash, reserve_target)
        if not self._api_client:
            return cash_position >= effective_min

        try:
            bill = await self._api_client.get_bill(UUID(str(bill_id)))
        except Exception:
            return cash_position >= effective_min

        vendor_name = ""
        vendor_id = bill.get("vendor_id")
        if vendor_id:
            try:
                vendor = await self._api_client.get_vendor(UUID(str(vendor_id)))
                vendor_name = str(
                    vendor.get("display_name") or vendor.get("name") or ""
                )
            except Exception:
                vendor_name = ""

        if self._is_essential_bill(bill, vendor_name, policy):
            return True

        amount_due = self._extract_decimal(bill.get("amount_due")) or Decimal("0")
        projected = cash_position - amount_due
        if projected >= effective_min:
            return True
        self._event_publisher.publish(
            agent_speaking(
                agent_id=ctx.owner.id if ctx.owner else UUID(int=0),
                agent_name=ctx.owner.name if ctx.owner else "Owner",
                message=(
                    f"{ctx.name}: Deferring non-essential bill payment to "
                    f"{vendor_name or 'vendor'} to keep cash above "
                    f"${effective_min:,.2f}."
                ),
                org_id=ctx.id,
            )
        )
        return False

    @staticmethod
    def _is_essential_bill(
        bill: dict[str, Any],
        vendor_name: str,
        policy: dict[str, Any],
    ) -> bool:
        default_keywords = {
            "payroll",
            "rent",
            "lease",
            "tax",
            "irs",
            "insurance",
            "utility",
            "utilities",
            "loan",
            "interest",
        }
        keywords = set(policy.get("essential_vendor_keywords") or []) or default_keywords
        haystack = " ".join(
            [
                vendor_name,
                str(bill.get("bill_number") or ""),
                str(bill.get("notes") or ""),
            ]
        ).lower()
        for line in bill.get("lines", []) or []:
            haystack += " " + str(line.get("description") or "").lower()
        return any(keyword in haystack for keyword in keywords)

    async def _pay_bill(
        self,
        ctx: OrganizationContext,
        tx: GeneratedTransaction,
    ) -> dict[str, Any] | None:
        """Record a payment made for a bill."""
        if not self._api_client or not tx.metadata:
            return None

        bill_id = tx.metadata.get("bill_id")
        if not bill_id:
            return None

        payment_data = {
            "bill_id": bill_id,
            "amount": str(tx.amount),
            "payment_date": self._get_simulation_date().isoformat(),
            "payment_method": "check",
        }

        try:
            result = await self._api_client.create_bill_payment(payment_data)
        except Exception as e:
            details = e.details if isinstance(e, AtlasAPIError) else None
            self._logger.error(
                "bill_payment_failed",
                error=str(e),
                details=details,
                org=ctx.name,
            )
            return None

        counterparty = (
            tx.description.split(" - ")[0]
            if " - " in tx.description
            else "Vendor"
        )
        event_metadata = self._extract_event_metadata(tx.metadata)
        self._event_publisher.publish(
            transaction_created(
                org_id=ctx.id,
                org_name=ctx.name,
                transaction_type="payment_sent",
                amount=float(tx.amount),
                counterparty=counterparty,
                description=tx.description,
                metadata=event_metadata,
            )
        )

        self._logger.info("bill_payment_sent", org=ctx.name, amount=str(tx.amount))
        return result

    async def _b2b_pair_already_recorded(self, pair_id: str) -> bool:
        if not self._api_client:
            return False

        try:
            invoices = await self._api_client.list_invoices(limit=200)
        except AtlasAPIError as exc:
            self._logger.warning("b2b_invoice_list_failed", error=str(exc))
            invoices = []

        for invoice in invoices:
            notes = str(invoice.get("notes", ""))
            if pair_id in notes:
                return True

        try:
            bills = await self._api_client.list_bills(limit=200)
        except AtlasAPIError as exc:
            self._logger.warning("b2b_bill_list_failed", error=str(exc))
            bills = []

        for bill in bills:
            notes = str(bill.get("notes", ""))
            vendor_ref = str(bill.get("vendor_bill_number", ""))
            if pair_id in notes or pair_id in vendor_ref:
                return True

        return False

    async def _execute_b2b_pair(
        self,
        pair: B2BPlannedPair,
        sim_date: date,
        customers_by_key: dict[str, list[dict[str, Any]]],
        vendors_by_key: dict[str, list[dict[str, Any]]],
    ) -> bool:
        if not self._api_client:
            return False

        seller_ctx = self._organizations.get(pair.seller_org_id)
        buyer_ctx = self._organizations.get(pair.buyer_org_id)
        if not seller_ctx or not buyer_ctx:
            return False

        if pair.pair_id in self._b2b_pairs_created:
            return False

        await self.switch_organization(seller_ctx.id)
        if await self._b2b_pair_already_recorded(pair.pair_id):
            self._b2b_pairs_created.add(pair.pair_id)
            if self._b2b_coordinator:
                self._b2b_coordinator.mark_pair_seen(pair.pair_id)
            return False

        seller_customers = customers_by_key.get(pair.seller_key, [])
        customer_id = self._find_customer_id_by_name(buyer_ctx.name, seller_customers)
        if not customer_id:
            await self._ensure_customer_present(seller_customers, buyer_ctx.name)
            customer_id = self._find_customer_id_by_name(buyer_ctx.name, seller_customers)
        if not customer_id:
            self._logger.warning(
                "b2b_missing_customer",
                seller=seller_ctx.name,
                buyer=buyer_ctx.name,
            )
            return False

        seller_note = build_b2b_note(pair.pair_id, buyer_ctx.id)
        invoice_tx = GeneratedTransaction(
            transaction_type=TransactionType.INVOICE,
            description=pair.description,
            amount=pair.amount,
            customer_id=customer_id,
            metadata={
                "b2b_pair_id": pair.pair_id,
                "counterparty_org_id": str(buyer_ctx.id),
                "notes": seller_note,
                "due_date": pair.due_date.isoformat(),
            },
        )
        invoice = await self._create_invoice(seller_ctx, invoice_tx, sim_date)
        if not invoice or not invoice.get("id"):
            return False
        invoice_id = str(invoice["id"])

        await self.switch_organization(buyer_ctx.id)
        if await self._b2b_pair_already_recorded(pair.pair_id):
            self._b2b_pairs_created.add(pair.pair_id)
            if self._b2b_coordinator:
                self._b2b_coordinator.mark_pair_seen(pair.pair_id)
            return False

        buyer_vendors = vendors_by_key.get(pair.buyer_key, [])
        vendor_id = self._find_vendor_id_by_name(seller_ctx.name, buyer_vendors)
        if not vendor_id:
            await self._ensure_vendor_present(buyer_vendors, seller_ctx.name)
            vendor_id = self._find_vendor_id_by_name(seller_ctx.name, buyer_vendors)
        if not vendor_id:
            self._logger.warning(
                "b2b_missing_vendor",
                seller=seller_ctx.name,
                buyer=buyer_ctx.name,
            )
            return False

        buyer_note = build_b2b_note(pair.pair_id, seller_ctx.id, invoice_id)
        vendor_bill_number = f"B2B-{pair.pair_id.split('-')[0]}-{sim_date.strftime('%Y%m%d')}"
        bill_tx = GeneratedTransaction(
            transaction_type=TransactionType.BILL,
            description=pair.description,
            amount=pair.amount,
            vendor_id=vendor_id,
            metadata={
                "b2b_pair_id": pair.pair_id,
                "counterparty_org_id": str(seller_ctx.id),
                "counterparty_doc_id": invoice_id,
                "notes": buyer_note,
                "due_date": pair.due_date.isoformat(),
                "vendor_bill_number": vendor_bill_number,
            },
        )
        bill = await self._create_bill(buyer_ctx, bill_tx, sim_date)
        if not bill or not bill.get("id"):
            return False
        bill_id = str(bill["id"])

        if pair.payment_flow != "none":
            try:
                await self._api_client.create_bill_payment(
                    {
                        "bill_id": bill_id,
                        "amount": str(pair.amount),
                        "payment_date": sim_date.isoformat(),
                        "payment_method": "check",
                    }
                )
            except AtlasAPIError as exc:
                self._logger.warning(
                    "b2b_bill_payment_failed",
                    seller=seller_ctx.name,
                    buyer=buyer_ctx.name,
                    error=str(exc),
                )
            else:
                self._event_publisher.publish(
                    transaction_created(
                        org_id=buyer_ctx.id,
                        org_name=buyer_ctx.name,
                        transaction_type="payment_sent",
                        amount=float(pair.amount),
                        counterparty=seller_ctx.name,
                        description=f"B2B payment - {pair.description}",
                        metadata={
                            "b2b_pair_id": pair.pair_id,
                            "counterparty_org_id": str(seller_ctx.id),
                            "counterparty_doc_id": invoice_id,
                        },
                    )
                )
                await self.switch_organization(seller_ctx.id)
                payment_tx = GeneratedTransaction(
                    transaction_type=TransactionType.PAYMENT_RECEIVED,
                    description=f"B2B payment - {pair.description}",
                    amount=pair.amount,
                    customer_id=customer_id,
                    metadata={
                        "invoice_id": invoice_id,
                        "b2b_pair_id": pair.pair_id,
                        "counterparty_org_id": str(buyer_ctx.id),
                        "counterparty_doc_id": bill_id,
                    },
                )
                await self._record_payment(seller_ctx, payment_tx)

        self._b2b_pairs_created.add(pair.pair_id)
        if self._b2b_coordinator:
            self._b2b_coordinator.mark_pair_seen(pair.pair_id)
        return True

    async def _process_b2b_transactions(self, sim_date: date) -> list[dict[str, Any]]:
        if not self._api_client or not self._b2b_coordinator:
            return []

        orgs_by_key = {ctx.owner_key: ctx for ctx in self._organizations.values()}
        if not orgs_by_key:
            return []

        customers_by_key: dict[str, list[dict[str, Any]]] = {}
        vendors_by_key: dict[str, list[dict[str, Any]]] = {}

        for owner_key, ctx in orgs_by_key.items():
            await self.switch_organization(ctx.id)
            customers_by_key[owner_key] = await self._api_client.list_customers()
            vendors_by_key[owner_key] = await self._api_client.list_vendors()

        planned_pairs = self._b2b_coordinator.plan_pairs(sim_date, customers_by_key)
        results: list[dict[str, Any]] = []

        for pair in planned_pairs:
            created = await self._execute_b2b_pair(
                pair, sim_date, customers_by_key, vendors_by_key
            )
            if created:
                results.append(
                    {
                        "pair_id": pair.pair_id,
                        "seller": pair.seller_name,
                        "buyer": pair.buyer_name,
                        "amount": str(pair.amount),
                    }
                )

        return results

    async def _find_quarterly_tax_bill(
        self,
        vendor_id: UUID,
        action: QuarterlyTaxAction,
    ) -> dict[str, Any] | None:
        if not self._api_client:
            return None

        description = (
            f"Quarterly estimated tax payment Q{action.quarter} {action.tax_year}"
        )
        try:
            bills = await self._api_client.list_bills(status="pending")
        except AtlasAPIError as exc:
            self._logger.warning(
                "quarterly_tax_bill_list_failed",
                error=str(exc),
            )
            return None

        for bill in bills:
            if bill.get("vendor_id") != str(vendor_id):
                continue
            if bill.get("due_date") != action.due_date.isoformat():
                continue
            for line in bill.get("lines", []):
                line_desc = str(line.get("description", ""))
                if description in line_desc:
                    return bill
        return None

    async def _create_quarterly_tax_bill(
        self,
        ctx: OrganizationContext,
        sim_date: date,
        vendors: list[dict[str, Any]],
        action: QuarterlyTaxAction,
    ) -> bool:
        if not self._api_client:
            return False

        tax_year_id = await self._ensure_tax_year_id(action.tax_year)
        if not tax_year_id:
            return False

        estimate = await self._ensure_quarterly_estimate(
            tax_year_id=tax_year_id,
            tax_year=action.tax_year,
            quarter=action.quarter,
            estimated_income=action.estimated_income,
        )
        if not estimate:
            return False

        estimate_id = estimate.get("id")
        if isinstance(estimate_id, str):
            self._set_quarterly_tax_record(
                ctx.id, action.tax_year, action.quarter, estimate_id=estimate_id
            )

        vendor_id = self._find_vendor_id_by_name(action.tax_vendor, vendors)
        if not vendor_id:
            self._logger.warning(
                "quarterly_tax_vendor_missing",
                org=ctx.name,
                vendor=action.tax_vendor,
            )
            return False

        record = self._get_quarterly_tax_record(ctx.id, action.tax_year, action.quarter)
        if record.get("bill_id"):
            self._tx_generator.mark_quarterly_tax_created(
                ctx.owner_key, action.tax_year, action.quarter
            )
            return False

        existing = await self._find_quarterly_tax_bill(vendor_id, action)
        if existing and existing.get("id"):
            self._set_quarterly_tax_record(
                ctx.id,
                action.tax_year,
                action.quarter,
                bill_id=str(existing["id"]),
            )
            self._tx_generator.mark_quarterly_tax_created(
                ctx.owner_key, action.tax_year, action.quarter
            )
            return False

        amount_raw = (
            estimate.get("amount_due")
            or estimate.get("remaining_due")
            or estimate.get("total_estimated_tax")
            or str(action.estimated_tax)
        )
        try:
            amount = Decimal(str(amount_raw)).quantize(Decimal("0.01"))
        except (ValueError, TypeError):
            amount = action.estimated_tax

        description = (
            f"Quarterly estimated tax payment Q{action.quarter} {action.tax_year}"
        )
        notes = None
        if isinstance(estimate_id, str):
            notes = f"quarterly_estimate_id={estimate_id}"

        tx = GeneratedTransaction(
            transaction_type=TransactionType.BILL,
            description=description,
            amount=amount,
            vendor_id=vendor_id,
            metadata={
                "expense_account_hint": "income tax",
                "due_date": action.due_date.isoformat(),
                "notes": notes,
            },
        )
        created = await self._create_bill(ctx, tx, sim_date)
        if created and created.get("id"):
            self._set_quarterly_tax_record(
                ctx.id,
                action.tax_year,
                action.quarter,
                bill_id=str(created["id"]),
            )
            self._tx_generator.mark_quarterly_tax_created(
                ctx.owner_key, action.tax_year, action.quarter
            )
            return True
        return False

    async def _pay_quarterly_tax_bill(
        self,
        ctx: OrganizationContext,
        sim_date: date,
        vendors: list[dict[str, Any]],
        action: QuarterlyTaxAction,
    ) -> bool:
        if not self._api_client:
            return False

        tax_year_id = await self._ensure_tax_year_id(action.tax_year)
        if not tax_year_id:
            return False

        estimate: dict[str, Any] | None = None
        record = self._get_quarterly_tax_record(ctx.id, action.tax_year, action.quarter)
        estimate_id = record.get("estimate_id")

        try:
            estimates = await self._api_client.list_quarterly_estimates(
                tax_year_id=tax_year_id
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "quarterly_estimate_list_failed",
                tax_year=action.tax_year,
                quarter=action.quarter,
                error=str(exc),
            )
            return False

        for item in estimates:
            try:
                if int(item.get("quarter", 0)) == action.quarter:
                    estimate = item
                    break
            except (ValueError, TypeError):
                continue

        if estimate and isinstance(estimate.get("id"), str):
            estimate_id = estimate["id"]
            self._set_quarterly_tax_record(
                ctx.id, action.tax_year, action.quarter, estimate_id=estimate_id
            )

        if not estimate_id:
            self._logger.warning(
                "quarterly_estimate_missing",
                org=ctx.name,
                tax_year=action.tax_year,
                quarter=action.quarter,
            )
            return False

        vendor_id = self._find_vendor_id_by_name(action.tax_vendor, vendors)
        if not vendor_id:
            self._logger.warning(
                "quarterly_tax_vendor_missing",
                org=ctx.name,
                vendor=action.tax_vendor,
            )
            return False

        bill_id = record.get("bill_id")
        bill = None
        if bill_id:
            try:
                bill = await self._api_client.get_bill(UUID(bill_id))
            except AtlasAPIError:
                bill = None

        if not bill:
            bill = await self._find_quarterly_tax_bill(vendor_id, action)
            if bill and bill.get("id"):
                bill_id = str(bill["id"])
                self._set_quarterly_tax_record(
                    ctx.id, action.tax_year, action.quarter, bill_id=bill_id
                )

        if not bill_id:
            self._logger.warning(
                "quarterly_tax_bill_missing",
                org=ctx.name,
                tax_year=action.tax_year,
                quarter=action.quarter,
            )
            return False

        if bill and bill.get("status") == "draft":
            try:
                bill = await self._api_client.approve_bill(UUID(bill_id))
            except AtlasAPIError as exc:
                self._logger.warning(
                    "quarterly_tax_bill_approve_failed",
                    org=ctx.name,
                    tax_year=action.tax_year,
                    quarter=action.quarter,
                    error=str(exc),
                )
                return False

        amount_raw = None
        if estimate:
            amount_raw = estimate.get("remaining_due") or estimate.get("amount_due")
        if amount_raw is None and bill:
            amount_raw = bill.get("balance") or bill.get("total_amount")
        if amount_raw is None:
            amount_raw = str(action.estimated_tax)
        try:
            amount = Decimal(str(amount_raw)).quantize(Decimal("0.01"))
        except (ValueError, TypeError):
            amount = action.estimated_tax

        try:
            await self._api_client.create_bill_payment(
                {
                    "bill_id": bill_id,
                    "amount": str(amount),
                    "payment_date": sim_date.isoformat(),
                    "payment_method": "check",
                }
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "quarterly_tax_bill_payment_failed",
                org=ctx.name,
                tax_year=action.tax_year,
                quarter=action.quarter,
                error=str(exc),
            )
            return False

        try:
            await self._api_client.record_quarterly_estimate_payment(
                estimate_id=UUID(estimate_id),
                amount=str(amount),
                payment_date=sim_date,
                payment_method="check",
            )
        except AtlasAPIError as exc:
            self._logger.warning(
                "quarterly_estimate_payment_failed",
                org=ctx.name,
                tax_year=action.tax_year,
                quarter=action.quarter,
                error=str(exc),
            )
            return False

        self._tx_generator.mark_quarterly_tax_paid(
            ctx.owner_key, action.tax_year, action.quarter
        )
        return True

    # === Task Execution ===

    async def run_single_task(self, task: str, org_id: UUID | None = None) -> str:
        """Run a single task using the accountant agent.

        Args:
            task: The task description.
            org_id: Optional org to switch to before running.

        Returns:
            The agent's final response.
        """
        if not self._accountant:
            raise RuntimeError("Orchestrator not initialized")

        if org_id:
            await self.switch_organization(org_id)

        # Publish thinking event
        self._event_publisher.publish(
            agent_thinking(
                agent_id=self._accountant.id,
                agent_name=self._accountant.name,
                prompt=task,
                org_id=self._current_org_id,
            )
        )

        self._logger.info("running_task", task=task[:100])

        response = await self._accountant.run_task(task)

        # Publish speaking event with response
        self._event_publisher.publish(
            agent_speaking(
                agent_id=self._accountant.id,
                agent_name=self._accountant.name,
                message=response,
                org_id=self._current_org_id,
            )
        )

        return response

    # === Phase Handlers ===

    async def _handle_early_morning(self, time: Any, phase: DayPhase) -> list[Any]:
        """Early morning: Prep and planning."""
        results: list[Any] = []
        day = self._scheduler.current_time.day
        sim_date = self._get_simulation_date()

        self._event_publisher.publish(
            phase_started(day, phase.value, "Business prep and planning")
        )

        # Sarah reviews her schedule
        if self._accountant:
            self._event_publisher.publish(
                agent_speaking(
                    agent_id=self._accountant.id,
                    agent_name=self._accountant.name,
                    message="Good morning! Let me review today's schedule and priorities.",
                    org_id=None,
                )
            )

        self._maybe_publish_vendor_price_increases(sim_date)

        # Generate deterministic recurring bills (once per day)
        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            if not self._api_client:
                continue

            try:
                vendors = await self._api_client.list_vendors()
                recurring = self._tx_generator.generate_recurring_transactions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                    vendors=vendors,
                )
                payroll = self._tx_generator.generate_payroll_transactions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                    vendors=vendors,
                )
                quarterly_actions = self._tx_generator.generate_quarterly_tax_actions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                )

                bills_created = 0
                quarterly_created = 0
                quarterly_paid = 0
                for tx in recurring + payroll:
                    if tx.transaction_type == TransactionType.BILL:
                        created = await self._create_bill(ctx, tx, sim_date)
                        if created:
                            bills_created += 1

                for action in quarterly_actions:
                    if action.action == "create":
                        if await self._create_quarterly_tax_bill(
                            ctx, sim_date, vendors, action
                        ):
                            quarterly_created += 1
                    elif action.action == "pay" and await self._pay_quarterly_tax_bill(
                        ctx, sim_date, vendors, action
                    ):
                        quarterly_paid += 1

                if bills_created > 0 or quarterly_created > 0 or quarterly_paid > 0:
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=self._accountant.id if self._accountant else UUID(int=0),
                            agent_name="Sarah Chen",
                            message=(
                                f"{ctx.name}: Recorded {bills_created} scheduled bill(s), "
                                f"{quarterly_created} quarterly tax bill(s), "
                                f"{quarterly_paid} quarterly tax payment(s)."
                            ),
                            org_id=org_id,
                        )
                    )

                period_end_results = await self._run_period_end_tasks(
                    org_id=org_id,
                    ctx=ctx,
                    sim_date=sim_date,
                )

                if period_end_results and "quarter_end" in period_end_results:
                    quarter_info = period_end_results["quarter_end"]
                    reports = (
                        quarter_info.get("management_reports", {})
                        if isinstance(quarter_info, dict)
                        else {}
                    )
                    revenue_total = Decimal(str(reports.get("revenue_total") or "0"))
                    expense_total = Decimal(str(reports.get("expense_total") or "0"))
                    net_income = revenue_total - expense_total
                    top_customer = None
                    top_expense = None
                    revenue_by_customer = reports.get("revenue_by_customer")
                    if isinstance(revenue_by_customer, list) and revenue_by_customer:
                        top_customer = revenue_by_customer[0].get("name")
                    expenses_by_category = reports.get("expenses_by_category")
                    if isinstance(expenses_by_category, list) and expenses_by_category:
                        top_expense = expenses_by_category[0].get("name")
                    owner_name = ctx.owner.name if ctx.owner else "Owner"
                    summary = (
                        f"Quarterly review for {ctx.name}: "
                        f"Revenue ${revenue_total:,.2f}, "
                        f"Expenses ${expense_total:,.2f}, "
                        f"Net ${net_income:,.2f}."
                    )
                    if top_customer:
                        summary += f" Top customer: {top_customer}."
                    if top_expense:
                        summary += f" Top expense category: {top_expense}."
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=self._accountant.id if self._accountant else UUID(int=0),
                            agent_name="Sarah Chen",
                            message=f"{owner_name} review: {summary}",
                            org_id=org_id,
                        )
                    )

                if period_end_results:
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=self._accountant.id if self._accountant else UUID(int=0),
                            agent_name="Sarah Chen",
                            message=(
                                f"{ctx.name}: Completed period-end tasks "
                                f"({', '.join(period_end_results.keys())})."
                            ),
                            org_id=org_id,
                        )
                    )

                results.append(
                    {
                        "org": ctx.name,
                        "recurring_bills": bills_created,
                        "quarterly_tax_bills": quarterly_created,
                        "quarterly_tax_payments": quarterly_paid,
                        "period_end": period_end_results,
                    }
                )

            except Exception as exc:
                self._logger.error(
                    "recurring_bills_error",
                    org=ctx.name,
                    error=str(exc),
                )

        b2b_results = await self._process_b2b_transactions(sim_date)
        if b2b_results:
            self._event_publisher.publish(
                agent_speaking(
                    agent_id=self._accountant.id if self._accountant else UUID(int=0),
                    agent_name="Sarah Chen",
                    message=f"Recorded {len(b2b_results)} B2B paired transaction(s).",
                    org_id=None,
                )
            )
            results.append(
                {
                    "b2b_pairs": len(b2b_results),
                }
            )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_morning(self, time: Any, phase: DayPhase) -> list[Any]:
        """Morning: Generate new business activity (invoices, sales)."""
        results: list[Any] = []
        day = self._scheduler.current_time.day
        sim_date = self._get_simulation_date()

        self._event_publisher.publish(
            phase_started(day, phase.value, "Morning business activity")
        )

        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            try:
                # Get customers and vendors for this org
                customers = await self._api_client.list_customers() if self._api_client else []
                vendors = await self._api_client.list_vendors() if self._api_client else []

                # Generate realistic transactions for this business
                transactions = self._tx_generator.generate_daily_transactions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                    customers=customers,
                    vendors=vendors,
                    current_hour=self._scheduler.current_time.hour,
                    current_phase=phase.value,
                    hourly=True,
                )

                # Process invoices and sales
                invoices_created = 0
                for tx in transactions:
                    if tx.transaction_type in [TransactionType.INVOICE, TransactionType.CASH_SALE]:
                        await self._create_invoice(ctx, tx, sim_date)
                        invoices_created += 1

                if invoices_created > 0:
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=self._accountant.id if self._accountant else UUID(int=0),
                            agent_name="Sarah Chen",
                            message=f"Created {invoices_created} invoice(s) for {ctx.name} today.",
                            org_id=org_id,
                        )
                    )

                results.append({
                    "org": ctx.name,
                    "invoices_created": invoices_created,
                    "transaction_count": len(transactions),
                })

            except Exception as e:
                self._logger.error("morning_task_error", org=ctx.name, error=str(e))
                self._event_publisher.publish(
                    error_event(f"Error generating business for {ctx.name}", {"error": str(e)})
                )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_lunch(self, time: Any, phase: DayPhase) -> list[Any]:
        """Lunch: Mid-day lull, light activity."""
        results: list[Any] = []
        day = self._scheduler.current_time.day

        self._event_publisher.publish(
            phase_started(day, phase.value, "Mid-day break")
        )

        # Light activity during lunch
        if self._accountant:
            self._event_publisher.publish(
                agent_speaking(
                    agent_id=self._accountant.id,
                    agent_name=self._accountant.name,
                    message="Taking a quick break. Will continue with the afternoon tasks shortly.",
                    org_id=None,
                )
            )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_afternoon(self, time: Any, phase: DayPhase) -> list[Any]:
        """Afternoon: Process bills and receive payments."""
        results: list[Any] = []
        day = self._scheduler.current_time.day
        sim_date = self._get_simulation_date()

        self._event_publisher.publish(
            phase_started(day, phase.value, "Peak afternoon activity")
        )

        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            try:
                # Get customers, vendors, and pending invoices
                customers = (
                    await self._api_client.list_customers() if self._api_client else []
                )
                vendors = (
                    await self._api_client.list_vendors() if self._api_client else []
                )
                if self._api_client:
                    pending_sent = await self._api_client.list_invoices(status="sent")
                    pending_overdue = await self._api_client.list_invoices(status="overdue")
                    pending_partial = await self._api_client.list_invoices(status="partial")
                    pending_invoices = list({
                        str(inv.get("id")): inv
                        for inv in pending_sent + pending_overdue + pending_partial
                        if inv.get("id")
                    }.values())
                    pending_approved_bills = await self._api_client.list_bills(status="approved")
                    pending_partial_bills = await self._api_client.list_bills(status="partial")
                    pending_bills = list({
                        str(bill.get("id")): bill
                        for bill in pending_approved_bills + pending_partial_bills
                        if bill.get("id")
                    }.values())
                else:
                    pending_invoices = []
                    pending_bills = []

                cash_policy = self._tx_generator.get_cash_flow_policy(ctx.owner_key)
                cash_position: Decimal | None = None
                reserve_target = Decimal("0")
                if cash_policy:
                    cash_position, _ = await self._get_cash_position(org_id)
                    reserve_target = self._tx_generator.get_reserve_target(
                        ctx.owner_key, sim_date
                    )
                    cash_position = await self._maybe_draw_loc(
                        ctx, sim_date, cash_position, reserve_target, cash_policy
                    )
                    cash_position = await self._maybe_build_reserve(
                        ctx, sim_date, cash_position, reserve_target
                    )

                # Generate transactions (bills and payments)
                transactions = self._tx_generator.generate_daily_transactions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                    customers=customers,
                    vendors=vendors,
                    pending_invoices=pending_invoices,
                    pending_bills=pending_bills,
                    current_hour=self._scheduler.current_time.hour,
                    current_phase=phase.value,
                    hourly=True,
                )

                bills_created = 0
                payments_received = 0
                bills_paid = 0

                for tx in transactions:
                    if tx.transaction_type == TransactionType.BILL:
                        await self._create_bill(ctx, tx, sim_date)
                        bills_created += 1
                    elif tx.transaction_type == TransactionType.PAYMENT_RECEIVED:
                        if tx.metadata and tx.metadata.get("invoice_id"):
                            await self._record_payment(ctx, tx)
                            payments_received += 1
                            if cash_position is not None:
                                cash_position += tx.amount
                    elif tx.transaction_type == TransactionType.BILL_PAYMENT:
                        if tx.metadata and tx.metadata.get("bill_id"):
                            if cash_position is not None:
                                should_pay = await self._should_pay_bill(
                                    ctx,
                                    tx.metadata["bill_id"],
                                    cash_position,
                                    reserve_target,
                                    cash_policy,
                                )
                            else:
                                should_pay = True
                            if should_pay:
                                await self._pay_bill(ctx, tx)
                                bills_paid += 1
                                if cash_position is not None:
                                    cash_position -= tx.amount

                if bills_created > 0 or payments_received > 0 or bills_paid > 0:
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=(
                                self._accountant.id
                                if self._accountant
                                else UUID(int=0)
                            ),
                            agent_name="Sarah Chen",
                            message=(
                                f"{ctx.name}: Recorded {bills_created} bill(s), "
                                f"received {payments_received} payment(s), "
                                f"paid {bills_paid} bill(s)."
                            ),
                            org_id=org_id,
                        )
                    )

                results.append({
                    "org": ctx.name,
                    "bills_created": bills_created,
                    "payments_received": payments_received,
                    "bills_paid": bills_paid,
                })

            except Exception as e:
                self._logger.error("afternoon_task_error", org=ctx.name, error=str(e))
                self._event_publisher.publish(
                    error_event(f"Error processing {ctx.name}", {"error": str(e)})
                )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_evening(self, time: Any, phase: DayPhase) -> list[Any]:
        """Evening: Dinner rush for restaurants + reconciliation and reports.

        Behavior depends on simulation mode:
        - FAST: Uses AccountingWorkflow (rule-based, no LLM)
        - LLM: Uses AccountantAgent (full LLM reasoning)
        - HYBRID: Uses AccountingWorkflow + LLM for analysis if issues found
        """
        results: list[Any] = []
        day = self._scheduler.current_time.day
        sim_date = self._get_simulation_date()

        mode_desc = {
            SimulationMode.FAST: "fast mode (rule-based)",
            SimulationMode.LLM: "LLM mode (agent reasoning)",
            SimulationMode.HYBRID: "hybrid mode (rules + LLM analysis)",
        }

        self._event_publisher.publish(
            phase_started(day, phase.value, f"Evening activity - {mode_desc[self._mode]}")
        )

        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            try:
                if self._mode == SimulationMode.FAST:
                    # FAST MODE: Use rule-based workflow (no LLM)
                    result = await self._handle_evening_fast(org_id, ctx, sim_date, phase)
                    results.append(result)

                elif self._mode == SimulationMode.HYBRID:
                    # HYBRID MODE: Rule-based + LLM analysis if issues
                    result = await self._handle_evening_hybrid(org_id, ctx, sim_date, phase)
                    results.append(result)

                else:
                    # LLM MODE: Full agent reasoning (original behavior)
                    result = await self._handle_evening_llm(org_id, ctx, sim_date, phase)
                    results.append(result)

            except Exception as e:
                self._logger.error("evening_task_error", org=ctx.name, error=str(e))
                self._event_publisher.publish(
                    error_event(f"Error during evening for {ctx.name}", {"error": str(e)})
                )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    def _get_accounting_workflow(self, org_id: UUID) -> AccountingWorkflow:
        if self._accounting_workflow:
            return self._accounting_workflow
        workflow = self._accounting_workflows.get(org_id)
        if workflow:
            return workflow
        raise RuntimeError("AccountingWorkflow not initialized")

    async def _run_period_end_tasks(
        self,
        org_id: UUID,
        ctx: OrganizationContext,
        sim_date: date,
    ) -> dict[str, Any]:
        if self._mode in (SimulationMode.FAST, SimulationMode.HYBRID):
            workflow = self._get_accounting_workflow(org_id)
            return await workflow.run_period_end_workflow(
                business_key=ctx.owner_key,
                org_id=org_id,
                current_date=sim_date,
            )
        if self._mode == SimulationMode.LLM:
            return await self._run_period_end_llm(org_id, ctx, sim_date)
        return {}

    async def _run_period_end_llm(
        self,
        org_id: UUID,
        ctx: OrganizationContext,
        sim_date: date,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}

        month_period = AccountingWorkflow._month_end_period(sim_date)
        if month_period:
            start, end, year, month = month_period
            key = (org_id, year, month)
            if key not in self._month_end_llm_done:
                task = (
                    f"Month-end close for {ctx.name} "
                    f"(period {start.isoformat()} to {end.isoformat()}). "
                    "Please run AR aging, AP aging, review bank transactions for "
                    "unmatched items, record any accrual adjustments needed with a "
                    "journal entry, and run a trial balance as of period end."
                )
                await self.run_single_task(task, org_id=org_id)
                self._month_end_llm_done.add(key)
                results["month_end"] = {
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                }

        quarter_period = AccountingWorkflow._quarter_end_period(sim_date)
        if quarter_period:
            start, end, year, quarter = quarter_period
            quarter_key = (org_id, year, quarter)
            if quarter_key not in self._quarter_end_llm_done:
                task = (
                    f"Quarter-end close for {ctx.name} (Q{quarter} {year}). "
                    f"Generate Profit & Loss for {start.isoformat()} to {end.isoformat()}, "
                    f"Balance Sheet as of {end.isoformat()}, and Cash Flow for the period. "
                    "Estimate a tax provision and record it as a journal entry. "
                    "Summarize key metrics for owner review."
                )
                await self.run_single_task(task, org_id=org_id)
                self._quarter_end_llm_done.add(quarter_key)
                results["quarter_end"] = {
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                    "quarter": quarter,
                    "year": year,
                }

        if sim_date.month == 12 and sim_date.day == 31:
            year = sim_date.year
            year_end_key = (org_id, year)
            if year_end_key not in self._year_end_llm_done:
                task = (
                    f"Year-end close for {ctx.name} as of {sim_date.isoformat()}. "
                    "Record depreciation, complete inventory adjustments if applicable, "
                    "and post closing entries to transfer net income to retained earnings."
                )
                await self.run_single_task(task, org_id=org_id)
                self._year_end_llm_done.add(year_end_key)
                results["year_end"] = {"year": year}

        if sim_date.month == 1 and sim_date.day <= 31:
            prior_year = sim_date.year - 1
            reporting_key = (org_id, prior_year)
            if reporting_key not in self._year_end_reporting_done:
                task = (
                    f"Year-end reporting for {ctx.name} ({prior_year}). "
                    "Compile 1099-NEC vendor filings and confirm they are prepared. "
                    "Note any missing W-9 information or follow-ups needed."
                )
                await self.run_single_task(task, org_id=org_id)
                self._year_end_reporting_done.add(reporting_key)
                results["year_end_reporting"] = {"tax_year": prior_year}

        return results

    async def _handle_evening_fast(
        self,
        org_id: UUID,
        ctx: OrganizationContext,
        sim_date: date,
        phase: DayPhase,
    ) -> dict[str, Any]:
        """Evening handler for FAST mode - rule-based, no LLM calls."""
        workflow = self._get_accounting_workflow(org_id)

        # Run the complete daily workflow
        summary = await workflow.run_daily_workflow(
            business_key=ctx.owner_key,
            org_id=org_id,
            current_date=sim_date,
            current_hour=self._scheduler.current_time.hour,
            current_phase=phase.value,
        )

        # Publish summary as agent speaking (for UI consistency)
        self._event_publisher.publish(
            agent_speaking(
                agent_id=UUID(int=0),  # No agent in fast mode
                agent_name="Sarah Chen (Auto)",
                message=summary.to_text()[:500],
                org_id=org_id,
            )
        )

        return {
            "org": ctx.name,
            "mode": "fast",
            "invoices_created": summary.invoices_created,
            "bills_created": summary.bills_created,
            "payments_received": summary.payments_received,
            "trial_balance_ok": summary.trial_balance_ok,
            "issues": summary.issues,
        }

    async def _handle_evening_hybrid(
        self,
        org_id: UUID,
        ctx: OrganizationContext,
        sim_date: date,
        phase: DayPhase,
    ) -> dict[str, Any]:
        """Evening handler for HYBRID mode - rule-based ops + LLM analysis."""
        workflow = self._get_accounting_workflow(org_id)

        # Run rule-based workflow first (fast)
        summary = await workflow.run_daily_workflow(
            business_key=ctx.owner_key,
            org_id=org_id,
            current_date=sim_date,
            current_hour=self._scheduler.current_time.hour,
            current_phase=phase.value,
        )

        result = {
            "org": ctx.name,
            "mode": "hybrid",
            "invoices_created": summary.invoices_created,
            "bills_created": summary.bills_created,
            "payments_received": summary.payments_received,
            "trial_balance_ok": summary.trial_balance_ok,
            "issues": summary.issues,
        }

        # If there are issues, use LLM for analysis
        if summary.issues and self._accountant:
            self._logger.info(
                "hybrid_mode_llm_analysis",
                org=ctx.name,
                issues_count=len(summary.issues),
            )

            task = f"""Analyze these issues for {ctx.name} and recommend actions:

{summary.to_text()}

Please provide specific recommendations for addressing each issue."""

            analysis = await self.run_single_task(task)
            result["llm_analysis"] = analysis[:500]

            self._event_publisher.publish(
                agent_speaking(
                    agent_id=self._accountant.id,
                    agent_name="Sarah Chen",
                    message=analysis[:500],
                    org_id=org_id,
                )
            )
        else:
            # No issues - just publish the summary
            self._event_publisher.publish(
                agent_speaking(
                    agent_id=UUID(int=0),
                    agent_name="Sarah Chen (Auto)",
                    message=summary.to_text()[:500],
                    org_id=org_id,
                )
            )

        return result

    async def _handle_evening_llm(
        self,
        org_id: UUID,
        ctx: OrganizationContext,
        sim_date: date,
        phase: DayPhase,
    ) -> dict[str, Any]:
        """Evening handler for LLM mode - full agent reasoning (original behavior)."""
        # Generate evening transactions (dinner rush for restaurants)
        customers = await self._api_client.list_customers() if self._api_client else []
        vendors = await self._api_client.list_vendors() if self._api_client else []

        transactions = self._tx_generator.generate_daily_transactions(
            business_key=ctx.owner_key,
            current_date=sim_date,
            customers=customers,
            vendors=vendors,
            current_hour=self._scheduler.current_time.hour,
            current_phase=phase.value,
            hourly=True,
        )

        # Process cash sales and invoices (dinner rush)
        invoices_created = 0
        for tx in transactions:
            if tx.transaction_type in [TransactionType.INVOICE, TransactionType.CASH_SALE]:
                await self._create_invoice(ctx, tx, sim_date)
                invoices_created += 1

        if invoices_created > 0:
            self._event_publisher.publish(
                agent_speaking(
                    agent_id=self._accountant.id if self._accountant else UUID(int=0),
                    agent_name="Sarah Chen",
                    message=(
                        f"Created {invoices_created} evening invoice(s) for "
                        f"{ctx.name} (dinner rush)."
                    ),
                    org_id=org_id,
                )
            )

        collection_summary: CollectionSummary | None = None
        collection_issues: list[str] = []
        try:
            workflow = self._get_accounting_workflow(org_id)
            collection_summary = await workflow.run_collection_workflow(
                business_key=ctx.owner_key,
                org_id=org_id,
                current_date=sim_date,
            )
            if collection_summary is not None:
                collection_issues = workflow.format_collection_issues(collection_summary)
        except Exception as exc:
            self._logger.warning(
                "llm_collection_workflow_failed",
                org=ctx.name,
                error=str(exc),
            )

        # End of day accounting task (LLM reasoning)
        collection_note = ""
        if collection_issues:
            collection_note = (
                "Collection workflow summary: " + "; ".join(collection_issues) + "\n"
            )
        task = f"""End of day for {ctx.name}. Please:
        1. Run a trial balance to ensure books are balanced
        2. Provide a quick summary of today's activity
        3. Note any issues that need attention tomorrow

{collection_note}"""

        response = await self.run_single_task(task)

        return {
            "org": ctx.name,
            "mode": "llm",
            "invoices_created": invoices_created,
            "collection_issues": collection_issues,
            "collection_summary": collection_summary,
            "response": response[:200],
        }

    async def _handle_night(self, time: Any, phase: DayPhase) -> list[Any]:
        """Night: Late-night transactions and day transition cleanup."""
        results: list[Any] = []
        day = self._scheduler.current_time.day
        sim_date = self._get_simulation_date()

        self._event_publisher.publish(
            phase_started(day, phase.value, "Late-night activity and cleanup")
        )

        # Generate late-night transactions (e.g., late-night pizza orders)
        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            try:
                customers = await self._api_client.list_customers() if self._api_client else []
                vendors = await self._api_client.list_vendors() if self._api_client else []

                transactions = self._tx_generator.generate_daily_transactions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                    customers=customers,
                    vendors=vendors,
                    current_hour=self._scheduler.current_time.hour,
                    current_phase=phase.value,
                    hourly=True,
                )

                # Process late-night cash sales
                invoices_created = 0
                for tx in transactions:
                    if tx.transaction_type == TransactionType.CASH_SALE:
                        await self._create_invoice(ctx, tx, sim_date)
                        invoices_created += 1

                if invoices_created > 0:
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=self._accountant.id if self._accountant else UUID(int=0),
                            agent_name="Sarah Chen",
                            message=(
                                f"Recorded {invoices_created} late-night sale(s) "
                                f"for {ctx.name}."
                            ),
                            org_id=org_id,
                        )
                    )

                results.append({
                    "org": ctx.name,
                    "late_night_sales": invoices_created,
                })

            except Exception as e:
                self._logger.error("night_transaction_error", org=ctx.name, error=str(e))

        # Clear agent histories for next day
        if self._accountant:
            self._accountant.clear_history()

        for owner in self._owners.values():
            owner.clear_history()

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    # === Simulation Control ===

    async def run_daily_cycle(self) -> dict[DayPhase, list[Any]]:
        """Run a complete daily simulation cycle."""
        if not self._is_initialized:
            raise RuntimeError("Orchestrator not initialized")

        day = self._scheduler.current_time.day

        self._event_publisher.publish(day_started(day))
        self._logger.info("daily_cycle_started", day=day)

        try:
            results = await self._scheduler.run_day()

            self._event_publisher.publish(
                day_completed(day, {"phase_count": len(results)})
            )
            self._logger.info("daily_cycle_completed", day=day)

            return results

        except Exception as e:
            self._logger.exception("daily_cycle_error", error=str(e))
            self._event_publisher.publish(
                error_event("Daily cycle failed", {"error": str(e)})
            )
            raise

    async def run_simulation(
        self,
        max_days: int | None = None,
        speed: float | None = None,
    ) -> None:
        """Run the simulation continuously.

        Args:
            max_days: Optional maximum number of days to simulate.
            speed: Optional speed multiplier override.
        """
        if not self._is_initialized:
            raise RuntimeError("Orchestrator not initialized")

        if speed:
            self._scheduler.speed = speed

        self._event_publisher.publish(
            simulation_started(self._scheduler.speed, max_days)
        )

        self._logger.info(
            "simulation_starting",
            max_days=max_days,
            speed=self._scheduler.speed,
        )

        try:
            await self._scheduler.run_continuous(max_days)

        finally:
            days_run = self._scheduler.current_time.day - 1
            self._event_publisher.publish(
                simulation_stopped(days_run, "completed")
            )
            self._logger.info("simulation_ended", days_run=days_run)

    def pause(self) -> None:
        """Pause the simulation."""
        self._scheduler.pause()
        self._logger.info("simulation_paused")

    def resume(self) -> None:
        """Resume the simulation."""
        self._scheduler.resume()
        self._logger.info("simulation_resumed")

    def stop(self) -> None:
        """Stop the simulation."""
        self._scheduler.stop()
        self._event_publisher.publish(
            simulation_stopped(self._scheduler.current_time.day - 1, "stopped")
        )
        self._logger.info("simulation_stopped")

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "is_initialized": self._is_initialized,
            "scheduler": self._scheduler.get_status(),
            "publisher": self._event_publisher.get_status(),
            "organizations": [
                {
                    "id": str(ctx.id),
                    "name": ctx.name,
                    "industry": ctx.industry,
                    "owner": ctx.owner.name if ctx.owner else None,
                    "customer_count": len(ctx.customers),
                    "vendor_count": len(ctx.vendors),
                }
                for ctx in self._organizations.values()
            ],
            "current_org": str(self._current_org_id) if self._current_org_id else None,
        }


async def main() -> None:
    """Main entry point for running the simulation.

    Usage:
        # Run one day in LLM mode (default)
        uv run python -m atlas_town.orchestrator

        # Run multiple days
        uv run python -m atlas_town.orchestrator --days=7

        # Run in fast mode (no LLM, 15x faster)
        uv run python -m atlas_town.orchestrator --mode=fast --days=30

        # Run in hybrid mode (fast ops + LLM analysis)
        uv run python -m atlas_town.orchestrator --mode=hybrid --days=7

        # Run a single task (always uses LLM)
        uv run python -m atlas_town.orchestrator "Run trial balance for Tony's"
    """
    import argparse
    import sys

    from atlas_town.config import configure_logging

    configure_logging()

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Atlas Town Accounting Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  llm     Full LLM agent reasoning (default, slower, costs money)
  fast    Rule-based workflow (15x faster, no API cost)
  hybrid  Rule-based operations + LLM for analysis when issues detected

Examples:
  %(prog)s                          # Run 1 day in LLM mode
  %(prog)s --days=30                # Run 30 days in LLM mode
  %(prog)s --mode=fast --days=365   # Run 1 year in fast mode (~12 min)
  %(prog)s --mode=hybrid --days=7   # Run 1 week in hybrid mode
  %(prog)s "Why is revenue down?"   # Run a single LLM task
        """,
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["llm", "fast", "hybrid"],
        default="llm",
        help="Simulation mode (default: llm)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to simulate (default: 1)",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Optional task for Sarah to complete (uses LLM mode)",
    )

    args = parser.parse_args()

    # Determine mode
    mode = SimulationMode(args.mode)

    # If a task is provided, always use LLM mode
    task = " ".join(args.task) if args.task else None
    if task:
        mode = SimulationMode.LLM

    logger.info(
        "starting_atlas_town_simulation",
        mode=mode.value,
        days=args.days if not task else "single_task",
    )

    try:
        async with Orchestrator(mode=mode) as orchestrator:
            if task:
                # Run a single task (always LLM)
                response = await orchestrator.run_single_task(task)
                print(f"\n{'='*60}")
                print("Sarah's Response:")
                print("=" * 60)
                print(response)
            elif args.days > 1:
                # Run multiple days
                await orchestrator.run_simulation(max_days=args.days)
            else:
                # Run one day
                await orchestrator.run_daily_cycle()

    except KeyboardInterrupt:
        logger.info("simulation_interrupted")
    except Exception as e:
        logger.exception("simulation_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
