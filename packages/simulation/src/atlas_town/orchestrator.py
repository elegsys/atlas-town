"""Orchestrator - coordinates agents and simulation lifecycle.

The orchestrator is the main coordinator for the Atlas Town simulation.
It manages:
- Multiple organizations and their owner agents
- The accountant agent (Sarah) who visits each business
- Customer and vendor agents for generating transactions
- Event publishing for real-time frontend updates
- Daily simulation cycles with phase transitions
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog

from atlas_town.agents import (
    AccountantAgent,
    AgentState,
    CustomerAgent,
    OwnerAgent,
    VendorAgent,
    create_all_owners,
    create_customers_for_industry,
    create_vendors_for_industry,
)
from atlas_town.clients import ClaudeClient, GeminiClient, OpenAIClient
from atlas_town.config import get_settings
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
    tool_called,
    tool_completed,
    tool_failed,
    transaction_created,
)
from atlas_town.scheduler import DayPhase, Scheduler
from atlas_town.tools import AtlasAPIClient, ToolExecutor
from atlas_town.transactions import (
    GeneratedTransaction,
    TransactionGenerator,
    TransactionType,
    create_transaction_generator,
)

logger = structlog.get_logger(__name__)


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
    ):
        settings = get_settings()

        # API client and tools
        self._api_client: AtlasAPIClient | None = None
        self._tool_executor: ToolExecutor | None = None

        # LLM clients (created on demand)
        self._claude_client: ClaudeClient | None = None
        self._openai_client: OpenAIClient | None = None
        self._gemini_client: GeminiClient | None = None

        # Agents
        self._accountant: AccountantAgent | None = None
        self._owners: dict[str, OwnerAgent] = {}

        # Organizations
        self._organizations: dict[UUID, OrganizationContext] = {}
        self._org_by_owner: dict[str, UUID] = {}  # owner_key -> org_id

        # Scheduler
        self._scheduler = Scheduler(speed_multiplier=settings.simulation_speed)

        # Event publishing
        self._event_publisher = event_publisher or get_publisher()
        self._start_websocket = start_websocket

        # Transaction generator for realistic daily activity
        self._tx_generator = create_transaction_generator()

        # State
        self._is_initialized = False
        self._current_org_id: UUID | None = None

        # Logging
        self._logger = logger.bind(component="orchestrator")

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

        # Create and authenticate API client
        self._api_client = AtlasAPIClient()
        await self._api_client.login()

        # Create tool executor
        self._tool_executor = ToolExecutor(self._api_client)

        # Load organizations and create agents
        await self._setup_organizations()
        self._create_agents()

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

        if self._api_client:
            await self._api_client.close()

        if self._start_websocket and self._event_publisher.is_running:
            await self._event_publisher.stop()

        self._is_initialized = False

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

    def _create_agents(self) -> None:
        """Create all agent instances."""
        # Create accountant (Sarah)
        self._accountant = AccountantAgent()
        if self._tool_executor:
            self._accountant.set_tool_executor(self._tool_executor)

        # Create owners for each organization
        self._owners = create_all_owners(self._org_by_owner)

        # Assign owners to organizations and create customers/vendors
        for org_id, ctx in self._organizations.items():
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

    def _find_expense_account(self, accounts: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Find an expense account using multiple strategies.

        Tries in order:
        1. account_type == "expense" (most correct)
        2. account_number starting with "5" or "6" (US GAAP expense accounts)
        3. name containing "expense" (fallback)
        """
        # Strategy 1: By account_type (most reliable if available)
        account = next(
            (a for a in accounts if a.get("account_type") == "expense"),
            None
        )
        if account:
            return account

        # Strategy 2: By account_number (US GAAP: 5xxx/6xxx = Expenses)
        account = next(
            (a for a in accounts
             if str(a.get("account_number", "")).startswith(("5", "6"))),
            None
        )
        if account:
            return account

        # Strategy 3: By name containing "expense" (last resort)
        account = next(
            (a for a in accounts if "expense" in a.get("name", "").lower()),
            None
        )
        return account

    def _get_simulation_date(self) -> date:
        """Get the current simulation date based on day number."""
        base_date = date.today() - timedelta(days=30)  # Start 30 days ago
        return base_date + timedelta(days=self._scheduler.current_time.day - 1)

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

            invoice_data = {
                "customer_id": str(tx.customer_id),
                "invoice_date": sim_date.isoformat(),
                "due_date": (sim_date + timedelta(days=30)).isoformat(),
                "lines": [{
                    "description": tx.description,
                    "quantity": "1",
                    "unit_price": str(tx.amount),
                    "revenue_account_id": revenue_account["id"],
                }],
            }

            result = await self._api_client.create_invoice(invoice_data)

            # Publish event
            self._event_publisher.publish(
                transaction_created(
                    tx_type="invoice",
                    amount=str(tx.amount),
                    description=tx.description,
                    org_id=ctx.id,
                    org_name=ctx.name,
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
            expense_account = self._find_expense_account(accounts)

            if not expense_account:
                self._logger.warning(
                    "no_expense_account_found",
                    org=ctx.name,
                    account_count=len(accounts),
                    msg="Cannot create bill - no expense account in chart of accounts",
                )
                return None

            bill_data = {
                "vendor_id": str(tx.vendor_id),
                "bill_date": sim_date.isoformat(),
                "due_date": (sim_date + timedelta(days=30)).isoformat(),
                "bill_number": f"BILL-{sim_date.strftime('%Y%m%d')}-{random.randint(100, 999)}",
                "lines": [{
                    "description": tx.description,
                    "quantity": "1",
                    "unit_price": str(tx.amount),
                    "expense_account_id": expense_account["id"],
                }],
            }

            result = await self._api_client.create_bill(bill_data)

            # Publish event
            self._event_publisher.publish(
                transaction_created(
                    tx_type="bill",
                    amount=str(tx.amount),
                    description=tx.description,
                    org_id=ctx.id,
                    org_name=ctx.name,
                )
            )

            self._logger.info("bill_created", org=ctx.name, amount=str(tx.amount))
            return result

        except Exception as e:
            self._logger.error("bill_creation_failed", error=str(e))
            return None

    async def _record_payment(
        self,
        ctx: OrganizationContext,
        tx: GeneratedTransaction,
    ) -> dict[str, Any] | None:
        """Record a payment received for an invoice."""
        if not self._api_client or not tx.metadata:
            return None

        invoice_id = tx.metadata.get("invoice_id")
        if not invoice_id:
            return None

        try:
            # Create payment
            payment_data = {
                "customer_id": str(tx.customer_id) if tx.customer_id else None,
                "amount": str(tx.amount),
                "payment_date": self._get_simulation_date().isoformat(),
                "payment_method": "check",
                "reference": f"PMT-{random.randint(10000, 99999)}",
            }

            result = await self._api_client.create_payment(payment_data)

            if result and result.get("id"):
                # Apply to invoice
                await self._api_client.apply_payment_to_invoice(
                    UUID(result["id"]),
                    UUID(invoice_id),
                    str(tx.amount),
                )

            # Publish event
            self._event_publisher.publish(
                transaction_created(
                    tx_type="payment",
                    amount=str(tx.amount),
                    description=tx.description,
                    org_id=ctx.id,
                    org_name=ctx.name,
                )
            )

            self._logger.info("payment_received", org=ctx.name, amount=str(tx.amount))
            return result

        except Exception as e:
            self._logger.error("payment_failed", error=str(e))
            return None

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
        results = []
        day = self._scheduler.current_time.day

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

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_morning(self, time: Any, phase: DayPhase) -> list[Any]:
        """Morning: Generate new business activity (invoices, sales)."""
        results = []
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
        results = []
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
        results = []
        day = self._scheduler.current_time.day
        sim_date = self._get_simulation_date()

        self._event_publisher.publish(
            phase_started(day, phase.value, "Peak afternoon activity")
        )

        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            try:
                # Get customers, vendors, and pending invoices
                customers = await self._api_client.list_customers() if self._api_client else []
                vendors = await self._api_client.list_vendors() if self._api_client else []
                pending_invoices = await self._api_client.list_invoices(status="sent") if self._api_client else []

                # Generate transactions (bills and payments)
                transactions = self._tx_generator.generate_daily_transactions(
                    business_key=ctx.owner_key,
                    current_date=sim_date,
                    customers=customers,
                    vendors=vendors,
                    pending_invoices=pending_invoices,
                )

                bills_created = 0
                payments_received = 0

                for tx in transactions:
                    if tx.transaction_type == TransactionType.BILL:
                        await self._create_bill(ctx, tx, sim_date)
                        bills_created += 1
                    elif tx.transaction_type == TransactionType.PAYMENT_RECEIVED:
                        if tx.metadata and tx.metadata.get("invoice_id"):
                            await self._record_payment(ctx, tx)
                            payments_received += 1

                if bills_created > 0 or payments_received > 0:
                    self._event_publisher.publish(
                        agent_speaking(
                            agent_id=self._accountant.id if self._accountant else UUID(int=0),
                            agent_name="Sarah Chen",
                            message=f"{ctx.name}: Recorded {bills_created} bill(s), received {payments_received} payment(s).",
                            org_id=org_id,
                        )
                    )

                results.append({
                    "org": ctx.name,
                    "bills_created": bills_created,
                    "payments_received": payments_received,
                })

            except Exception as e:
                self._logger.error("afternoon_task_error", org=ctx.name, error=str(e))
                self._event_publisher.publish(
                    error_event(f"Error processing {ctx.name}", {"error": str(e)})
                )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_evening(self, time: Any, phase: DayPhase) -> list[Any]:
        """Evening: Reconciliation and reports."""
        results = []
        day = self._scheduler.current_time.day

        self._event_publisher.publish(
            phase_started(day, phase.value, "Wind down and accounting")
        )

        for org_id, ctx in self._organizations.items():
            await self.switch_organization(org_id)

            task = f"""End of day for {ctx.name}. Please:
            1. Run a trial balance to ensure books are balanced
            2. Provide a quick summary of today's activity
            3. Note any issues that need attention tomorrow"""

            try:
                response = await self.run_single_task(task)
                results.append({"org": ctx.name, "response": response[:200]})
            except Exception as e:
                self._logger.error("evening_task_error", org=ctx.name, error=str(e))
                self._event_publisher.publish(
                    error_event(f"Error closing {ctx.name}", {"error": str(e)})
                )

        self._event_publisher.publish(phase_completed(day, phase.value, results))
        return results

    async def _handle_night(self, time: Any, phase: DayPhase) -> list[Any]:
        """Night: Day transition and cleanup."""
        results = []
        day = self._scheduler.current_time.day

        self._event_publisher.publish(
            phase_started(day, phase.value, "End of day processing")
        )

        # Clear agent histories
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
    """Main entry point for running the simulation."""
    import sys

    from atlas_town.config import configure_logging

    configure_logging()

    logger.info("starting_atlas_town_simulation")

    try:
        async with Orchestrator() as orchestrator:
            # Parse command line arguments
            if len(sys.argv) > 1:
                if sys.argv[1] == "--run":
                    # Run continuous simulation
                    max_days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
                    await orchestrator.run_simulation(max_days=max_days)
                else:
                    # Run a single task
                    task = " ".join(sys.argv[1:])
                    response = await orchestrator.run_single_task(task)
                    print(f"\n{'='*60}")
                    print("Sarah's Response:")
                    print("=" * 60)
                    print(response)
            else:
                # Default: run one day
                await orchestrator.run_daily_cycle()

    except KeyboardInterrupt:
        logger.info("simulation_interrupted")
    except Exception as e:
        logger.exception("simulation_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
