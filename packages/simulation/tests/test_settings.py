"""Tests for configuration settings."""

import os

import pytest


def test_settings_loads_from_env():
    """Test that settings loads from environment variables."""
    # Import after env vars are set in conftest
    from atlas_town.config.settings import get_settings

    # Clear the cache to force reload
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.atlas_username == "test@example.com"
    assert settings.atlas_password.get_secret_value() == "testpassword"
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert settings.openai_api_key.get_secret_value() == "sk-test"


def test_settings_has_defaults():
    """Test that settings has sensible defaults."""
    from atlas_town.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.atlas_api_url == "http://localhost:8000"
    assert settings.atlas_timeout == 30.0
    assert settings.atlas_max_retries == 3
    # Defaults to cheapest models (Jan 2026)
    assert settings.claude_model == "claude-haiku-4-5"
    assert settings.gpt_model == "gpt-5-nano"
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.ws_port == 8765
    assert settings.simulation_speed == 1.0


def test_settings_are_cached():
    """Test that get_settings returns cached instance."""
    from atlas_town.config.settings import get_settings

    get_settings.cache_clear()

    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2
