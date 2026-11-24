"""Logs: one JSON line per event, on standard output, for the platform to collect.

Logged: what happened, the trace id, the decision, the score, the names of the reasons, and
how long it took. Never logged: the payment's values (amount, V1 to V28, timestamp), the
reasons' values, or any secret.

A safety net on top: every line passes through MaskingRenderer, which hides the value of any
field whose name sounds secret (token, secret, password, authorization) and any occurrence of
a known secret value, wherever it appears in the line.
"""
import logging
import re
from collections.abc import MutableMapping, Sequence
from typing import Any

import structlog

SECRET_NAMES = re.compile(r"token|secret|password|authorization|api_?key", re.IGNORECASE)
HIDDEN = "[hidden]"


class MaskingRenderer:
    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self.secrets = [secret for secret in secrets if secret]
        self.render = structlog.processors.JSONRenderer()

    def __call__(self, logger: Any, method: str, event: MutableMapping[str, Any]) -> str:
        for name in event:
            if SECRET_NAMES.search(name):
                event[name] = HIDDEN
        line = str(self.render(logger, method, event))
        for secret in self.secrets:
            line = line.replace(secret, HIDDEN)
        return line


def configure(level: str, secrets: Sequence[str] = ()) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,     # adds the request's trace_id
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            MaskingRenderer(secrets),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
