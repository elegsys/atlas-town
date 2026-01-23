"""Sarah the Accountant - manages books for all organizations."""

from typing import Any
from uuid import UUID

import structlog

from atlas_town.agents.base import AgentAction, AgentState, BaseAgent
from atlas_town.agents.owner import LLMProvider
from atlas_town.clients.claude import ClaudeClient
from atlas_town.clients.gemini import GeminiClient
from atlas_town.clients.ollama import OllamaClient
from atlas_town.clients.openai_client import OpenAIClient
from atlas_town.config import get_settings
from atlas_town.tools.definitions import ACCOUNTANT_TOOLS
from atlas_town.tools.executor import ToolExecutor

logger = structlog.get_logger(__name__)

SARAH_SYSTEM_PROMPT = """You are Sarah Chen, a professional bookkeeper and accountant managing
the finances for multiple small businesses in Atlas Town. You are meticulous,
organized, and take pride in keeping accurate records.

## Your Personality
- Methodical and detail-oriented
- Friendly but professional
- You explain your actions clearly
- You double-check numbers before finalizing entries
- You're proactive about identifying issues

## Your Role
You manage the books for 5 businesses:
1. Craig's Landscaping - Lawn care and landscaping services
2. Tony's Pizzeria - Restaurant and food service
3. Nexus Tech Consulting - IT consulting and software development
4. Main Street Dental - Dental practice
5. Harbor Realty - Real estate and property management

## Your Daily Tasks
- Review and process invoices
- Record customer payments
- Enter vendor bills
- Process bill payments
- Reconcile bank transactions
- Generate financial reports
- Ensure books are balanced

## Guidelines
1. Always verify the current organization context before taking actions
2. When creating invoices or bills, include clear descriptions
3. Match payments to invoices/bills when possible
4. Flag any discrepancies or unusual transactions
5. Keep accurate records with proper dates and references

## Communication Style
When explaining your work:
- State which organization you're working on
- Describe what you're about to do and why
- Report the outcome of your actions
- Note any issues that need attention

Remember: Accuracy is paramount. When in doubt, ask for clarification rather than
making assumptions."""


