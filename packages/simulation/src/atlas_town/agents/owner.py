"""Business owner agents for Atlas Town."""

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from atlas_town.agents.base import AgentAction, AgentState, BaseAgent
from atlas_town.clients.claude import ClaudeClient
from atlas_town.clients.gemini import GeminiClient
from atlas_town.clients.ollama import OllamaClient
from atlas_town.clients.openai_client import OpenAIClient
from atlas_town.config import get_settings
from atlas_town.tools.definitions import OWNER_TOOLS

logger = structlog.get_logger(__name__)


class LLMProvider(str, Enum):
    """LLM provider selection."""

    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"


@dataclass
class OwnerPersona:
    """Defines a business owner's personality and business."""

    name: str
    business_name: str
    industry: str
    personality_traits: list[str]
    communication_style: str
    business_focus: str
    typical_concerns: list[str]
    llm_provider: LLMProvider


# The 5 business owner personas
OWNER_PERSONAS: dict[str, OwnerPersona] = {
    "craig": OwnerPersona(
        name="Craig Miller",
        business_name="Craig's Landscaping",
        industry="landscaping",
        personality_traits=["practical", "hardworking", "straightforward", "weather-conscious"],
        communication_style="Direct and no-nonsense, uses industry jargon",
        business_focus="Seasonal lawn care, landscaping projects, snow removal in winter",
        typical_concerns=[
            "Weather affecting jobs",
            "Equipment maintenance costs",
            "Seasonal cash flow",
            "Finding reliable workers",
        ],
        llm_provider=LLMProvider.OPENAI,
    ),
    "tony": OwnerPersona(
        name="Tony Russo",
        business_name="Tony's Pizzeria",
        industry="restaurant",
        personality_traits=["passionate", "family-oriented", "quality-focused", "community-minded"],
        communication_style="Warm and expressive, talks about food with enthusiasm",
        business_focus="Authentic Italian pizza, family recipes, local ingredients",
        typical_concerns=[
            "Food costs and margins",
            "Staff scheduling",
            "Health inspections",
            "Competition from chains",
        ],
        llm_provider=LLMProvider.OPENAI,
    ),
    "maya": OwnerPersona(
        name="Maya Patel",
        business_name="Nexus Tech Consulting",
        industry="technology",
        personality_traits=["analytical", "innovative", "client-focused", "detail-oriented"],
        communication_style="Professional and precise, explains technical concepts clearly",
        business_focus="IT consulting, software development, cloud migration",
        typical_concerns=[
            "Project timelines and scope creep",
            "Keeping skills current",
            "Retainer vs project billing",
            "Client communication",
        ],
        llm_provider=LLMProvider.CLAUDE,
    ),
    "chen": OwnerPersona(
        name="Dr. Emily Chen",
        business_name="Main Street Dental",
        industry="healthcare",
        personality_traits=["caring", "meticulous", "patient-focused", "professional"],
        communication_style="Calm and reassuring, explains procedures clearly",
        business_focus="Family dentistry, preventive care, cosmetic procedures",
        typical_concerns=[
            "Insurance reimbursements",
            "Equipment upgrades",
            "Patient retention",
            "Compliance and regulations",
        ],
        llm_provider=LLMProvider.GEMINI,
    ),
    "marcus": OwnerPersona(
        name="Marcus Johnson",
        business_name="Harbor Realty",
        industry="real_estate",
        personality_traits=["persuasive", "networked", "market-savvy", "ambitious"],
        communication_style="Confident and relationship-focused, market insights",
        business_focus="Residential sales, property management, investment properties",
        typical_concerns=[
            "Market fluctuations",
            "Commission tracking",
            "Trust account compliance",
            "Lead generation",
        ],
        llm_provider=LLMProvider.OPENAI,
    ),
}


def _create_owner_system_prompt(persona: OwnerPersona) -> str:
    """Generate a system prompt for a business owner."""
    traits = ", ".join(persona.personality_traits)
    concerns = "\n".join(f"- {c}" for c in persona.typical_concerns)

    return f"""You are {persona.name}, the owner of {persona.business_name}, a {persona.industry} business in Atlas Town.

## Your Personality
You are {traits}. {persona.communication_style}

## Your Business
{persona.business_focus}

## Your Typical Concerns
{concerns}

## Your Role in the Simulation
As a business owner, you:
1. Review your business's financial status
2. Make decisions about operations
3. Interact with your accountant Sarah about bookkeeping
4. Generate realistic business transactions

## Guidelines
- Stay in character as {persona.name}
- Make decisions that a real {persona.industry} business owner would make
- Express concerns naturally based on your personality
- When reviewing reports, comment on items relevant to your business

## Communication Style
{persona.communication_style}

Remember: You're running a real business. Think about cash flow, customer relationships, vendor payments, and growth opportunities."""


