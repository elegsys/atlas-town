"""Base agent class defining the interface for all AI agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


class AgentState(str, Enum):
    """Possible states for an agent."""

    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"
    ERROR = "error"


@dataclass
class AgentMessage:
    """A message in the agent's conversation history."""

    role: str  # "user", "assistant", or "tool_result"
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentAction:
    """An action taken by an agent."""

    agent_id: UUID
    action_type: str  # "tool_call", "message", "complete"
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentObservation:
    """An observation/result from an action."""

    action_id: UUID
    success: bool
    result: Any = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseAgent(ABC):
    """Abstract base class for all AI agents in the simulation.

    Implements the Think-Act-Observe loop pattern:
    1. Think: Agent reasons about current state and decides what to do
    2. Act: Agent executes a tool call or sends a message
    3. Observe: Agent receives the result and updates its state

    Subclasses must implement:
    - _get_system_prompt(): Returns the agent's persona and instructions
    - _get_tools(): Returns the list of tools available to this agent
    """

    def __init__(
        self,
        agent_id: UUID | None = None,
        name: str = "Agent",
        description: str = "",
    ):
        self.id = agent_id or uuid4()
        self.name = name
        self.description = description
        self.state = AgentState.IDLE
        self._conversation_history: list[AgentMessage] = []
        self._action_history: list[AgentAction] = []
        self._current_org_id: UUID | None = None

        self._logger = logger.bind(agent_id=str(self.id), agent_name=self.name)

    @property
    def conversation_history(self) -> list[AgentMessage]:
        """Get the agent's conversation history."""
        return self._conversation_history.copy()

    @property
    def action_history(self) -> list[AgentAction]:
        """Get the agent's action history."""
        return self._action_history.copy()

    @property
    def current_org_id(self) -> UUID | None:
        """Get the current organization context."""
        return self._current_org_id

    def set_organization(self, org_id: UUID) -> None:
        """Set the organization context for this agent."""
        self._current_org_id = org_id
        self._logger.info("organization_set", org_id=str(org_id))

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Get the system prompt defining this agent's persona and behavior.

        Returns:
            The system prompt string.
        """
        pass

    @abstractmethod
    def _get_tools(self) -> list[dict[str, Any]]:
        """Get the list of tools available to this agent.

        Returns:
            List of tool definitions in the LLM provider's format.
        """
        pass

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history."""
        message = AgentMessage(role="user", content=content)
        self._conversation_history.append(message)
        self._logger.debug("user_message_added", content_length=len(content))

    def add_assistant_message(
        self, content: str, tool_calls: list[dict[str, Any]] | None = None
    ) -> None:
        """Add an assistant message to the conversation history."""
        message = AgentMessage(
            role="assistant",
            content=content,
            tool_calls=tool_calls or [],
        )
        self._conversation_history.append(message)
        self._logger.debug(
            "assistant_message_added",
            content_length=len(content),
            tool_calls=len(tool_calls or []),
        )

    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        """Add a tool result to the conversation history."""
        message = AgentMessage(
            role="tool_result",
            content=result,
            tool_call_id=tool_call_id,
        )
        self._conversation_history.append(message)
        self._logger.debug("tool_result_added", tool_call_id=tool_call_id)

    def record_action(self, action: AgentAction) -> None:
        """Record an action taken by this agent."""
        self._action_history.append(action)
        self._logger.info(
            "action_recorded",
            action_type=action.action_type,
            tool_name=action.tool_name,
        )

    def clear_history(self) -> None:
        """Clear conversation and action history."""
        self._conversation_history.clear()
        self._action_history.clear()
        self._logger.debug("history_cleared")

    def get_context_summary(self) -> dict[str, Any]:
        """Get a summary of the agent's current context.

        Returns:
            Dictionary with agent state and context information.
        """
        return {
            "agent_id": str(self.id),
            "name": self.name,
            "state": self.state.value,
            "current_org_id": str(self._current_org_id) if self._current_org_id else None,
            "message_count": len(self._conversation_history),
            "action_count": len(self._action_history),
        }

    async def think(self, prompt: str) -> AgentAction:
        """Process a prompt and decide on an action.

        This is the main entry point for agent reasoning. Subclasses
        can override this to customize the thinking process.

        Args:
            prompt: The input prompt to process.

        Returns:
            The action the agent decided to take.
        """
        self.state = AgentState.THINKING
        self._logger.info("thinking_started", prompt_length=len(prompt))

        # Add the prompt as a user message
        self.add_user_message(prompt)

        # Subclasses implement the actual LLM call
        action = await self._generate_response()

        self.record_action(action)
        return action

    @abstractmethod
    async def _generate_response(self) -> AgentAction:
        """Generate a response using the LLM.

        Must be implemented by subclasses to call their specific LLM provider.

        Returns:
            The action decided by the agent.
        """
        pass

    async def observe(self, observation: AgentObservation) -> None:
        """Process an observation from a previous action.

        Args:
            observation: The result of the previous action.
        """
        self._logger.info(
            "observation_received",
            success=observation.success,
            has_error=observation.error is not None,
        )

        # If there was a tool call, add the result to history
        if observation.result is not None:
            result_str = (
                str(observation.result)
                if not isinstance(observation.result, str)
                else observation.result
            )
            # Find the most recent tool call to get its ID
            for msg in reversed(self._conversation_history):
                if msg.role == "assistant" and msg.tool_calls:
                    tool_call_id = msg.tool_calls[-1].get("id", "unknown")
                    self.add_tool_result(tool_call_id, result_str)
                    break

        self.state = AgentState.IDLE

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name}, state={self.state.value})"
