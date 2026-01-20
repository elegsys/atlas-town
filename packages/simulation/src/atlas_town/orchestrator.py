"""Orchestrator - coordinates agents and simulation lifecycle."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from atlas_town.agents import AccountantAgent, AgentState
from atlas_town.clients.claude import ClaudeClient
from atlas_town.config import get_settings
from atlas_town.tools import AtlasAPIClient, ToolExecutor

logger = structlog.get_logger(__name__)


class SimulationPhase(str, Enum):
    """Phases of the daily simulation cycle."""

    MORNING = "morning"      # Owners review, plan day
    DAYTIME = "daytime"      # Business operations, transactions
    EVENING = "evening"      # Sarah reconciles, reports
    NIGHT = "night"          # System maintenance, day transition


@dataclass
class Organization:
    """Represents a business in Atlas Town."""

    id: UUID
    name: str
    industry: str
    owner_name: str


@dataclass
class SimulationState:
    """Current state of the simulation."""

    day: int = 1
    phase: SimulationPhase = SimulationPhase.MORNING
    current_org_index: int = 0
    is_running: bool = False
    is_paused: bool = False
    started_at: datetime | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


class Orchestrator:
    """Main coordinator for the Atlas Town simulation.

    The orchestrator:
    1. Manages the Atlas API connection
    2. Coordinates agent activities
    3. Tracks simulation state (day, phase, events)
    4. Publishes events for the frontend

    Usage:
        async with Orchestrator() as orch:
            await orch.run_single_task("Create an invoice for customer X")
    """

    def __init__(self):
        settings = get_settings()

        # API client and tools
        self._api_client: AtlasAPIClient | None = None
        self._tool_executor: ToolExecutor | None = None

        # Agents
        self._accountant: AccountantAgent | None = None

        # State
        self._state = SimulationState()
        self._organizations: list[Organization] = []

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
        """Initialize API client, tools, and agents."""
        self._logger.info("initializing_orchestrator")

        # Create and authenticate API client
        self._api_client = AtlasAPIClient()
        await self._api_client.login()

        # Create tool executor
        self._tool_executor = ToolExecutor(self._api_client)

        # Load organizations
        await self._load_organizations()

        # Create agents
        self._accountant = AccountantAgent()
        self._accountant.set_tool_executor(self._tool_executor)

        # Set initial organization context if available
        if self._organizations:
            org = self._organizations[0]
            self._accountant.set_organization(org.id)
            await self._api_client.switch_organization(org.id)

        self._logger.info(
            "orchestrator_initialized",
            org_count=len(self._organizations),
        )

    async def shutdown(self) -> None:
        """Cleanup and shutdown."""
        self._logger.info("shutting_down_orchestrator")
        self._state.is_running = False

        if self._api_client:
            await self._api_client.close()

    async def _load_organizations(self) -> None:
        """Load available organizations from the API client."""
        if not self._api_client:
            return

        # Get organizations from the login response
        for org_data in self._api_client.organizations:
            org = Organization(
                id=UUID(org_data["id"]),
                name=org_data.get("name", "Unknown"),
                industry=org_data.get("industry", "general"),
                owner_name=org_data.get("owner_name", "Owner"),
            )
            self._organizations.append(org)

        self._logger.info("organizations_loaded", count=len(self._organizations))

    @property
    def state(self) -> SimulationState:
        """Get current simulation state."""
        return self._state

    @property
    def organizations(self) -> list[Organization]:
        """Get list of organizations."""
        return self._organizations.copy()

    @property
    def accountant(self) -> AccountantAgent | None:
        """Get the accountant agent."""
        return self._accountant

    def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event for the frontend."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._state.events.append(event)
        self._logger.debug("event_emitted", event_type=event_type)

    async def switch_organization(self, org_id: UUID) -> None:
        """Switch to a different organization context."""
        if not self._api_client:
            raise RuntimeError("Orchestrator not initialized")

        await self._api_client.switch_organization(org_id)

        if self._accountant:
            self._accountant.set_organization(org_id)

        # Find the org index
        for i, org in enumerate(self._organizations):
            if org.id == org_id:
                self._state.current_org_index = i
                break

        self._emit_event("organization_switched", {
            "org_id": str(org_id),
            "org_name": self._organizations[self._state.current_org_index].name,
        })

        self._logger.info("organization_switched", org_id=str(org_id))

    async def run_single_task(self, task: str) -> str:
        """Run a single task using the accountant agent.

        This is the simplest way to interact with the simulation.
        The accountant will process the task and return a response.

        Args:
            task: The task description (e.g., "Create an invoice for...")

        Returns:
            The agent's final response.
        """
        if not self._accountant:
            raise RuntimeError("Orchestrator not initialized")

        self._emit_event("task_started", {"task": task[:100]})

        self._logger.info("running_task", task=task[:100])

        response = await self._accountant.run_task(task)

        self._emit_event("task_completed", {
            "task": task[:100],
            "response": response[:200] if response else "",
        })

        return response

    async def run_daily_cycle(self) -> None:
        """Run a complete daily simulation cycle.

        This cycles through all phases:
        1. Morning: Review and planning
        2. Daytime: Business operations
        3. Evening: Reconciliation and reports
        4. Night: Day transition
        """
        self._state.is_running = True
        self._state.started_at = datetime.now(timezone.utc)

        self._logger.info("daily_cycle_started", day=self._state.day)
        self._emit_event("day_started", {"day": self._state.day})

        try:
            # Morning phase
            await self._run_morning_phase()

            # Daytime phase
            await self._run_daytime_phase()

            # Evening phase
            await self._run_evening_phase()

            # Night phase (transition)
            await self._run_night_phase()

        except Exception as e:
            self._logger.exception("daily_cycle_error", error=str(e))
            self._emit_event("error", {"message": str(e)})
            raise

        finally:
            self._state.is_running = False

        self._logger.info("daily_cycle_completed", day=self._state.day)
        self._emit_event("day_completed", {"day": self._state.day})

    async def _run_morning_phase(self) -> None:
        """Morning phase: Review previous day, plan current day."""
        self._state.phase = SimulationPhase.MORNING
        self._emit_event("phase_changed", {"phase": "morning"})
        self._logger.info("morning_phase_started")

        # Sarah reviews each organization
        for org in self._organizations:
            await self.switch_organization(org.id)

            # Check AR aging
            task = f"""Good morning! Please review the financial status for {org.name}.
            Check the AR aging report and identify any overdue invoices.
            Provide a brief summary of the accounts receivable situation."""

            await self.run_single_task(task)

        self._logger.info("morning_phase_completed")

    async def _run_daytime_phase(self) -> None:
        """Daytime phase: Process transactions and business operations."""
        self._state.phase = SimulationPhase.DAYTIME
        self._emit_event("phase_changed", {"phase": "daytime"})
        self._logger.info("daytime_phase_started")

        # In a full simulation, this is where customer/vendor agents
        # would generate transactions. For now, we just process
        # any pending items.

        for org in self._organizations:
            await self.switch_organization(org.id)

            task = f"""Process any pending transactions for {org.name}.
            Check for:
            1. Any bills that need to be approved
            2. Any payments that need to be applied
            3. Any bank transactions that need categorization

            Take appropriate actions for each item found."""

            await self.run_single_task(task)

        self._logger.info("daytime_phase_completed")

    async def _run_evening_phase(self) -> None:
        """Evening phase: Reconciliation and reporting."""
        self._state.phase = SimulationPhase.EVENING
        self._emit_event("phase_changed", {"phase": "evening"})
        self._logger.info("evening_phase_started")

        for org in self._organizations:
            await self.switch_organization(org.id)

            task = f"""End of day for {org.name}. Please:
            1. Run a trial balance to ensure books are balanced
            2. Provide a quick summary of today's activity
            3. Note any issues that need attention tomorrow"""

            await self.run_single_task(task)

        self._logger.info("evening_phase_completed")

    async def _run_night_phase(self) -> None:
        """Night phase: Day transition and cleanup."""
        self._state.phase = SimulationPhase.NIGHT
        self._emit_event("phase_changed", {"phase": "night"})
        self._logger.info("night_phase_started")

        # Increment day counter
        self._state.day += 1

        # Clear agent histories for the new day
        if self._accountant:
            self._accountant.clear_history()

        self._logger.info("night_phase_completed", next_day=self._state.day)


async def main() -> None:
    """Main entry point for running the simulation."""
    import sys

    # Configure logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger.info("starting_atlas_town_simulation")

    try:
        async with Orchestrator() as orchestrator:
            # For testing, run a single task
            if len(sys.argv) > 1:
                task = " ".join(sys.argv[1:])
            else:
                task = "Please list all customers and provide a summary of their balances."

            response = await orchestrator.run_single_task(task)
            print(f"\n{'='*60}")
            print("Sarah's Response:")
            print('='*60)
            print(response)

    except Exception as e:
        logger.exception("simulation_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
