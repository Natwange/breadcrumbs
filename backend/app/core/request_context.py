"""Request-scoped context (request IDs) for structured logging.

A ``contextvar`` carries the current request id through the async call stack so
any log record emitted while handling a request is automatically tagged with
it. A logging filter injects the value onto every ``LogRecord``.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None) -> None:
    request_id_var.set(request_id)


def get_request_id() -> str | None:
    return request_id_var.get()


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record.

    Ensures ``record.request_id`` always exists so formatters can rely on it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True
