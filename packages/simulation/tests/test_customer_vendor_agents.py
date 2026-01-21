"""Tests for customer and vendor agent implementations."""

import pytest

from atlas_town.agents.customer import (
    CustomerAgent,
    CustomerProfile,
    CustomerType,
    CUSTOMER_ARCHETYPES,
    create_customers_for_industry,
)
from atlas_town.agents.vendor import (
    VendorAgent,
    VendorProfile,
    VendorType,
    VENDOR_ARCHETYPES,
    create_vendors_for_industry,
)


class TestCustomerProfile:
    """Tests for CustomerProfile dataclass."""

    def test_profile_creation(self):
        """Test creating a customer profile."""
        profile = CustomerProfile(
            name="Test Customer",
            customer_type=CustomerType.RESIDENTIAL,
            payment_reliability=0.9,
            average_order_value=100.0,
            order_frequency="weekly",
            preferred_services=["service_a", "service_b"],
            payment_method="credit_card",
        )

        assert profile.name == "Test Customer"
        assert profile.customer_type == CustomerType.RESIDENTIAL
        assert profile.payment_reliability == 0.9

    def test_customer_type_values(self):
        """Test CustomerType enum values."""
        assert CustomerType.RESIDENTIAL.value == "residential"
        assert CustomerType.COMMERCIAL.value == "commercial"
        assert CustomerType.RECURRING.value == "recurring"
        assert CustomerType.ONE_TIME.value == "one_time"


class TestCustomerArchetypes:
    """Tests for customer archetype definitions."""

    def test_all_industries_have_archetypes(self):
        """Test that all industries have customer archetypes."""
        expected_industries = ["landscaping", "restaurant", "technology", "healthcare", "real_estate"]

        for industry in expected_industries:
            assert industry in CUSTOMER_ARCHETYPES, f"Missing archetypes for {industry}"
            assert len(CUSTOMER_ARCHETYPES[industry]) > 0

    def test_archetypes_have_valid_profiles(self):
        """Test that all archetypes have valid profiles."""
        for industry, profiles in CUSTOMER_ARCHETYPES.items():
            for profile in profiles:
                assert profile.name, f"Missing name in {industry} archetype"
                assert 0.0 <= profile.payment_reliability <= 1.0
                assert profile.average_order_value > 0
                assert profile.order_frequency in ["daily", "weekly", "monthly", "occasional"]


class TestCustomerAgent:
    """Tests for CustomerAgent class."""

    def test_customer_initialization(self):
        """Test customer agent initializes correctly."""
        profile = CUSTOMER_ARCHETYPES["restaurant"][0]
        agent = CustomerAgent(profile=profile, business_industry="restaurant")

        assert agent.name == profile.name
        assert agent.profile == profile

    def test_customer_has_no_tools(self):
        """Test that customers don't have tools."""
        profile = CUSTOMER_ARCHETYPES["landscaping"][0]
        agent = CustomerAgent(profile=profile, business_industry="landscaping")

        tools = agent._get_tools()
        assert tools == []

    def test_customer_system_prompt_includes_profile(self):
        """Test system prompt includes profile details."""
        profile = CUSTOMER_ARCHETYPES["technology"][0]
        agent = CustomerAgent(profile=profile, business_industry="technology")

        prompt = agent._get_system_prompt()
        assert profile.name in prompt
        assert str(profile.average_order_value) in prompt

    def test_will_pay_on_time_respects_reliability(self):
        """Test payment reliability affects behavior."""
        # High reliability customer
        high_profile = CustomerProfile(
            name="High Reliability",
            customer_type=CustomerType.COMMERCIAL,
            payment_reliability=1.0,  # Always pays
            average_order_value=100.0,
            order_frequency="monthly",
            preferred_services=["service"],
            payment_method="check",
        )
        high_agent = CustomerAgent(profile=high_profile, business_industry="test")

        # With 1.0 reliability, should always pay on time
        for _ in range(10):
            assert high_agent.will_pay_on_time() is True


