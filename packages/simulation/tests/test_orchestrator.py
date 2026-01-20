"""Tests for the Orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from atlas_town.orchestrator import Orchestrator, Organization, SimulationPhase, SimulationState


class TestSimulationState:
    """Tests for SimulationState dataclass."""

    def test_default_state(self):
        """Test default simulation state."""
        state = SimulationState()

        assert state.day == 1
        assert state.phase == SimulationPhase.MORNING
        assert state.current_org_index == 0
        assert state.is_running is False
        assert state.is_paused is False
        assert state.started_at is None
        assert state.events == []


class TestOrganization:
    """Tests for Organization dataclass."""

    def test_organization_creation(self):
        """Test organization creation."""
        org_id = uuid4()
        org = Organization(
            id=org_id,
            name="Test Corp",
            industry="consulting",
            owner_name="John Doe",
        )

        assert org.id == org_id
        assert org.name == "Test Corp"
        assert org.industry == "consulting"
        assert org.owner_name == "John Doe"


class TestSimulationPhase:
    """Tests for SimulationPhase enum."""

    def test_phase_values(self):
        """Test phase enum values."""
        assert SimulationPhase.MORNING.value == "morning"
        assert SimulationPhase.DAYTIME.value == "daytime"
        assert SimulationPhase.EVENING.value == "evening"
        assert SimulationPhase.NIGHT.value == "night"


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_orchestrator_initial_state(self):
        """Test orchestrator starts with correct initial state."""
        orch = Orchestrator()

        assert orch._api_client is None
        assert orch._accountant is None
        assert orch._state.day == 1
        assert orch._state.is_running is False
        assert orch._organizations == []

    def test_state_property(self):
        """Test state property returns simulation state."""
        orch = Orchestrator()

        state = orch.state
        assert isinstance(state, SimulationState)
        assert state.day == 1

    def test_organizations_property_returns_copy(self):
        """Test organizations property returns a copy."""
        orch = Orchestrator()
        orch._organizations = [
            Organization(uuid4(), "Test", "consulting", "Owner")
        ]

        orgs = orch.organizations
        assert len(orgs) == 1

        # Modifying returned list shouldn't affect internal list
        orgs.clear()
        assert len(orch._organizations) == 1

    def test_emit_event(self):
        """Test event emission."""
        orch = Orchestrator()

        orch._emit_event("test_event", {"key": "value"})

        assert len(orch._state.events) == 1
        event = orch._state.events[0]
        assert event["type"] == "test_event"
        assert event["data"]["key"] == "value"
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_initialize_creates_components(self):
        """Test that initialize creates API client and agents."""
        orch = Orchestrator()

        with patch("atlas_town.orchestrator.AtlasAPIClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.login = AsyncMock(return_value={})
            mock_client.organizations = [
                {"id": str(uuid4()), "name": "Test Org"}
            ]
            mock_client.switch_organization = AsyncMock()
            MockClient.return_value = mock_client

            await orch.initialize()

            assert orch._api_client is not None
            assert orch._tool_executor is not None
            assert orch._accountant is not None
            mock_client.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self):
        """Test that shutdown closes API client."""
        orch = Orchestrator()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        orch._api_client = mock_client

        await orch.shutdown()

        mock_client.close.assert_called_once()
        assert orch._state.is_running is False

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test orchestrator as async context manager."""
        with patch("atlas_town.orchestrator.AtlasAPIClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.login = AsyncMock(return_value={})
            mock_client.organizations = []
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            async with Orchestrator() as orch:
                assert orch._api_client is not None

            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_organization(self):
        """Test switching organization context."""
        orch = Orchestrator()

        # Set up mock client
        mock_client = AsyncMock()
        mock_client.switch_organization = AsyncMock()
        orch._api_client = mock_client

        # Set up organizations
        org_id = uuid4()
        orch._organizations = [
            Organization(org_id, "Test Org", "consulting", "Owner")
        ]

        # Set up mock accountant
        mock_accountant = MagicMock()
        orch._accountant = mock_accountant

        await orch.switch_organization(org_id)

        mock_client.switch_organization.assert_called_once_with(org_id)
        mock_accountant.set_organization.assert_called_once_with(org_id)
        assert len(orch._state.events) == 1
        assert orch._state.events[0]["type"] == "organization_switched"

    @pytest.mark.asyncio
    async def test_run_single_task_without_initialization_raises(self):
        """Test that run_single_task raises if not initialized."""
        orch = Orchestrator()

        with pytest.raises(RuntimeError, match="not initialized"):
            await orch.run_single_task("Do something")

    @pytest.mark.asyncio
    async def test_run_single_task_calls_accountant(self):
        """Test that run_single_task delegates to accountant."""
        orch = Orchestrator()

        mock_accountant = MagicMock()
        mock_accountant.run_task = AsyncMock(return_value="Task completed")
        orch._accountant = mock_accountant

        result = await orch.run_single_task("Create an invoice")

        mock_accountant.run_task.assert_called_once_with("Create an invoice")
        assert result == "Task completed"

        # Should emit events
        assert len(orch._state.events) == 2
        assert orch._state.events[0]["type"] == "task_started"
        assert orch._state.events[1]["type"] == "task_completed"

    @pytest.mark.asyncio
    async def test_run_daily_cycle_updates_state(self):
        """Test that run_daily_cycle updates simulation state."""
        orch = Orchestrator()
        orch._organizations = []  # Empty orgs for faster test

        mock_accountant = MagicMock()
        mock_accountant.run_task = AsyncMock(return_value="Done")
        mock_accountant.clear_history = MagicMock()
        orch._accountant = mock_accountant

        mock_client = AsyncMock()
        mock_client.switch_organization = AsyncMock()
        orch._api_client = mock_client

        initial_day = orch._state.day

        await orch.run_daily_cycle()

        # Day should have incremented
        assert orch._state.day == initial_day + 1

        # Should have emitted day_started and day_completed events
        event_types = [e["type"] for e in orch._state.events]
        assert "day_started" in event_types
        assert "day_completed" in event_types

        # History should be cleared for new day
        mock_accountant.clear_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_phases_cycle_correctly(self):
        """Test that daily cycle goes through all phases."""
        orch = Orchestrator()
        orch._organizations = []

        mock_accountant = MagicMock()
        mock_accountant.run_task = AsyncMock(return_value="Done")
        mock_accountant.clear_history = MagicMock()
        orch._accountant = mock_accountant

        mock_client = AsyncMock()
        orch._api_client = mock_client

        phases_seen = []

        original_emit = orch._emit_event

        def capture_phase(event_type, data):
            if event_type == "phase_changed":
                phases_seen.append(data["phase"])
            original_emit(event_type, data)

        orch._emit_event = capture_phase

        await orch.run_daily_cycle()

        assert phases_seen == ["morning", "daytime", "evening", "night"]
