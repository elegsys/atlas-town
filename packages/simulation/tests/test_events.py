"""Tests for the event system."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from atlas_town.events import (
    EventPublisher,
    EventType,
    SimulationEvent,
    agent_moving,
    agent_speaking,
    agent_thinking,
    day_completed,
    day_started,
    error_event,
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
from atlas_town.events.types import (
    AgentEvent,
    MovementEvent,
    PhaseEvent,
    ToolEvent,
    TransactionEvent,
)


class TestEventTypes:
    """Tests for event type definitions."""

    def test_event_type_values(self):
        """Test that all event types have correct values."""
        assert EventType.SIMULATION_STARTED.value == "simulation.started"
        assert EventType.DAY_STARTED.value == "day.started"
        assert EventType.AGENT_THINKING.value == "agent.thinking"
        assert EventType.TOOL_CALLED.value == "tool.called"
        assert EventType.INVOICE_CREATED.value == "invoice.created"

    def test_simulation_event_to_dict(self):
        """Test basic event serialization."""
        event = SimulationEvent(
            event_type=EventType.SIMULATION_STARTED,
            data={"speed": 2.0},
        )

        result = event.to_dict()

        assert result["type"] == "simulation.started"
        assert result["data"]["speed"] == 2.0
        assert "id" in result
        assert "timestamp" in result

    def test_agent_event_to_dict(self):
        """Test agent event serialization."""
        agent_id = uuid4()
        org_id = uuid4()

        event = AgentEvent(
            event_type=EventType.AGENT_THINKING,
            agent_id=agent_id,
            agent_name="Sarah Chen",
            org_id=org_id,
            data={"prompt_preview": "Review financials"},
        )

        result = event.to_dict()

        assert result["type"] == "agent.thinking"
        assert result["agent"]["id"] == str(agent_id)
        assert result["agent"]["name"] == "Sarah Chen"
        assert result["agent"]["org_id"] == str(org_id)

    def test_phase_event_to_dict(self):
        """Test phase event serialization."""
        event = PhaseEvent(
            event_type=EventType.PHASE_STARTED,
            day=5,
            phase="morning",
            description="Morning business activity",
        )

        result = event.to_dict()

        assert result["type"] == "phase.started"
        assert result["phase"]["day"] == 5
        assert result["phase"]["name"] == "morning"
        assert result["phase"]["description"] == "Morning business activity"

    def test_tool_event_to_dict(self):
        """Test tool event serialization."""
        agent_id = uuid4()

        event = ToolEvent(
            event_type=EventType.TOOL_COMPLETED,
            agent_id=agent_id,
            agent_name="Sarah Chen",
            tool_name="list_customers",
            result="Found 10 customers",
            duration_ms=150.5,
        )

        result = event.to_dict()

        assert result["type"] == "tool.completed"
        assert result["tool"]["name"] == "list_customers"
        assert result["tool"]["result"] == "Found 10 customers"
        assert result["tool"]["duration_ms"] == 150.5
        assert result["agent"]["name"] == "Sarah Chen"

    def test_transaction_event_to_dict(self):
        """Test transaction event serialization."""
        org_id = uuid4()

        event = TransactionEvent(
            event_type=EventType.INVOICE_CREATED,
            org_id=org_id,
            org_name="Craig's Landscaping",
            transaction_type="invoice",
            amount=1500.00,
            counterparty="Smith Residence",
            description="Lawn maintenance - March",
        )

        result = event.to_dict()

        assert result["type"] == "invoice.created"
        assert result["transaction"]["type"] == "invoice"
        assert result["transaction"]["amount"] == 1500.00
        assert result["transaction"]["counterparty"] == "Smith Residence"
        assert result["org"]["name"] == "Craig's Landscaping"

    def test_movement_event_to_dict(self):
        """Test movement event serialization."""
        agent_id = uuid4()

        event = MovementEvent(
            event_type=EventType.AGENT_MOVING,
            agent_id=agent_id,
            agent_name="Sarah Chen",
            from_location="Craig's Landscaping",
            to_location="Tony's Pizzeria",
            reason="Visiting for accounting duties",
        )

        result = event.to_dict()

        assert result["type"] == "agent.moving"
        assert result["movement"]["from"] == "Craig's Landscaping"
        assert result["movement"]["to"] == "Tony's Pizzeria"
        assert result["movement"]["reason"] == "Visiting for accounting duties"


class TestEventFactories:
    """Tests for event factory functions."""

    def test_simulation_started(self):
        """Test simulation_started factory."""
        event = simulation_started(speed=5.0, max_days=30)

        assert event.event_type == EventType.SIMULATION_STARTED
        assert event.data["speed"] == 5.0
        assert event.data["max_days"] == 30

    def test_simulation_stopped(self):
        """Test simulation_stopped factory."""
        event = simulation_stopped(days_completed=15, reason="user_stopped")

        assert event.event_type == EventType.SIMULATION_STOPPED
        assert event.data["days_completed"] == 15
        assert event.data["reason"] == "user_stopped"

    def test_day_started(self):
        """Test day_started factory."""
        event = day_started(day=3)

        assert event.event_type == EventType.DAY_STARTED
        assert event.day == 3
        assert event.phase == "start"

    def test_day_completed(self):
        """Test day_completed factory."""
        event = day_completed(day=3, summary={"transactions": 15})

        assert event.event_type == EventType.DAY_COMPLETED
        assert event.day == 3
        assert event.data["summary"]["transactions"] == 15

    def test_phase_started(self):
        """Test phase_started factory."""
        event = phase_started(day=2, phase="afternoon", description="Peak activity")

        assert event.event_type == EventType.PHASE_STARTED
        assert event.day == 2
        assert event.phase == "afternoon"
        assert event.description == "Peak activity"

    def test_phase_completed(self):
        """Test phase_completed factory."""
        event = phase_completed(day=2, phase="morning", results=[1, 2, 3])

        assert event.event_type == EventType.PHASE_COMPLETED
        assert event.day == 2
        assert event.data["results_count"] == 3

    def test_agent_thinking(self):
        """Test agent_thinking factory."""
        agent_id = uuid4()
        org_id = uuid4()

        event = agent_thinking(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            prompt="Review AR aging",
            org_id=org_id,
        )

        assert event.event_type == EventType.AGENT_THINKING
        assert event.agent_id == agent_id
        assert event.agent_name == "Sarah Chen"
        assert "Review AR" in event.data["prompt_preview"]

    def test_agent_speaking(self):
        """Test agent_speaking factory."""
        agent_id = uuid4()

        event = agent_speaking(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            message="The books are balanced.",
        )

        assert event.event_type == EventType.AGENT_SPEAKING
        assert event.data["message"] == "The books are balanced."

    def test_agent_moving(self):
        """Test agent_moving factory."""
        agent_id = uuid4()

        event = agent_moving(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            from_location="Office",
            to_location="Craig's Landscaping",
            reason="Morning review",
        )

        assert event.event_type == EventType.AGENT_MOVING
        assert event.from_location == "Office"
        assert event.to_location == "Craig's Landscaping"

    def test_tool_called(self):
        """Test tool_called factory."""
        agent_id = uuid4()

        event = tool_called(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            tool_name="create_invoice",
            tool_args={"customer_id": "123", "amount": 500},
        )

        assert event.event_type == EventType.TOOL_CALLED
        assert event.tool_name == "create_invoice"
        assert event.tool_args["amount"] == 500

    def test_tool_completed(self):
        """Test tool_completed factory."""
        agent_id = uuid4()

        event = tool_completed(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            tool_name="create_invoice",
            result={"id": "inv-123"},
            duration_ms=200.0,
        )

        assert event.event_type == EventType.TOOL_COMPLETED
        assert event.duration_ms == 200.0

    def test_tool_failed(self):
        """Test tool_failed factory."""
        agent_id = uuid4()

        event = tool_failed(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            tool_name="create_invoice",
            error="Customer not found",
            duration_ms=50.0,
        )

        assert event.event_type == EventType.TOOL_FAILED
        assert event.error == "Customer not found"

    def test_transaction_created_invoice(self):
        """Test transaction_created factory for invoice."""
        org_id = uuid4()

        event = transaction_created(
            org_id=org_id,
            org_name="Tony's Pizzeria",
            transaction_type="invoice",
            amount=150.00,
            counterparty="Catering Client",
            description="Wedding catering",
        )

        assert event.event_type == EventType.INVOICE_CREATED
        assert event.amount == 150.00

    def test_transaction_created_bill(self):
        """Test transaction_created factory for bill."""
        org_id = uuid4()

        event = transaction_created(
            org_id=org_id,
            org_name="Craig's Landscaping",
            transaction_type="bill",
            amount=500.00,
            counterparty="Equipment Supplier",
        )

        assert event.event_type == EventType.BILL_CREATED

    def test_org_visited(self):
        """Test org_visited factory."""
        agent_id = uuid4()
        org_id = uuid4()

        event = org_visited(
            agent_id=agent_id,
            agent_name="Sarah Chen",
            org_id=org_id,
            org_name="Nexus Tech",
        )

        assert event.event_type == EventType.ORG_VISITED
        assert event.data["org_name"] == "Nexus Tech"

    def test_error_event(self):
        """Test error_event factory."""
        event = error_event(
            message="Connection failed",
            details={"retry_count": 3},
        )

        assert event.event_type == EventType.ERROR
        assert event.data["message"] == "Connection failed"
        assert event.data["details"]["retry_count"] == 3


class TestEventPublisher:
    """Tests for the EventPublisher class."""

    def test_publisher_initialization(self):
        """Test publisher initializes with defaults."""
        publisher = EventPublisher()

        assert publisher.is_running is False
        assert publisher.client_count == 0
        assert publisher.recent_events == []

    def test_publisher_with_custom_settings(self):
        """Test publisher with custom host/port."""
        publisher = EventPublisher(
            host="127.0.0.1",
            port=9999,
            buffer_size=50,
        )

        assert publisher._host == "127.0.0.1"
        assert publisher._port == 9999
        assert publisher._buffer_size == 50

    def test_add_event_hook(self):
        """Test adding event hooks."""
        publisher = EventPublisher()
        hook = MagicMock()

        publisher.add_event_hook(hook)

        assert hook in publisher._event_hooks

    def test_remove_event_hook(self):
        """Test removing event hooks."""
        publisher = EventPublisher()
        hook = MagicMock()

        publisher.add_event_hook(hook)
        publisher.remove_event_hook(hook)

        assert hook not in publisher._event_hooks

    def test_publish_calls_hooks(self):
        """Test that publish calls registered hooks."""
        publisher = EventPublisher()
        hook = MagicMock()
        publisher.add_event_hook(hook)

        event = simulation_started(speed=1.0)
        publisher.publish(event)

        hook.assert_called_once_with(event)

    def test_publish_buffers_events(self):
        """Test that publish adds events to buffer."""
        publisher = EventPublisher()

        event1 = day_started(day=1)
        event2 = day_started(day=2)

        publisher.publish(event1)
        publisher.publish(event2)

        assert len(publisher.recent_events) == 2
        assert publisher.recent_events[0] == event1
        assert publisher.recent_events[1] == event2

    def test_buffer_respects_max_size(self):
        """Test that buffer respects max size."""
        publisher = EventPublisher(buffer_size=3)

        for i in range(5):
            publisher.publish(day_started(day=i + 1))

        assert len(publisher.recent_events) == 3
        # Should have days 3, 4, 5 (first two dropped)
        assert publisher.recent_events[0].day == 3
        assert publisher.recent_events[2].day == 5

    def test_get_status(self):
        """Test getting publisher status."""
        publisher = EventPublisher(host="localhost", port=8888)

        status = publisher.get_status()

        assert status["is_running"] is False
        assert status["host"] == "localhost"
        assert status["port"] == 8888
        assert status["client_count"] == 0
        assert status["buffer_size"] == 0

    def test_should_send_to_client_no_filters(self):
        """Test that clients without filters receive all events."""
        publisher = EventPublisher()

        # Create mock client with no subscriptions
        mock_ws = MagicMock()
        mock_ws.remote_address = ("127.0.0.1", 12345)

        from atlas_town.events.publisher import ClientConnection
        client = ClientConnection(websocket=mock_ws)

        event = simulation_started(speed=1.0)

        assert publisher._should_send_to_client(client, event) is True

    def test_should_send_to_client_with_event_filter(self):
        """Test event type filtering."""
        publisher = EventPublisher()

        mock_ws = MagicMock()
        mock_ws.remote_address = ("127.0.0.1", 12345)

        from atlas_town.events.publisher import ClientConnection
        client = ClientConnection(websocket=mock_ws)
        client.subscribed_events.add(EventType.SIMULATION_STARTED)

        # Should receive
        event1 = simulation_started(speed=1.0)
        assert publisher._should_send_to_client(client, event1) is True

        # Should not receive
        event2 = day_started(day=1)
        assert publisher._should_send_to_client(client, event2) is False


class TestEventPublisherAsync:
    """Async tests for EventPublisher."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping the publisher."""
        publisher = EventPublisher(host="127.0.0.1", port=18765)

        await publisher.start()
        assert publisher.is_running is True

        await publisher.stop()
        assert publisher.is_running is False

    @pytest.mark.asyncio
    async def test_start_twice_is_safe(self):
        """Test that starting twice doesn't cause issues."""
        publisher = EventPublisher(host="127.0.0.1", port=18766)

        await publisher.start()
        await publisher.start()  # Should warn but not fail

        assert publisher.is_running is True

        await publisher.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test that stopping when not running is safe."""
        publisher = EventPublisher()

        await publisher.stop()  # Should not raise

        assert publisher.is_running is False
