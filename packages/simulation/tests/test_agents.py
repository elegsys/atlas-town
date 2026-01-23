"""Tests for agent implementations."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from atlas_town.agents.accountant import AccountantAgent
from atlas_town.agents.base import AgentAction, AgentMessage, AgentState, BaseAgent


class ConcreteAgent(BaseAgent):
    """Concrete implementation for testing BaseAgent."""

    def _get_system_prompt(self) -> str:
        return "Test system prompt"

    def _get_tools(self) -> list[dict]:
        return [{"name": "test_tool", "description": "Test", "input_schema": {"type": "object"}}]

    async def _generate_response(self) -> AgentAction:
        return AgentAction(
            agent_id=self.id,
            action_type="message",
            message="Test response",
        )


class TestBaseAgent:
    """Tests for BaseAgent abstract class."""

    def test_agent_initialization(self):
        """Test agent initializes with correct defaults."""
        agent = ConcreteAgent(name="Test Agent")

        assert agent.name == "Test Agent"
        assert agent.state == AgentState.IDLE
        assert len(agent.conversation_history) == 0
        assert len(agent.action_history) == 0

    def test_agent_with_custom_id(self):
        """Test agent accepts custom UUID."""
        custom_id = uuid4()
        agent = ConcreteAgent(agent_id=custom_id, name="Test")

        assert agent.id == custom_id

    def test_add_user_message(self):
        """Test adding user message to history."""
        agent = ConcreteAgent()
        agent.add_user_message("Hello")

        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0].role == "user"
        assert agent.conversation_history[0].content == "Hello"

    def test_add_assistant_message_with_tool_calls(self):
        """Test adding assistant message with tool calls."""
        agent = ConcreteAgent()
        tool_calls = [{"id": "call_123", "name": "test_tool", "arguments": {}}]
        agent.add_assistant_message("Thinking...", tool_calls=tool_calls)

        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0].role == "assistant"
        assert agent.conversation_history[0].tool_calls == tool_calls

    def test_add_tool_result(self):
        """Test adding tool result to history."""
        agent = ConcreteAgent()
        agent.add_tool_result("call_123", '{"result": "success"}')

        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0].role == "tool_result"
        assert agent.conversation_history[0].tool_call_id == "call_123"

    def test_set_organization(self):
        """Test setting organization context."""
        agent = ConcreteAgent()
        org_id = uuid4()
        agent.set_organization(org_id)

        assert agent.current_org_id == org_id

    def test_clear_history(self):
        """Test clearing conversation history."""
        agent = ConcreteAgent()
        agent.add_user_message("Test")
        agent.add_assistant_message("Response")
        agent.clear_history()

        assert len(agent.conversation_history) == 0
        assert len(agent.action_history) == 0

    def test_get_context_summary(self):
        """Test getting agent context summary."""
        agent = ConcreteAgent(name="Test Agent")
        org_id = uuid4()
        agent.set_organization(org_id)
        agent.add_user_message("Test")

        summary = agent.get_context_summary()

        assert summary["name"] == "Test Agent"
        assert summary["state"] == "idle"
        assert summary["current_org_id"] == str(org_id)
        assert summary["message_count"] == 1

    @pytest.mark.asyncio
    async def test_think_adds_message_and_records_action(self):
        """Test that think() adds message and records action."""
        agent = ConcreteAgent()

        action = await agent.think("What should I do?")

        assert len(agent.conversation_history) == 1  # User message added
        assert len(agent.action_history) == 1  # Action recorded
        assert action.action_type == "message"


class TestAccountantAgent:
    """Tests for AccountantAgent."""

    def test_accountant_initialization(self):
        """Test accountant agent initializes correctly."""
        agent = AccountantAgent()

        assert agent.name == "Sarah Chen"
        assert "bookkeeper" in agent.description.lower()
        assert agent.state == AgentState.IDLE

    def test_accountant_system_prompt(self):
        """Test accountant has appropriate system prompt."""
        agent = AccountantAgent()
        prompt = agent._get_system_prompt()

        assert "Sarah Chen" in prompt
        assert "accountant" in prompt.lower() or "bookkeeper" in prompt.lower()
        assert "invoice" in prompt.lower()

    def test_accountant_has_accounting_tools(self):
        """Test accountant has expected tools."""
        agent = AccountantAgent()
        tools = agent._get_tools()

        tool_names = [t["name"] for t in tools]

        # Should have key accounting tools
        assert "list_customers" in tool_names
        assert "create_invoice" in tool_names
        assert "list_bills" in tool_names
        assert "create_payment" in tool_names
        assert "get_trial_balance" in tool_names

    def test_set_tool_executor(self):
        """Test setting tool executor."""
        agent = AccountantAgent()
        mock_executor = MagicMock()
        agent.set_tool_executor(mock_executor)

        assert agent._tool_executor == mock_executor

    @pytest.mark.asyncio
    async def test_execute_tool_without_executor_raises(self):
        """Test that executing tool without executor raises error."""
        agent = AccountantAgent()

        with pytest.raises(RuntimeError, match="Tool executor not set"):
            await agent.execute_tool("list_customers", {})

    @pytest.mark.asyncio
    async def test_execute_tool_calls_executor(self):
        """Test that execute_tool calls the tool executor."""
        agent = AccountantAgent()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={"success": True, "result": []})
        agent.set_tool_executor(mock_executor)

        result = await agent.execute_tool("list_customers", {"limit": 10})

        mock_executor.execute.assert_called_once_with("list_customers", {"limit": 10})
        assert result["success"] is True

    def test_format_items(self):
        """Test formatting line items for prompts."""
        agent = AccountantAgent()
        items = [
            {"description": "Consulting", "quantity": 5, "unit_price": "100.00"},
            {"description": "Support", "quantity": 2, "unit_price": "50.00"},
        ]

        formatted = agent._format_items(items)

        assert "Consulting" in formatted
        assert "Qty: 5" in formatted
        assert "$100.00" in formatted


class TestAgentDataClasses:
    """Tests for agent data classes."""

    def test_agent_message_creation(self):
        """Test AgentMessage creation."""
        msg = AgentMessage(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls == []
        assert msg.timestamp is not None

    def test_agent_action_creation(self):
        """Test AgentAction creation."""
        agent_id = uuid4()
        action = AgentAction(
            agent_id=agent_id,
            action_type="tool_call",
            tool_name="list_customers",
            tool_args={"limit": 10},
        )

        assert action.agent_id == agent_id
        assert action.action_type == "tool_call"
        assert action.tool_name == "list_customers"
        assert action.tool_args == {"limit": 10}

    def test_agent_state_values(self):
        """Test AgentState enum values."""
        assert AgentState.IDLE.value == "idle"
        assert AgentState.THINKING.value == "thinking"
        assert AgentState.ACTING.value == "acting"
        assert AgentState.WAITING.value == "waiting"
        assert AgentState.ERROR.value == "error"
