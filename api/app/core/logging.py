import logging
import sys

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _trace_ids,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            _otel_logs,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    from app.core.redact import install_access_log_filter

    install_access_log_filter()

    from app.core.observability import init_sentry

    init_sentry()


def _trace_ids(logger, method, event_dict):  # noqa: ANN001
    from app.core.tracing import add_trace_ids

    return add_trace_ids(logger, method, event_dict)


def _otel_logs(_logger, method, event_dict):  # noqa: ANN001
    from app.core.tracing import emit_log

    emit_log(method, event_dict)
    return event_dict


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
