"""Logging helpers shared by the CLI, agent, daemon and GUI."""

from __future__ import annotations

import json
import logging as std_logging
import sys
from datetime import UTC, datetime
from typing import TextIO

_STANDARD_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(std_logging.Formatter):
    """Emit one JSON object per log record for journald or diagnostics."""

    def format(self, record: std_logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
        }
        if extras:
            payload["context"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


def configure_logging(
    *,
    level: int | str = std_logging.INFO,
    json_output: bool = False,
    stream: TextIO | None = None,
) -> None:
    """Configure only the PowerDeck logger hierarchy, without touching root handlers."""

    logger = std_logging.getLogger("powerdeck")
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()

    handler = std_logging.StreamHandler(stream or sys.stderr)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            std_logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    logger.addHandler(handler)


def get_logger(component: str | None = None) -> std_logging.Logger:
    name = "powerdeck" if not component else f"powerdeck.{component}"
    return std_logging.getLogger(name)


__all__ = ["JsonFormatter", "configure_logging", "get_logger"]
