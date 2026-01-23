"""Tests for owner agent implementations."""

from uuid import uuid4

import pytest

from atlas_town.agents.owner import (
    OWNER_PERSONAS,
    LLMProvider,
    OwnerAgent,
    create_all_owners,
)


class TestOwnerPersona:
    """Tests for OwnerPersona dataclass."""

    def test_persona_has_required_fields(self):
        """Test that all personas have required fields."""
        for key, persona in OWNER_PERSONAS.items():
            assert persona.name, f"{key} missing name"
            assert persona.business_name, f"{key} missing business_name"
            assert persona.industry, f"{key} missing industry"
            assert persona.personality_traits, f"{key} missing personality_traits"
            assert persona.llm_provider, f"{key} missing llm_provider"

    def test_all_five_personas_exist(self):
        """Test that all 5 owner personas are defined."""
        expected_keys = ["craig", "tony", "maya", "chen", "marcus"]
        for key in expected_keys:
            assert key in OWNER_PERSONAS, f"Missing persona: {key}"

    def test_llm_provider_distribution(self):
        """Test that personas use different LLM providers."""
        providers = {p.llm_provider for p in OWNER_PERSONAS.values()}

        # Should use all three providers
        assert LLMProvider.CLAUDE in providers
        assert LLMProvider.OPENAI in providers
        assert LLMProvider.GEMINI in providers


class TestOwnerAgent:
    """Tests for OwnerAgent class."""

    def test_owner_initialization(self):
        """Test owner agent initializes correctly."""
        agent = OwnerAgent(persona_key="craig")

        assert agent.name == "Craig Miller"
        assert agent.business_name == "Craig's Landscaping"
        assert agent.industry == "landscaping"

    def test_owner_with_invalid_persona_raises(self):
        """Test that invalid persona key raises error."""
        with pytest.raises(ValueError, match="Unknown persona"):
            OwnerAgent(persona_key="invalid")

    def test_owner_with_custom_id(self):
        """Test owner accepts custom UUID."""
        custom_id = uuid4()
        agent = OwnerAgent(persona_key="tony", agent_id=custom_id)

        assert agent.id == custom_id

    def test_owner_with_org_id(self):
        """Test owner accepts organization ID."""
        org_id = uuid4()
        agent = OwnerAgent(persona_key="maya", org_id=org_id)

        assert agent.current_org_id == org_id

    def test_owner_system_prompt_contains_persona(self):
        """Test system prompt includes persona details."""
        agent = OwnerAgent(persona_key="chen")
        prompt = agent._get_system_prompt()

        assert "Dr. Emily Chen" in prompt
        assert "Main Street Dental" in prompt
        assert "healthcare" in prompt.lower() or "dental" in prompt.lower()

    def test_owner_has_read_only_tools(self):
        """Test that owners have read-only tools."""
        agent = OwnerAgent(persona_key="marcus")
        tools = agent._get_tools()

        tool_names = [t["name"] for t in tools]

        # Should have read tools
        assert "list_customers" in tool_names
        assert "list_invoices" in tool_names
        assert "get_trial_balance" in tool_names

        # Should NOT have write tools
        assert "create_invoice" not in tool_names
        assert "create_bill" not in tool_names
        assert "create_payment" not in tool_names

    def test_craig_uses_openai(self):
        """Test Craig (landscaping) uses OpenAI."""
        agent = OwnerAgent(persona_key="craig")
        assert agent.persona.llm_provider == LLMProvider.OPENAI

    def test_maya_uses_claude(self):
        """Test Maya (tech) uses Claude."""
        agent = OwnerAgent(persona_key="maya")
        assert agent.persona.llm_provider == LLMProvider.CLAUDE

    def test_chen_uses_gemini(self):
        """Test Dr. Chen (dental) uses Gemini."""
        agent = OwnerAgent(persona_key="chen")
        assert agent.persona.llm_provider == LLMProvider.GEMINI


class TestCreateAllOwners:
    """Tests for create_all_owners factory function."""

    def test_creates_all_five_owners(self):
        """Test that factory creates all 5 owners."""
        owners = create_all_owners()

        assert len(owners) == 5
        assert "craig" in owners
        assert "tony" in owners
        assert "maya" in owners
        assert "chen" in owners
        assert "marcus" in owners

    def test_creates_owners_with_org_ids(self):
        """Test factory assigns org IDs correctly."""
        org_ids = {
            "craig": uuid4(),
            "tony": uuid4(),
        }

        owners = create_all_owners(org_ids)

        assert owners["craig"].current_org_id == org_ids["craig"]
        assert owners["tony"].current_org_id == org_ids["tony"]
        assert owners["maya"].current_org_id is None  # Not specified

    def test_each_owner_has_unique_id(self):
        """Test that each owner gets a unique agent ID."""
        owners = create_all_owners()

        ids = [o.id for o in owners.values()]
        assert len(ids) == len(set(ids))  # All unique
