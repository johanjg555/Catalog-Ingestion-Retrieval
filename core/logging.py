"""Structured logging configuration using structlog."""

import logging
import sys
import os
import structlog

from core.config import settings


def setup_logging() -> None:
    """Configure structlog for JSON-formatted, async-safe logging."""

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Standard-library root logger ────────────────────────────
    
    log_dir = os.path.dirname(settings.log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(settings.log_file)
    stream_handler = logging.StreamHandler(sys.stdout)
    
    # Clear existing handlers to prevent duplicates if called multiple times
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    logging.basicConfig(
        format="%(message)s",
        handlers=[stream_handler, file_handler],
        level=log_level,
    )

    # structlog pipeline ──────────────────────────────────────
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named logger instance."""
    return structlog.get_logger(name)
