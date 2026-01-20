"""Structured logging configuration for Atlas Town."""

import logging
import sys
from typing import Literal

import structlog

from atlas_town.config.settings import get_settings


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None,
    format: Literal["json", "console"] | None = None,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to settings.
        format: Output format (json or console). Defaults to settings.
    """
    settings = get_settings()
    log_level = level or settings.log_level
    log_format = format or "console"

    # Set up standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )

    # Choose processors based on format
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )

    # Common processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance bound to the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Bound logger instance.
    """
    return structlog.get_logger(name)
