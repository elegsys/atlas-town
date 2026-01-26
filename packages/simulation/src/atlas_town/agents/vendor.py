"""Vendor agent archetypes for generating realistic expenses."""

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from atlas_town.agents.base import AgentAction, BaseAgent
from atlas_town.clients.openai_client import OpenAIClient

logger = structlog.get_logger(__name__)


class VendorType(str, Enum):
    """Types of vendors."""

    SUPPLIER = "supplier"
    SERVICE = "service"
    UTILITY = "utility"
    RECURRING = "recurring"


@dataclass
class VendorProfile:
    """Profile defining vendor behavior."""

    name: str
    vendor_type: VendorType
    category: str  # expense category
    typical_amount: float
    billing_frequency: str  # "daily", "weekly", "monthly", "as_needed"
    payment_terms: int  # days until due
    description: str


# Vendor archetypes for each business type
VENDOR_ARCHETYPES: dict[str, list[VendorProfile]] = {
    "landscaping": [
        VendorProfile(
            name="Green Thumb Supplies",
            vendor_type=VendorType.SUPPLIER,
            category="supplies",
            typical_amount=500.0,
            billing_frequency="weekly",
            payment_terms=30,
            description="Seeds, fertilizer, mulch, plants",
        ),
        VendorProfile(
            name="Midwest Equipment Rental",
            vendor_type=VendorType.SERVICE,
            category="equipment_rental",
            typical_amount=350.0,
            billing_frequency="as_needed",
            payment_terms=15,
            description="Heavy equipment rental for large projects",
        ),
        VendorProfile(
            name="QuickFuel Gas Station",
            vendor_type=VendorType.RECURRING,
            category="fuel",
            typical_amount=400.0,
            billing_frequency="weekly",
            payment_terms=7,
            description="Fuel for trucks and equipment",
        ),
        VendorProfile(
            name="Smith Insurance Agency",
            vendor_type=VendorType.RECURRING,
            category="insurance",
            typical_amount=800.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Liability and equipment insurance",
        ),
        VendorProfile(
            name="Atlas Community Bank",
            vendor_type=VendorType.RECURRING,
            category="financing",
            typical_amount=650.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Business loan and credit line servicing",
        ),
    ],
    "restaurant": [
        VendorProfile(
            name="Fresh Foods Distributor",
            vendor_type=VendorType.SUPPLIER,
            category="food_inventory",
            typical_amount=2500.0,
            billing_frequency="weekly",
            payment_terms=14,
            description="Fresh produce, meat, dairy",
        ),
        VendorProfile(
            name="Sysco Food Service",
            vendor_type=VendorType.SUPPLIER,
            category="supplies",
            typical_amount=1200.0,
            billing_frequency="weekly",
            payment_terms=21,
            description="Dry goods, canned items, cleaning supplies",
        ),
        VendorProfile(
            name="City Utilities",
            vendor_type=VendorType.UTILITY,
            category="utilities",
            typical_amount=650.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Gas, water, electric",
        ),
        VendorProfile(
            name="POS Systems Inc",
            vendor_type=VendorType.RECURRING,
            category="software",
            typical_amount=150.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Point of sale system subscription",
        ),
        VendorProfile(
            name="Kitchen Repair Pros",
            vendor_type=VendorType.SERVICE,
            category="equipment_maintenance",
            typical_amount=850.0,
            billing_frequency="as_needed",
            payment_terms=15,
            description="Commercial kitchen equipment repairs and maintenance",
        ),
        VendorProfile(
            name="Atlas Community Bank",
            vendor_type=VendorType.RECURRING,
            category="financing",
            typical_amount=900.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Restaurant equipment loan and working capital line",
        ),
    ],
    "technology": [
        VendorProfile(
            name="AWS Cloud Services",
            vendor_type=VendorType.RECURRING,
            category="cloud_hosting",
            typical_amount=1500.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Cloud infrastructure and hosting",
        ),
        VendorProfile(
            name="JetBrains Software",
            vendor_type=VendorType.RECURRING,
            category="software_licenses",
            typical_amount=500.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Development tools and IDE licenses",
        ),
        VendorProfile(
            name="TechPro Contractors",
            vendor_type=VendorType.SERVICE,
            category="contractors",
            typical_amount=3000.0,
            billing_frequency="as_needed",
            payment_terms=15,
            description="Specialized contractors for projects",
        ),
        VendorProfile(
            name="Coworking Space LLC",
            vendor_type=VendorType.RECURRING,
            category="rent",
            typical_amount=2000.0,
            billing_frequency="monthly",
            payment_terms=1,
            description="Office space rental",
        ),
        VendorProfile(
            name="Atlas Community Bank",
            vendor_type=VendorType.RECURRING,
            category="financing",
            typical_amount=750.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Tech startup financing and credit line",
        ),
    ],
    "healthcare": [
        VendorProfile(
            name="Dental Supply Co",
            vendor_type=VendorType.SUPPLIER,
            category="medical_supplies",
            typical_amount=1800.0,
            billing_frequency="weekly",
            payment_terms=30,
            description="Dental supplies, tools, consumables",
        ),
        VendorProfile(
            name="Lab Services Inc",
            vendor_type=VendorType.SERVICE,
            category="lab_services",
            typical_amount=800.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Dental lab work, crowns, bridges",
        ),
        VendorProfile(
            name="Medical Equipment Leasing",
            vendor_type=VendorType.RECURRING,
            category="equipment_lease",
            typical_amount=1200.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="X-ray and imaging equipment lease",
        ),
        VendorProfile(
            name="Practice Management Software",
            vendor_type=VendorType.RECURRING,
            category="software",
            typical_amount=350.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Patient management and billing software",
        ),
        VendorProfile(
            name="Atlas Community Bank",
            vendor_type=VendorType.RECURRING,
            category="financing",
            typical_amount=1100.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Medical equipment loan and operating line",
        ),
    ],
    "real_estate": [
        VendorProfile(
            name="MLS Subscription Service",
            vendor_type=VendorType.RECURRING,
            category="subscriptions",
            typical_amount=400.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Multiple Listing Service access",
        ),
        VendorProfile(
            name="ProPhotography Studios",
            vendor_type=VendorType.SERVICE,
            category="marketing",
            typical_amount=300.0,
            billing_frequency="as_needed",
            payment_terms=15,
            description="Property photography and virtual tours",
        ),
        VendorProfile(
            name="SignMasters Printing",
            vendor_type=VendorType.SUPPLIER,
            category="marketing_materials",
            typical_amount=250.0,
            billing_frequency="as_needed",
            payment_terms=30,
            description="For sale signs, brochures, business cards",
        ),
        VendorProfile(
            name="Office Space Partners",
            vendor_type=VendorType.RECURRING,
            category="rent",
            typical_amount=1800.0,
            billing_frequency="monthly",
            payment_terms=1,
            description="Office rent and utilities",
        ),
        VendorProfile(
            name="Atlas Community Bank",
            vendor_type=VendorType.RECURRING,
            category="financing",
            typical_amount=700.0,
            billing_frequency="monthly",
            payment_terms=30,
            description="Brokerage credit line and financing services",
        ),
    ],
}


