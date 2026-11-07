"""Cobrança: conversa, agente, régua e o webhook do WhatsApp."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import approvals, conversations
from app.api.routes.webhooks import evolution_router
from app.services.runtime import create_service


async def _pull_replies(stop: asyncio.Event) -> None:
    from app.channels.inbound_sync import pull_unseen_replies
    from app.channels.reconcile import reconcile_outbound
    from app.core.logging import get_logger

    log = get_logger(__name__)
    while not stop.is_set():
        try:
            await asyncio.to_thread(pull_unseen_replies)
        except Exception:
            log.exception("inbound.sync_failed")
        try:
            await asyncio.to_thread(reconcile_outbound)
        except Exception:
            log.exception("outbound.reconcile_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=8)
        except TimeoutError:
            continue


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    stop = asyncio.Event()
    task = None
    from app.channels.reconcile import reconciliation_enabled

    if reconciliation_enabled():
        task = asyncio.create_task(_pull_replies(stop))
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            await task
        from app.core.observability import flush_traces
        from app.core.tracing import shutdown_tracing

        shutdown_tracing()
        flush_traces()


app = create_service(
    "cobranca",
    [evolution_router, conversations.router, approvals.router],
    lifespan=_lifespan,
)
