"""Configuration module for Atlas Town simulation."""

from atlas_town.config.logging import configure_logging, get_logger
from atlas_town.config.settings import FlatSettings, get_settings

__all__ = ["FlatSettings", "get_settings", "configure_logging", "get_logger"]