class VendorAgent(BaseAgent):
    """Vendor agent that generates realistic bills and expenses.

    Vendors generate bills that the business needs to pay.
    They don't use tools directly - they create expense requests.
    """

    def __init__(
        self,
        profile: VendorProfile,
        business_industry: str,
        agent_id: UUID | None = None,
    ):
        super().__init__(
            agent_id=agent_id,
            name=profile.name,
            description=f"{profile.vendor_type.value} vendor ({profile.category})",
        )

        self._profile = profile
        self._industry = business_industry
        self._llm_client = OpenAIClient()

        self._logger = logger.bind(
            agent_id=str(self.id),
            vendor_type=profile.vendor_type.value,
            category=profile.category,
        )

    @property
    def profile(self) -> VendorProfile:
        """Get the vendor profile."""
        return self._profile

    def _get_system_prompt(self) -> str:
        """Get the vendor's system prompt."""
        return f"""You are simulating {self._profile.name}, a
{self._profile.vendor_type.value} vendor.

Profile:
- Category: {self._profile.category}
- Typical bill amount: ${self._profile.typical_amount:.2f}
- Billing frequency: {self._profile.billing_frequency}
- Payment terms: Net {self._profile.payment_terms} days
- Products/Services: {self._profile.description}

Your role is to generate realistic bills and invoices.
When asked, provide details about what you're billing for."""

    def _get_tools(self) -> list[dict[str, Any]]:
        """Vendors don't have tools - they generate bills."""
        return []

    async def _generate_response(self) -> AgentAction:
        """Generate a vendor response."""
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

    async def generate_bill(self) -> dict[str, Any]:
        """Generate a realistic bill.

        Returns:
            Dictionary with bill details (items, amount, due_date_offset, notes)
        """
        import random

        # Add some variance to the typical amount (±20%)
        variance = random.uniform(0.8, 1.2)
        amount = round(self._profile.typical_amount * variance, 2)

        prompt = f"""As {self._profile.name}, generate a bill for a {self._industry} business.

Your typical products/services: {self._profile.description}
Bill amount should be around ${amount:.2f}

Describe the specific items or services being billed. Be realistic and detailed."""

        action = await self.think(prompt)

        return {
            "vendor_name": self._profile.name,
            "vendor_type": self._profile.vendor_type.value,
            "category": self._profile.category,
            "description": action.message,
            "amount": amount,
            "payment_terms": self._profile.payment_terms,
        }

    def should_send_bill_today(self, day_of_month: int) -> bool:
        """Determine if this vendor should send a bill today.

        Args:
            day_of_month: Current day of the month (1-31)

        Returns:
            True if bill should be sent today
        """
        import random

        if self._profile.billing_frequency == "daily":
            return True
        elif self._profile.billing_frequency == "weekly":
            # Bill on a consistent day of week (use vendor name hash)
            return hash(self._profile.name) % 7 == day_of_month % 7
        elif self._profile.billing_frequency == "monthly":
            # Bill on a consistent day of month
            bill_day = (hash(self._profile.name) % 28) + 1
            return day_of_month == bill_day
        elif self._profile.billing_frequency == "as_needed":
            # 20% chance on any given day
            return random.random() < 0.2
        return False


def create_vendors_for_industry(industry: str) -> list[VendorAgent]:
    """Create vendor agents for a specific industry.

    Args:
        industry: The business industry (e.g., "landscaping", "restaurant")

    Returns:
        List of VendorAgent instances
    """
    archetypes = VENDOR_ARCHETYPES.get(industry, [])
    return [VendorAgent(profile=p, business_industry=industry) for p in archetypes]
