"""Única porta pública da API. Auth fica aqui; o resto segue para o serviço dono."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.api.routes import auth
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.routing import owner_of
from app.services.runtime import create_service

log = get_logger(__name__)

# Hop-by-hop. content-length e content-encoding saem porque o httpx já decodificou o corpo.
_DROP = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "content-encoding",
})


def _base_url(owner: str) -> str:
    settings = get_settings()
    urls = {
        "cobranca": settings.cobranca_url,
        "conciliacao": settings.conciliacao_url,
        "cadastro": settings.cadastro_url,
    }
    return urls[owner].rstrip("/")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))
    try:
        yield
    finally:
        await app.state.http.aclose()
        from app.core.observability import flush_traces
        from app.core.tracing import shutdown_tracing

        shutdown_tracing()
        flush_traces()


app = create_service(
    "gateway",
    [auth.router],
    title="Settlr",
    lifespan=_lifespan,
    cors=True,
)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy(path: str, request: Request) -> Response:
    owner = owner_of("/" + path)
    if owner is None:
        return JSONResponse({"detail": "não encontrado"}, status_code=404)

    url = _base_url(owner) + request.url.path
    if request.url.query:
        url = f"{url}?{request.url.query}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
    body = await request.body()
    try:
        upstream = await request.app.state.http.request(
            request.method, url, headers=headers, content=body
        )
    except httpx.HTTPError:
        log.warning("gateway.upstream_down", owner=owner, path=request.url.path)
        return JSONResponse({"detail": f"serviço {owner} indisponível"}, status_code=503)

    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _DROP}
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=resp_headers,
    )
