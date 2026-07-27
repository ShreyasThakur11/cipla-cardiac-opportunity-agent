"""Structured logging.

Agent runs are audited after the fact: which tools fired, what the guardrails
decided, how long each stage took. Plain text loses that. Every log line here
is a JSON object with a stable set of keys, so a run can be replayed from the
log alone.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

from .config import get_settings

#: Correlates every log line emitted while handling one question.
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")

_CONFIGURED = False


def _inject_trace_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Stamp every line with the id of the run that produced it.

    structlog types a processor's event dict as a MutableMapping rather than a
    dict, so annotating it as dict makes this an invalid processor.
    """
    event_dict.setdefault("trace_id", trace_id_var.get())
    return event_dict


def configure_logging(level: str | None = None, *, force: bool = False) -> None:
    """Install the structlog pipeline. Idempotent unless ``force`` is set."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    resolved = (level or get_settings().log_level or "INFO").upper()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, resolved, logging.INFO),
        force=True,
    )
    # The HTTP client libraries are chatty at DEBUG and drown the agent trace.
    for noisy in ("httpx", "httpcore", "urllib3", "anthropic"):
        logging.getLogger(noisy).setLevel(max(logging.INFO, getattr(logging, resolved, 20)))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_trace_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, resolved, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> Any:
    """Return a bound structlog logger, configuring the pipeline on first use."""
    configure_logging()
    return structlog.get_logger(name)


def new_trace_id() -> str:
    """Start a new correlation scope and return its identifier."""
    trace = uuid.uuid4().hex[:12]
    trace_id_var.set(trace)
    return trace


def current_trace_id() -> str:
    """The correlation identifier for the work in flight."""
    return trace_id_var.get()


__all__ = [
    "configure_logging",
    "current_trace_id",
    "get_logger",
    "new_trace_id",
]
