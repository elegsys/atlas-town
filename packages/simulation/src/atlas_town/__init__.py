"""Atlas Town - AI simulation engine for realistic accounting data generation."""

__version__ = "0.1.0"

from atlas_town.agents import AccountantAgent, AgentState, BaseAgent
from atlas_town.config import configure_logging, get_settings
from atlas_town.orchestrator import Orchestrator, SimulationPhase
from atlas_town.tools import AtlasAPIClient, ToolExecutor

__all__ = [
    # Version
    "__version__",
    # Agents
    "BaseAgent",
    "AgentState",
    "AccountantAgent",
    # Orchestrator
    "Orchestrator",
    "SimulationPhase",
    # Tools
    "AtlasAPIClient",
    "ToolExecutor",
    # Config
    "get_settings",
    "configure_logging",
]
