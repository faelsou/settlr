"""OTLP para o coletor: traces, métricas e logs.

Desligado se `OTEL_EXPORTER_OTLP_ENDPOINT` estiver vazio.
Falha ao exportar não derruba cobrança nem conciliação.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_provider = None
_meter_provider = None
_logger_provider = None
_http_clients = False

_SKIP_LOG_KEYS = frozenset({"event", "exc_info", "exception"})


def tracing_enabled() -> bool:
    return _provider is not None


def setup_tracing(service: str) -> bool:
    """Liga traces, métricas e logs uma vez por processo.

    O nome vem de `SERVICE_NAME` ou do argumento. Os três sinais usam o mesmo endpoint gRPC.
    """
    global _provider, _meter_provider, _logger_provider
    settings = get_settings()
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return False
    if _provider is not None:
        return True
    name = os.environ.get("SERVICE_NAME") or service
    try:
        _provider, _meter_provider, _logger_provider = _start(endpoint, name, settings.env)
    except Exception:
        logger.warning("otel desligado: falha ao iniciar", exc_info=True)
        _provider = None
        _meter_provider = None
        _logger_provider = None
        return False
    logger.info("otel ligado", extra={"service": name, "endpoint": endpoint})
    return True


def shutdown_tracing() -> None:
    global _provider, _meter_provider, _logger_provider
    for provider in (_provider, _meter_provider, _logger_provider):
        if provider is None:
            continue
        try:
            provider.shutdown()
        except Exception:
            logger.warning("otel: falha ao encerrar", exc_info=True)
    _provider = None
    _meter_provider = None
    _logger_provider = None


def add_trace_ids(_logger, _method, event_dict: dict) -> dict:
    """Coloca `trace_id` no log para o Grafana abrir o trace no Tempo."""
    span = trace.get_current_span()
    context = span.get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict


def emit_log(method: str, event_dict: dict) -> None:
    """Encaminha o structlog ao coletor. Sem provider, não faz nada."""
    provider = _logger_provider
    if provider is None:
        return
    try:
        from opentelemetry._logs import get_logger
        from opentelemetry.context import get_current

        body = event_dict.get("event", "")
        if not isinstance(body, str):
            body = str(body)
        trace_id = event_dict.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            body = f"{body} trace_id={trace_id}"
        attributes: dict[str, str | int | float | bool] = {}
        for key, value in event_dict.items():
            if key in _SKIP_LOG_KEYS:
                continue
            parsed = _log_attribute(value)
            if parsed is None:
                continue
            attributes[str(key)] = parsed
        get_logger("app", logger_provider=provider).emit(
            body=body,
            severity_number=_severity(method),
            severity_text=method.upper(),
            attributes=attributes,
            context=get_current(),
            exception=_exception(event_dict.get("exc_info")),
        )
    except Exception:
        return


def _severity(method: str):
    from opentelemetry._logs import SeverityNumber

    return {
        "debug": SeverityNumber.DEBUG,
        "info": SeverityNumber.INFO,
        "warning": SeverityNumber.WARN,
        "warn": SeverityNumber.WARN,
        "error": SeverityNumber.ERROR,
        "exception": SeverityNumber.ERROR,
        "critical": SeverityNumber.FATAL,
        "fatal": SeverityNumber.FATAL,
    }.get(method, SeverityNumber.INFO)


def _exception(value: object) -> BaseException | None:
    if isinstance(value, BaseException):
        return value
    if isinstance(value, tuple) and len(value) > 1 and isinstance(value[1], BaseException):
        return value[1]
    return None


def _log_attribute(value: object) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value if len(value) <= 4096 else value[:4096]
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= 4096 else text[:4096]


def _otlp_target(endpoint: str) -> tuple[str, bool]:
    insecure = endpoint.startswith("http://")
    target = endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")
    return target, insecure


def _start(endpoint: str, service: str, environment: str):
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    target, insecure = _otlp_target(endpoint)
    resource = Resource.create(
        {
            "service.name": service,
            # O Loki indexa `service` e o painel filtra por esse label (o Promtail usa o mesmo).
            "service": service,
            "deployment.environment": environment,
            "deployment.environment.name": environment,
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=target, insecure=insecure))
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=target, insecure=insecure),
                export_interval_millis=15000,
            )
        ],
    )
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=target, insecure=insecure))
    )
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    set_logger_provider(logger_provider)
    _instrument_clients()
    return tracer_provider, meter_provider, logger_provider


async def _async_redact(span, _request) -> None:  # noqa: ANN001
    from app.core.redact import redact_span

    redact_span(span)


def _instrument_clients() -> None:
    global _http_clients
    if _http_clients:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        from app.core.redact import redact_span

        HTTPXClientInstrumentor().instrument(
            request_hook=lambda span, _request: redact_span(span),
            async_request_hook=_async_redact,
        )
    except Exception:
        logger.warning("tracing: httpx sem instrumentação", exc_info=True)
    _http_clients = True


def instrument_app(app, service: str) -> None:
    if not setup_tracing(service):
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from app.core.redact import redact_span

        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="health,internal/metrics",
            server_request_hook=lambda span, _scope: redact_span(span),
        )
    except Exception:
        logger.warning("tracing: fastapi sem instrumentação", exc_info=True)


def instrument_celery(service: str) -> None:
    if not setup_tracing(service):
        return
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except Exception:
        logger.warning("tracing: celery sem instrumentação", exc_info=True)
