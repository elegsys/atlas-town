"""Customer agent archetypes for generating realistic transactions."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

from atlas_town.agents.base import AgentAction, AgentState, BaseAgent
from atlas_town.clients.openai_client import OpenAIClient

logger = structlog.get_logger(__name__)


class CustomerType(str, Enum):
    """Types of customers."""

    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    RECURRING = "recurring"
    ONE_TIME = "one_time"


@dataclass
class CustomerProfile:
    """Profile defining customer behavior."""

    name: str
    customer_type: CustomerType
    payment_reliability: float  # 0.0 to 1.0 (probability of paying on time)
    average_order_value: float
    order_frequency: str  # "daily", "weekly", "monthly", "occasional"
    preferred_services: list[str]
    payment_method: str


# Customer archetypes for each business type
CUSTOMER_ARCHETYPES: dict[str, list[CustomerProfile]] = {
    "landscaping": [
        CustomerProfile(
            name="Residential Homeowner",
            customer_type=CustomerType.RESIDENTIAL,
            payment_reliability=0.85,
            average_order_value=150.0,
            order_frequency="weekly",
            preferred_services=["lawn_mowing", "trimming", "leaf_removal"],
            payment_method="check",
        ),
        CustomerProfile(
            name="Property Manager",
            customer_type=CustomerType.COMMERCIAL,
            payment_reliability=0.95,
            average_order_value=500.0,
            order_frequency="weekly",
            preferred_services=["lawn_care", "landscaping", "snow_removal"],
            payment_method="bank_transfer",
        ),
        CustomerProfile(
            name="Commercial Building",
            customer_type=CustomerType.RECURRING,
            payment_reliability=0.90,
            average_order_value=800.0,
            order_frequency="monthly",
            preferred_services=["grounds_maintenance", "seasonal_planting"],
            payment_method="bank_transfer",
        ),
    ],
    "restaurant": [
        CustomerProfile(
            name="Walk-in Diner",
            customer_type=CustomerType.ONE_TIME,
            payment_reliability=1.0,
            average_order_value=25.0,
            order_frequency="daily",
            preferred_services=["dine_in", "takeout"],
            payment_method="credit_card",
        ),
        CustomerProfile(
            name="Catering Client",
            customer_type=CustomerType.RECURRING,
            payment_reliability=0.90,
            average_order_value=350.0,
            order_frequency="monthly",
            preferred_services=["catering", "event_packages"],
            payment_method="check",
        ),
        CustomerProfile(
            name="Corporate Account",
            customer_type=CustomerType.COMMERCIAL,
            payment_reliability=0.95,
            average_order_value=200.0,
            order_frequency="weekly",
            preferred_services=["lunch_delivery", "meeting_catering"],
            payment_method="invoice",
        ),
    ],
    "technology": [
        CustomerProfile(
            name="Small Business",
            customer_type=CustomerType.RECURRING,
            payment_reliability=0.85,
            average_order_value=2500.0,
            order_frequency="monthly",
            preferred_services=["it_support", "maintenance"],
            payment_method="bank_transfer",
        ),
        CustomerProfile(
            name="Project Client",
            customer_type=CustomerType.ONE_TIME,
            payment_reliability=0.80,
            average_order_value=15000.0,
            order_frequency="occasional",
            preferred_services=["software_development", "consulting"],
            payment_method="milestone_payments",
        ),
        CustomerProfile(
            name="Enterprise Retainer",
            customer_type=CustomerType.COMMERCIAL,
            payment_reliability=0.95,
            average_order_value=5000.0,
            order_frequency="monthly",
            preferred_services=["retainer", "priority_support"],
            payment_method="bank_transfer",
        ),
    ],
    "healthcare": [
        CustomerProfile(
            name="Regular Patient",
            customer_type=CustomerType.RECURRING,
            payment_reliability=0.75,
            average_order_value=200.0,
            order_frequency="monthly",
            preferred_services=["checkup", "cleaning"],
            payment_method="insurance_copay",
        ),
        CustomerProfile(
            name="Insurance Patient",
            customer_type=CustomerType.RECURRING,
            payment_reliability=0.95,
            average_order_value=500.0,
            order_frequency="occasional",
            preferred_services=["procedures", "x_rays"],
            payment_method="insurance",
        ),
        CustomerProfile(
            name="Self-Pay Patient",
            customer_type=CustomerType.ONE_TIME,
            payment_reliability=0.70,
            average_order_value=350.0,
            order_frequency="occasional",
            preferred_services=["emergency", "cosmetic"],
            payment_method="credit_card",
        ),
    ],
    "real_estate": [
        CustomerProfile(
            name="Home Buyer",
            customer_type=CustomerType.ONE_TIME,
            payment_reliability=1.0,
            average_order_value=12000.0,  # Commission
            order_frequency="occasional",
            preferred_services=["buying_agent"],
            payment_method="escrow",
        ),
        CustomerProfile(
            name="Home Seller",
            customer_type=CustomerType.ONE_TIME,
            payment_reliability=1.0,
            average_order_value=15000.0,  # Commission
            order_frequency="occasional",
            preferred_services=["listing_agent"],
            payment_method="closing",
        ),
        CustomerProfile(
            name="Property Owner",
            customer_type=CustomerType.RECURRING,
            payment_reliability=0.90,
            average_order_value=200.0,  # Management fee
            order_frequency="monthly",
            preferred_services=["property_management"],
            payment_method="bank_transfer",
        ),
    ],
}


class CustomerAgent(BaseAgent):
    """Customer agent that generates realistic purchase behavior.

    Customers don't use tools directly - they generate transaction
    requests that the accountant processes.
    """

    def __init__(
        self,
        profile: CustomerProfile,
        business_industry: str,
        agent_id: UUID | None = None,
    ):
        super().__init__(
            agent_id=agent_id,
            name=profile.name,
            description=f"{profile.customer_type.value} customer for {business_industry}",
        )

        self._profile = profile
        self._industry = business_industry
        self._llm_client = OpenAIClient()

        self._logger = logger.bind(
            agent_id=str(self.id),
            customer_type=profile.customer_type.value,
            industry=business_industry,
        )

    @property
    def profile(self) -> CustomerProfile:
        """Get the customer profile."""
        return self._profile

    def _get_system_prompt(self) -> str:
        """Get the customer's system prompt."""
        return f"""You are simulating a {self._profile.customer_type.value} customer for a {self._industry} business.

Profile:
- Name: {self._profile.name}
- Typical order value: ${self._profile.average_order_value:.2f}
- Order frequency: {self._profile.order_frequency}
- Preferred services: {', '.join(self._profile.preferred_services)}
- Payment method: {self._profile.payment_method}

Your role is to generate realistic purchase requests and behaviors.
When asked, describe what you'd like to purchase in natural language."""

    def _get_tools(self) -> list[dict[str, Any]]:
        """Customers don't have tools - they generate requests."""
        return []

    async def _generate_response(self) -> AgentAction:
        """Generate a customer response."""
        response = await self._llm_client.generate(
            system_prompt=self._get_system_prompt(),
            messages=[{"role": m.role, "content": m.content} for m in self._conversation_history],
            tools=None,
        )

        self.add_assistant_message(content=response.content)

        return AgentAction(
            agent_id=self.id,
            action_type="message",
            message=response.content,
        )

    async def generate_purchase_request(self) -> dict[str, Any]:
        """Generate a realistic purchase request.

        Returns:
            Dictionary with purchase details (items, estimated_value, notes)
        """
        prompt = f"""As a {self._profile.name}, generate a realistic purchase request.

Consider:
- Your typical order value is around ${self._profile.average_order_value:.2f}
- You prefer: {', '.join(self._profile.preferred_services)}

Describe what you want to purchase. Be specific about quantities and services."""

        action = await self.think(prompt)

        return {
            "customer_type": self._profile.customer_type.value,
            "request": action.message,
            "estimated_value": self._profile.average_order_value,
            "payment_method": self._profile.payment_method,
        }

    def will_pay_on_time(self) -> bool:
        """Determine if this customer will pay on time based on reliability."""
        import random
        return random.random() < self._profile.payment_reliability


def create_customers_for_industry(industry: str) -> list[CustomerAgent]:
    """Create customer agents for a specific industry.

    Args:
        industry: The business industry (e.g., "landscaping", "restaurant")

    Returns:
        List of CustomerAgent instances
    """
    archetypes = CUSTOMER_ARCHETYPES.get(industry, [])
    return [CustomerAgent(profile=p, business_industry=industry) for p in archetypes]
