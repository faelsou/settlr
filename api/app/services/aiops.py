"""AIOps: recebe o Alertmanager, diagnostica e conversa no Slack.

Fora do gateway e fora do domínio de falha da aplicação: não usa o Postgres nem
o Redis da cobrança, e o /health dele não depende deles.
"""

import hmac
import json
import threading
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from app.aiops.config import get_aiops_settings
from app.aiops.engine import Engine
from app.aiops.models import AlertmanagerPayload
from app.aiops.slack import start_socket_mode, verify_signature
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import install_metrics
from app.core.tracing import instrument_app

log = get_logger(__name__)


def _watch_loop(engine: Engine, stop: threading.Event) -> None:
    while not stop.wait(2):
        engine.watch_once()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.engine = Engine()
    app.state.socket = start_socket_mode(app.state.engine.dispatch)
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_loop, args=(app.state.engine, stop), name="aiops-watch", daemon=True
    )
    watcher.start()
    try:
        yield
    finally:
        stop.set()
        if app.state.socket is not None:
            app.state.socket.close()
        app.state.engine.shutdown()
        from app.core.tracing import shutdown_tracing

        shutdown_tracing()


configure_logging()
app = FastAPI(
    title="Settlr — aiops",
    version="0.1.0",
    docs_url="/docs" if get_settings().env != "prod" else None,
    lifespan=_lifespan,
)
app.state.service_name = "aiops"
install_metrics(app, "aiops")


def _engine(request: Request) -> Engine:
    return request.app.state.engine


@app.get("/health", tags=["infra"])
def health(request: Request) -> dict:
    settings = get_aiops_settings()
    engine = _engine(request)
    if settings.slack_app_token:
        slack = "socket"
    elif settings.slack_signing_secret:
        slack = "http"
    else:
        slack = "off"
    return {
        "service": "aiops",
        "slack": slack if settings.slack_enabled else "off",
        "llm": "on" if get_settings().llm_api_key else "off",
        "kubernetes": "on" if engine.sources.kube.enabled else "off",
        "dry_run": settings.aiops_dry_run,
        "incidentes_abertos": len(engine.store.open_incidents()),
    }


@app.post("/aiops/alertmanager", status_code=status.HTTP_202_ACCEPTED, tags=["aiops"])
def alertmanager(
    payload: AlertmanagerPayload, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    expected = get_aiops_settings().aiops_webhook_token
    if expected:
        given = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), expected.encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido")
    elif get_settings().env != "dev":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AIOPS_WEBHOOK_TOKEN ausente")
    return _engine(request).handle_alerts(payload)


async def _verified_body(request: Request) -> bytes:
    body = await request.body()
    if not verify_signature(
        body,
        request.headers.get("x-slack-request-timestamp"),
        request.headers.get("x-slack-signature"),
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "assinatura do Slack inválida")
    return body


@app.post("/slack/events", tags=["slack"])
async def slack_events(request: Request) -> Response:
    body = await _verified_body(request)
    payload = json.loads(body)
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload["challenge"]})
    # O Slack reenvia se o ack passar de 3s; o primeiro envio já foi tratado.
    if request.headers.get("x-slack-retry-num"):
        return Response(status_code=200)
    _engine(request).dispatch("events_api", payload)
    return Response(status_code=200)


@app.post("/slack/interactions", tags=["slack"])
async def slack_interactions(request: Request) -> Response:
    body = await _verified_body(request)
    payload = json.loads(parse_qs(body.decode())["payload"][0])
    _engine(request).dispatch("interactive", payload)
    return Response(status_code=200)


@app.post("/slack/commands", tags=["slack"])
async def slack_commands(request: Request) -> JSONResponse:
    body = await _verified_body(request)
    form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
    return JSONResponse(_engine(request).dispatch("slash_commands", form) or {})


instrument_app(app, "aiops")
