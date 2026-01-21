"""Configuration settings for Atlas Town simulation."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AtlasAPISettings(BaseSettings):
    """Settings for Atlas API connection."""

    url: str = Field(default="http://localhost:8000", description="Atlas API base URL")
    username: str = Field(..., description="Atlas API username (email)")
    password: SecretStr = Field(..., description="Atlas API password")
    timeout: float = Field(default=30.0, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Max retry attempts for failed requests")


class LLMSettings(BaseSettings):
    """Settings for LLM providers."""

    anthropic_api_key: SecretStr = Field(..., description="Anthropic API key for Claude")
    openai_api_key: SecretStr = Field(..., description="OpenAI API key for GPT")
    google_api_key: SecretStr = Field(..., description="Google API key for Gemini")

    # Model selections (defaults to cheapest capable models - Jan 2026)
    claude_model: str = Field(default="claude-haiku-4-5", description="Claude model ID")
    gpt_model: str = Field(default="gpt-5-nano", description="OpenAI GPT model ID")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Google Gemini model ID")

    # Rate limiting
    max_tokens: int = Field(default=4096, description="Max tokens per response")
    temperature: float = Field(default=0.7, description="LLM temperature for creativity")


class WebSocketSettings(BaseSettings):
    """Settings for WebSocket event publishing."""

    host: str = Field(default="0.0.0.0", description="WebSocket server host")
    port: int = Field(default=8765, description="WebSocket server port")
    ping_interval: float = Field(default=30.0, description="Ping interval in seconds")
    ping_timeout: float = Field(default=10.0, description="Ping timeout in seconds")


class SimulationSettings(BaseSettings):
    """Settings for simulation behavior."""

    speed_multiplier: float = Field(
        default=1.0, description="Simulation speed (1.0 = real-time, 10.0 = 10x faster)"
    )
    day_duration_seconds: float = Field(
        default=300.0, description="Duration of one simulated day in real seconds"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )
    log_format: Literal["json", "console"] = Field(
        default="console", description="Log output format"
    )


class Settings(BaseSettings):
    """Main settings aggregating all configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Nested settings with prefixes
    atlas: AtlasAPISettings = Field(default_factory=AtlasAPISettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    websocket: WebSocketSettings = Field(default_factory=WebSocketSettings)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)


# For flat environment variables (alternative approach)
class FlatSettings(BaseSettings):
    """Flat settings for simpler environment variable configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Atlas API
    atlas_api_url: str = Field(
        default="http://localhost:8000", validation_alias="ATLAS_API_URL"
    )
    atlas_username: str = Field(..., validation_alias="ATLAS_USERNAME")
    atlas_password: SecretStr = Field(..., validation_alias="ATLAS_PASSWORD")
    atlas_timeout: float = Field(default=30.0, validation_alias="ATLAS_TIMEOUT")
    atlas_max_retries: int = Field(default=3, validation_alias="ATLAS_MAX_RETRIES")

    # LLM API Keys
    anthropic_api_key: SecretStr = Field(..., validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr = Field(..., validation_alias="OPENAI_API_KEY")
    google_api_key: SecretStr = Field(..., validation_alias="GOOGLE_API_KEY")

    # Model selections (defaults to cheapest capable models - Jan 2026)
    claude_model: str = Field(
        default="claude-haiku-4-5", validation_alias="CLAUDE_MODEL"
    )
    gpt_model: str = Field(default="gpt-5-nano", validation_alias="GPT_MODEL")
    gemini_model: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL")

    # LLM parameters
    llm_max_tokens: int = Field(default=4096, validation_alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.7, validation_alias="LLM_TEMPERATURE")

    # WebSocket
    ws_host: str = Field(default="0.0.0.0", validation_alias="WS_HOST")
    ws_port: int = Field(default=8765, validation_alias="WS_PORT")

    # Simulation
    simulation_speed: float = Field(default=1.0, validation_alias="SIMULATION_SPEED")
    day_duration_seconds: float = Field(
        default=300.0, validation_alias="DAY_DURATION_SECONDS"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )


@lru_cache
def get_settings() -> FlatSettings:
    """Get cached settings instance."""
    return FlatSettings()