class TestCreateCustomersForIndustry:
    """Tests for customer factory function."""

    def test_creates_customers_for_valid_industry(self):
        """Test factory creates customers for valid industry."""
        customers = create_customers_for_industry("restaurant")

        assert len(customers) > 0
        assert all(isinstance(c, CustomerAgent) for c in customers)

    def test_returns_empty_for_unknown_industry(self):
        """Test factory returns empty list for unknown industry."""
        customers = create_customers_for_industry("unknown_industry")
        assert customers == []


class TestVendorProfile:
    """Tests for VendorProfile dataclass."""

    def test_profile_creation(self):
        """Test creating a vendor profile."""
        profile = VendorProfile(
            name="Test Vendor",
            vendor_type=VendorType.SUPPLIER,
            category="supplies",
            typical_amount=500.0,
            billing_frequency="weekly",
            payment_terms=30,
            description="Test supplies",
        )

        assert profile.name == "Test Vendor"
        assert profile.vendor_type == VendorType.SUPPLIER
        assert profile.payment_terms == 30

    def test_vendor_type_values(self):
        """Test VendorType enum values."""
        assert VendorType.SUPPLIER.value == "supplier"
        assert VendorType.SERVICE.value == "service"
        assert VendorType.UTILITY.value == "utility"
        assert VendorType.RECURRING.value == "recurring"


class TestVendorArchetypes:
    """Tests for vendor archetype definitions."""

    def test_all_industries_have_archetypes(self):
        """Test that all industries have vendor archetypes."""
        expected_industries = ["landscaping", "restaurant", "technology", "healthcare", "real_estate"]

        for industry in expected_industries:
            assert industry in VENDOR_ARCHETYPES, f"Missing archetypes for {industry}"
            assert len(VENDOR_ARCHETYPES[industry]) > 0

    def test_archetypes_have_valid_profiles(self):
        """Test that all archetypes have valid profiles."""
        for industry, profiles in VENDOR_ARCHETYPES.items():
            for profile in profiles:
                assert profile.name, f"Missing name in {industry} vendor"
                assert profile.typical_amount > 0
                assert profile.payment_terms >= 0
                assert profile.billing_frequency in ["daily", "weekly", "monthly", "as_needed"]


class TestVendorAgent:
    """Tests for VendorAgent class."""

    def test_vendor_initialization(self):
        """Test vendor agent initializes correctly."""
        profile = VENDOR_ARCHETYPES["restaurant"][0]
        agent = VendorAgent(profile=profile, business_industry="restaurant")

        assert agent.name == profile.name
        assert agent.profile == profile

    def test_vendor_has_no_tools(self):
        """Test that vendors don't have tools."""
        profile = VENDOR_ARCHETYPES["technology"][0]
        agent = VendorAgent(profile=profile, business_industry="technology")

        tools = agent._get_tools()
        assert tools == []

    def test_vendor_system_prompt_includes_profile(self):
        """Test system prompt includes profile details."""
        profile = VENDOR_ARCHETYPES["healthcare"][0]
        agent = VendorAgent(profile=profile, business_industry="healthcare")

        prompt = agent._get_system_prompt()
        assert profile.name in prompt
        assert str(profile.payment_terms) in prompt

    def test_should_send_bill_daily_vendor(self):
        """Test daily billing vendor always sends bill."""
        profile = VendorProfile(
            name="Daily Vendor",
            vendor_type=VendorType.SUPPLIER,
            category="supplies",
            typical_amount=100.0,
            billing_frequency="daily",
            payment_terms=7,
            description="Daily supplies",
        )
        agent = VendorAgent(profile=profile, business_industry="test")

        # Daily vendor should always send bill
        for day in range(1, 32):
            assert agent.should_send_bill_today(day) is True


class TestCreateVendorsForIndustry:
    """Tests for vendor factory function."""

    def test_creates_vendors_for_valid_industry(self):
        """Test factory creates vendors for valid industry."""
        vendors = create_vendors_for_industry("landscaping")

        assert len(vendors) > 0
        assert all(isinstance(v, VendorAgent) for v in vendors)

    def test_returns_empty_for_unknown_industry(self):
        """Test factory returns empty list for unknown industry."""
        vendors = create_vendors_for_industry("unknown_industry")
        assert vendors == []
