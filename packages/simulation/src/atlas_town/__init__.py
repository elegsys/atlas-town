"""Atlas Town - AI simulation engine for realistic accounting data generation."""

__version__ = "0.1.0"

from atlas_town.agents import (
    AccountantAgent,
    AgentState,
    BaseAgent,
    CustomerAgent,
    OwnerAgent,
    VendorAgent,
    create_all_owners,
    create_customers_for_industry,
    create_vendors_for_industry,
)
from atlas_town.clients import ClaudeClient, GeminiClient, OpenAIClient
from atlas_town.config import configure_logging, get_settings
from atlas_town.orchestrator import Orchestrator, SimulationPhase
from atlas_town.scheduler import DayPhase, Scheduler, SimulatedTime
from atlas_town.tools import AtlasAPIClient, ToolExecutor

__all__ = [
    # Version
    "__version__",
    # Agents
    "BaseAgent",
    "AgentState",
    "AccountantAgent",
    "OwnerAgent",
    "CustomerAgent",
    "VendorAgent",
    "create_all_owners",
    "create_customers_for_industry",
    "create_vendors_for_industry",
    # LLM Clients
    "ClaudeClient",
    "OpenAIClient",
    "GeminiClient",
    # Orchestrator & Scheduler
    "Orchestrator",
    "SimulationPhase",
    "Scheduler",
    "DayPhase",
    "SimulatedTime",
    # Tools
    "AtlasAPIClient",
    "ToolExecutor",
    # Config
    "get_settings",
    "configure_logging",
]