class AccountantAgent(BaseAgent):
    """Sarah the Accountant - manages financial records for all businesses.

    This agent uses the configured LLM provider for reasoning and has access
    to all accounting tools including invoicing, bills, payments, and reports.
    """

    def __init__(
        self,
        agent_id: UUID | None = None,
        llm_client: ClaudeClient | OpenAIClient | GeminiClient | OllamaClient | None = None,
        llm_provider: LLMProvider | None = None,
        tool_executor: ToolExecutor | None = None,
    ):
        super().__init__(
            agent_id=agent_id,
            name="Sarah Chen",
            description="Professional bookkeeper managing finances for Atlas Town businesses",
        )

        self._llm_client = llm_client or self._create_llm_client(llm_provider)
        self._tool_executor = tool_executor
        self._logger = logger.bind(agent_id=str(self.id), agent_name=self.name)

    def _create_llm_client(
        self, provider: LLMProvider | None = None
    ) -> ClaudeClient | OpenAIClient | GeminiClient | OllamaClient:
        """Create the LLM client based on provider or environment config."""
        settings = get_settings()

        # Use explicit provider, env var override, or default to Claude
        if provider is None:
            provider_str = settings.llm_provider.lower()
            try:
                provider = LLMProvider(provider_str)
            except ValueError:
                provider = LLMProvider.CLAUDE

        if provider == LLMProvider.CLAUDE:
            return ClaudeClient()
        elif provider == LLMProvider.OPENAI:
            return OpenAIClient()
        elif provider == LLMProvider.GEMINI:
            return GeminiClient()
        elif provider == LLMProvider.OLLAMA:
            return OllamaClient()
        elif provider == LLMProvider.LM_STUDIO:
            return OpenAIClient(
                api_key="lm-studio",
                base_url=settings.lm_studio_base_url,
                model=settings.lm_studio_model or None,
            )
        else:
            return ClaudeClient()

    def set_tool_executor(self, executor: ToolExecutor) -> None:
        """Set the tool executor for this agent."""
        self._tool_executor = executor

    def _get_system_prompt(self) -> str:
        """Get Sarah's system prompt."""
        return SARAH_SYSTEM_PROMPT

    def _get_tools(self) -> list[dict[str, Any]]:
        """Get the accounting tools available to Sarah."""
        return ACCOUNTANT_TOOLS

    def _format_messages_for_llm(self) -> list[dict[str, Any]]:
        """Format conversation history for the LLM client."""
        messages = []
        for msg in self._conversation_history:
            messages.append({
                "role": msg.role,
                "content": msg.content,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
            })
        return messages

    async def _generate_response(self) -> AgentAction:
        """Generate a response using Claude."""
        self._logger.debug("generating_response")

        # Call the LLM
        response = await self._llm_client.generate(
            system_prompt=self._get_system_prompt(),
            messages=self._format_messages_for_llm(),
            tools=self._get_tools(),
        )

        # Add assistant message to history
        self.add_assistant_message(
            content=response.content,
            tool_calls=response.tool_calls,
        )

        # Determine the action type
        if response.tool_calls:
            # Agent wants to use a tool
            tool_call = response.tool_calls[0]  # Process one tool at a time
            action = AgentAction(
                agent_id=self.id,
                action_type="tool_call",
                tool_name=tool_call["name"],
                tool_args=tool_call["arguments"],
                message=response.content,
            )
            self.state = AgentState.ACTING
        elif response.stop_reason == "end_turn":
            # Agent is done
            action = AgentAction(
                agent_id=self.id,
                action_type="complete",
                message=response.content,
            )
            self.state = AgentState.IDLE
        else:
            # Agent sent a message
            action = AgentAction(
                agent_id=self.id,
                action_type="message",
                message=response.content,
            )
            self.state = AgentState.IDLE

        return action

    async def execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call and return the result.

        Args:
            tool_name: Name of the tool to execute.
            tool_args: Arguments for the tool.

        Returns:
            Tool execution result.
        """
        if not self._tool_executor:
            raise RuntimeError("Tool executor not set")

        self._logger.info("executing_tool", tool=tool_name, args=tool_args)
        result = await self._tool_executor.execute(tool_name, tool_args)
        return result

    async def run_task(self, task: str, max_iterations: int = 10) -> str:
        """Run a task to completion, handling tool calls automatically.

        This is the main entry point for having Sarah complete a task.
        She will think, act, and observe in a loop until the task is complete.

        Args:
            task: The task description for Sarah to complete.
            max_iterations: Maximum number of think-act-observe cycles.

        Returns:
            Final response from Sarah.
        """
        self._logger.info("starting_task", task=task[:100])

        # Initial prompt
        current_prompt = task
        final_response = ""

        for iteration in range(max_iterations):
            self._logger.debug("iteration", number=iteration + 1)

            # Think and decide on action
            action = await self.think(current_prompt)

            if action.action_type == "tool_call":
                # Execute the tool
                if not self._tool_executor:
                    error_msg = "Cannot execute tools: no tool executor configured"
                    self._logger.error("no_tool_executor")
                    return error_msg

                result = await self.execute_tool(
                    action.tool_name or "",
                    action.tool_args,
                )

                # Add tool result to conversation
                # Find the tool call ID from the last assistant message
                tool_call_id = "unknown"
                for msg in reversed(self._conversation_history):
                    if msg.role == "assistant" and msg.tool_calls:
                        tool_call_id = msg.tool_calls[-1].get("id", "unknown")
                        break

                self.add_tool_result(
                    tool_call_id=tool_call_id,
                    result=str(result),
                )

                # Continue the loop - Sarah will process the result
                current_prompt = ""  # No new user input, just continue

            elif action.action_type == "complete":
                # Task is done
                final_response = action.message or ""
                self._logger.info("task_completed", response_length=len(final_response))
                break

            elif action.action_type == "message":
                # Sarah sent a message but may need to continue
                final_response = action.message or ""
                # Check if she's asking for clarification or done
                break

        return final_response

    async def process_invoice(
        self,
        customer_id: str,
        items: list[dict[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        """High-level method to create and send an invoice.

        Args:
            customer_id: The customer's UUID.
            items: List of line items with description, quantity, unit_price.
            notes: Optional notes for the invoice.

        Returns:
            The created invoice details.
        """
        task = f"""Please create an invoice for customer {customer_id} with the following items:

{self._format_items(items)}

Notes: {notes if notes else 'None'}

After creating the invoice, please send it to the customer."""

        await self.run_task(task)

        # Return the last tool result which should be the invoice
        for msg in reversed(self._conversation_history):
            if msg.role == "tool_result":
                return {"status": "success", "result": msg.content}

        return {"status": "completed"}

    def _format_items(self, items: list[dict[str, Any]]) -> str:
        """Format line items for a prompt."""
        lines = []
        for i, item in enumerate(items, 1):
            lines.append(
                f"{i}. {item.get('description', 'Item')} - "
                f"Qty: {item.get('quantity', 1)}, "
                f"Price: ${item.get('unit_price', '0.00')}"
            )
        return "\n".join(lines)
