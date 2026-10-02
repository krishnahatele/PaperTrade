"""Structured logging built on structlog.

Every log line is a structured event. In containers we emit JSON; locally
``MARKETOS_LOG_JSON=false`` gives human-readable console output. Standard
library loggers (uvicorn, sqlalchemy, alembic) are routed through the same
pipeline so the output format is uniform.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    level = logging.getLevelName(settings.log_level.upper())

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.typing.Processor
    if settings.log_json:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its own handlers; let records propagate to root instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # Request logging is done by our middleware.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None, **initial: Any) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger.bind(**initial) if initial else logger
