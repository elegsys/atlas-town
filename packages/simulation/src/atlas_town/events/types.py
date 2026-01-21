"""Event type definitions for WebSocket publishing.

These events are published to connected frontend clients to drive
real-time visualization of the simulation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EventType(str, Enum):
    """Types of events published by the simulation."""

    # Simulation lifecycle
    SIMULATION_STARTED = "simulation.started"
    SIMULATION_STOPPED = "simulation.stopped"
    SIMULATION_PAUSED = "simulation.paused"
    SIMULATION_RESUMED = "simulation.resumed"

    # Day/Phase transitions
    DAY_STARTED = "day.started"
    DAY_COMPLETED = "day.completed"
    PHASE_STARTED = "phase.started"
    PHASE_COMPLETED = "phase.completed"

    # Agent activity
    AGENT_THINKING = "agent.thinking"
    AGENT_ACTING = "agent.acting"
    AGENT_IDLE = "agent.idle"
    AGENT_SPEAKING = "agent.speaking"
    AGENT_MOVING = "agent.moving"

    # Tool execution
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # Business transactions
    TRANSACTION_CREATED = "transaction.created"
    INVOICE_CREATED = "invoice.created"
    BILL_CREATED = "bill.created"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_SENT = "payment.sent"

    # Organization context
    ORG_SWITCHED = "org.switched"
    ORG_VISITED = "org.visited"

    # Errors
    ERROR = "error"


@dataclass
class SimulationEvent:
    """Base event structure for all simulation events."""

    event_type: EventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: UUID = field(default_factory=uuid4)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary for JSON transmission."""
        return {
            "id": str(self.event_id),
            "type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


@dataclass
class AgentEvent(SimulationEvent):
    """Event related to agent activity."""

    agent_id: UUID | None = None
    agent_name: str = ""
    org_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["agent"] = {
            "id": str(self.agent_id) if self.agent_id else None,
            "name": self.agent_name,
            "org_id": str(self.org_id) if self.org_id else None,
        }
        return base


@dataclass
class PhaseEvent(SimulationEvent):
    """Event for phase transitions."""

    day: int = 1
    phase: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["phase"] = {
            "day": self.day,
            "name": self.phase,
            "description": self.description,
        }
        return base


@dataclass
class ToolEvent(SimulationEvent):
    """Event for tool execution."""

    agent_id: UUID | None = None
    agent_name: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["tool"] = {
            "name": self.tool_name,
            "args": self.tool_args,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
        base["agent"] = {
            "id": str(self.agent_id) if self.agent_id else None,
            "name": self.agent_name,
        }
        return base


@dataclass
class TransactionEvent(SimulationEvent):
    """Event for business transactions."""

    org_id: UUID | None = None
    org_name: str = ""
    transaction_type: str = ""  # invoice, bill, payment, journal
    amount: float = 0.0
    counterparty: str = ""  # customer or vendor name
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["transaction"] = {
            "type": self.transaction_type,
            "amount": self.amount,
            "counterparty": self.counterparty,
            "description": self.description,
        }
        base["org"] = {
            "id": str(self.org_id) if self.org_id else None,
            "name": self.org_name,
        }
        return base


@dataclass
class MovementEvent(SimulationEvent):
    """Event for agent movement in the town visualization."""

    agent_id: UUID | None = None
    agent_name: str = ""
    from_location: str = ""  # building name or "street"
    to_location: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["movement"] = {
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "agent_name": self.agent_name,
            "from": self.from_location,
            "to": self.to_location,
            "reason": self.reason,
        }
        return base


# Factory functions for creating events


def simulation_started(speed: float = 1.0, max_days: int | None = None) -> SimulationEvent:
    """Create a simulation started event."""
    return SimulationEvent(
        event_type=EventType.SIMULATION_STARTED,
        data={"speed": speed, "max_days": max_days},
    )


def simulation_stopped(days_completed: int, reason: str = "completed") -> SimulationEvent:
    """Create a simulation stopped event."""
    return SimulationEvent(
        event_type=EventType.SIMULATION_STOPPED,
        data={"days_completed": days_completed, "reason": reason},
    )


def day_started(day: int) -> PhaseEvent:
    """Create a day started event."""
    return PhaseEvent(
        event_type=EventType.DAY_STARTED,
        day=day,
        phase="start",
        description=f"Day {day} begins",
    )


def day_completed(day: int, summary: dict[str, Any] | None = None) -> PhaseEvent:
    """Create a day completed event."""
    return PhaseEvent(
        event_type=EventType.DAY_COMPLETED,
        day=day,
        phase="end",
        description=f"Day {day} completed",
        data={"summary": summary or {}},
    )


def phase_started(day: int, phase: str, description: str = "") -> PhaseEvent:
    """Create a phase started event."""
    return PhaseEvent(
        event_type=EventType.PHASE_STARTED,
        day=day,
        phase=phase,
        description=description,
    )


def phase_completed(day: int, phase: str, results: list[Any] | None = None) -> PhaseEvent:
    """Create a phase completed event."""
    return PhaseEvent(
        event_type=EventType.PHASE_COMPLETED,
        day=day,
        phase=phase,
        data={"results_count": len(results) if results else 0},
    )


def agent_thinking(
    agent_id: UUID, agent_name: str, prompt: str, org_id: UUID | None = None
) -> AgentEvent:
    """Create an agent thinking event."""
    return AgentEvent(
        event_type=EventType.AGENT_THINKING,
        agent_id=agent_id,
        agent_name=agent_name,
        org_id=org_id,
        data={"prompt_preview": prompt[:200] if prompt else ""},
    )


def agent_speaking(
    agent_id: UUID, agent_name: str, message: str, org_id: UUID | None = None
) -> AgentEvent:
    """Create an agent speaking event (for thought bubbles)."""
    return AgentEvent(
        event_type=EventType.AGENT_SPEAKING,
        agent_id=agent_id,
        agent_name=agent_name,
        org_id=org_id,
        data={"message": message[:500] if message else ""},
    )


def agent_moving(
    agent_id: UUID,
    agent_name: str,
    from_location: str,
    to_location: str,
    reason: str = "",
) -> MovementEvent:
    """Create an agent movement event."""
    return MovementEvent(
        event_type=EventType.AGENT_MOVING,
        agent_id=agent_id,
        agent_name=agent_name,
        from_location=from_location,
        to_location=to_location,
        reason=reason,
    )


def tool_called(
    agent_id: UUID,
    agent_name: str,
    tool_name: str,
    tool_args: dict[str, Any],
) -> ToolEvent:
    """Create a tool called event."""
    return ToolEvent(
        event_type=EventType.TOOL_CALLED,
        agent_id=agent_id,
        agent_name=agent_name,
        tool_name=tool_name,
        tool_args=tool_args,
    )


def tool_completed(
    agent_id: UUID,
    agent_name: str,
    tool_name: str,
    result: Any,
    duration_ms: float,
) -> ToolEvent:
    """Create a tool completed event."""
    return ToolEvent(
        event_type=EventType.TOOL_COMPLETED,
        agent_id=agent_id,
        agent_name=agent_name,
        tool_name=tool_name,
        result=str(result)[:500] if result else None,
        duration_ms=duration_ms,
    )


def tool_failed(
    agent_id: UUID,
    agent_name: str,
    tool_name: str,
    error: str,
    duration_ms: float,
) -> ToolEvent:
    """Create a tool failed event."""
    return ToolEvent(
        event_type=EventType.TOOL_FAILED,
        agent_id=agent_id,
        agent_name=agent_name,
        tool_name=tool_name,
        error=error,
        duration_ms=duration_ms,
    )


def transaction_created(
    org_id: UUID,
    org_name: str,
    transaction_type: str,
    amount: float,
    counterparty: str,
    description: str = "",
) -> TransactionEvent:
    """Create a transaction event."""
    event_type_map = {
        "invoice": EventType.INVOICE_CREATED,
        "bill": EventType.BILL_CREATED,
        "payment_received": EventType.PAYMENT_RECEIVED,
        "payment_sent": EventType.PAYMENT_SENT,
    }
    return TransactionEvent(
        event_type=event_type_map.get(transaction_type, EventType.TRANSACTION_CREATED),
        org_id=org_id,
        org_name=org_name,
        transaction_type=transaction_type,
        amount=amount,
        counterparty=counterparty,
        description=description,
    )


def org_visited(
    agent_id: UUID,
    agent_name: str,
    org_id: UUID,
    org_name: str,
) -> AgentEvent:
    """Create an organization visited event."""
    return AgentEvent(
        event_type=EventType.ORG_VISITED,
        agent_id=agent_id,
        agent_name=agent_name,
        org_id=org_id,
        data={"org_name": org_name},
    )


def error_event(message: str, details: dict[str, Any] | None = None) -> SimulationEvent:
    """Create an error event."""
    return SimulationEvent(
        event_type=EventType.ERROR,
        data={"message": message, "details": details or {}},
    )