class OwnerAgent(BaseAgent):
    """Business owner agent with industry-specific persona.

    Each owner has:
    - A unique personality and communication style
    - Industry-specific concerns and focus
    - Read-only access to their business financials
    - Ability to make business decisions
    """

    def __init__(
        self,
        persona_key: str,
        agent_id: UUID | None = None,
        org_id: UUID | None = None,
    ):
        if persona_key not in OWNER_PERSONAS:
            raise ValueError(f"Unknown persona: {persona_key}. Valid: {list(OWNER_PERSONAS.keys())}")

        self._persona = OWNER_PERSONAS[persona_key]

        super().__init__(
            agent_id=agent_id,
            name=self._persona.name,
            description=f"Owner of {self._persona.business_name} ({self._persona.industry})",
        )

        # Set organization if provided
        if org_id:
            self.set_organization(org_id)

        # Create the appropriate LLM client
        self._llm_client = self._create_llm_client()

        self._logger = logger.bind(
            agent_id=str(self.id),
            agent_name=self.name,
            business=self._persona.business_name,
        )

    def _create_llm_client(self) -> ClaudeClient | OpenAIClient | GeminiClient | OllamaClient:
        """Create the LLM client based on persona's provider or environment override."""
        # Check for environment variable override
        settings = get_settings()
        provider_override = settings.llm_provider.lower()

        # Use override if set to a local provider, otherwise use persona's provider
        if provider_override in ("ollama", "lm_studio"):
            provider = LLMProvider(provider_override)
        else:
            provider = self._persona.llm_provider

        if provider == LLMProvider.CLAUDE:
            return ClaudeClient()
        elif provider == LLMProvider.OPENAI:
            return OpenAIClient()
        elif provider == LLMProvider.GEMINI:
            return GeminiClient()
        elif provider == LLMProvider.OLLAMA:
            return OllamaClient()
        elif provider == LLMProvider.LM_STUDIO:
            # LM Studio uses OpenAI-compatible API
            return OpenAIClient(
                api_key="lm-studio",  # LM Studio doesn't require a real key
                base_url=settings.lm_studio_base_url,
                model=settings.lm_studio_model or None,
            )
        else:
            # Default to OpenAI
            return OpenAIClient()

    @property
    def persona(self) -> OwnerPersona:
        """Get the owner's persona."""
        return self._persona

    @property
    def business_name(self) -> str:
        """Get the business name."""
        return self._persona.business_name

    @property
    def industry(self) -> str:
        """Get the industry."""
        return self._persona.industry

    def _get_system_prompt(self) -> str:
        """Get the owner's system prompt."""
        return _create_owner_system_prompt(self._persona)

    def _get_tools(self) -> list[dict[str, Any]]:
        """Get the tools available to this owner (read-only access)."""
        return OWNER_TOOLS

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
        """Generate a response using the configured LLM."""
        self._logger.debug("generating_response")

        # Call the LLM (all clients have the same interface)
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
            tool_call = response.tool_calls[0]
            action = AgentAction(
                agent_id=self.id,
                action_type="tool_call",
                tool_name=tool_call["name"],
                tool_args=tool_call["arguments"],
                message=response.content,
            )
            self.state = AgentState.ACTING
        elif response.stop_reason == "end_turn":
            action = AgentAction(
                agent_id=self.id,
                action_type="complete",
                message=response.content,
            )
            self.state = AgentState.IDLE
        else:
            action = AgentAction(
                agent_id=self.id,
                action_type="message",
                message=response.content,
            )
            self.state = AgentState.IDLE

        return action

    async def review_financials(self, focus: str | None = None) -> str:
        """Have the owner review their business financials.

        Args:
            focus: Optional area to focus on (e.g., "receivables", "cash flow")

        Returns:
            Owner's commentary on the financials.
        """
        focus_text = f" Focus on {focus}." if focus else ""

        prompt = f"""Please review the current financial status of {self._persona.business_name}.{focus_text}

Look at:
1. Outstanding invoices (AR aging)
2. Bills due (AP aging)
3. Recent profit/loss if available

Share your thoughts as {self._persona.name}, commenting on anything that concerns you or looks good."""

        action = await self.think(prompt)
        return action.message or ""

    async def make_decision(self, scenario: str, options: list[str]) -> str:
        """Have the owner make a business decision.

        Args:
            scenario: Description of the situation
            options: List of possible choices

        Returns:
            Owner's decision and reasoning.
        """
        options_text = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(options))

        prompt = f"""As {self._persona.name}, you need to make a decision:

Situation: {scenario}

Options:
{options_text}

What would you choose and why? Consider your business priorities and typical concerns."""

        action = await self.think(prompt)
        return action.message or ""


def create_all_owners(org_ids: dict[str, UUID] | None = None) -> dict[str, OwnerAgent]:
    """Create all 5 owner agents.

    Args:
        org_ids: Optional mapping of persona_key -> organization UUID

    Returns:
        Dictionary of persona_key -> OwnerAgent
    """
    org_ids = org_ids or {}
    owners = {}

    for key in OWNER_PERSONAS:
        owners[key] = OwnerAgent(
            persona_key=key,
            org_id=org_ids.get(key),
        )

    return owners
