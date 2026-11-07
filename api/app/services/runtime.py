from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.metrics import install_metrics


@asynccontextmanager
async def _flush_on_shutdown(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        from app.core.observability import flush_traces
        from app.core.tracing import shutdown_tracing

        shutdown_tracing()
        flush_traces()


def create_service(
    name: str,
    routers: Sequence[APIRouter],
    *,
    title: str | None = None,
    lifespan=None,
    cors: bool = False,
) -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title=title or f"Settlr — {name}",
        version="0.1.0",
        docs_url="/docs" if settings.env != "prod" else None,
        lifespan=lifespan or _flush_on_shutdown,
    )
    app.state.service_name = name
    if cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health.router)
    for router in routers:
        app.include_router(router)
    install_metrics(app, name)
    from app.core.tracing import instrument_app

    instrument_app(app, name)
    return app
