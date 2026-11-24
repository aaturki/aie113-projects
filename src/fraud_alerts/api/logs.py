"""Logs: one JSON line per event, on standard output, for the platform to collect.

Logged: what happened, the trace id, the decision, the score, the names of the reasons, and
how long it took. Never logged: the payment's values (amount, V1 to V28, timestamp), the
reasons' values, or any secret.
"""
import logging

import structlog


def configure(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,     # adds the request's trace_id
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
