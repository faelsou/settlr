"""Webhooks públicos (sem sessão de usuário). Cada um verifica assinatura ou token."""

import hashlib
import hmac
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.channels.delivery import apply_delivery_updates, is_delivery_event, parse_delivery_updates
from app.channels.metrics import record_message
from app.channels.session import alert_session_down, connection_state, session_is_down
from app.channels.tasks import process_inbound
from app.channels.whatsapp import EvolutionWebhook, debounce_push, parse_inbound
from app.core.config import get_settings
from app.core.db import system_session, tenant_session
from app.ingest.tasks import handle_issuer_event
from app.models import Tenant
from app.models.enums import PaymentOrigin
from app.reconciliation.service import BankPaymentIn, register_bank_payment
from app.reconciliation.tasks import reconcile

evolution_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
issuer_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
bank_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _same(a: str | None, b: str) -> bool:
    return bool(a) and hmac.compare_digest(a.encode(), b.encode())


@evolution_router.post("/evolution", status_code=status.HTTP_202_ACCEPTED)
def evolution_webhook(
    payload: EvolutionWebhook,
    token: str | None = Query(default=None),
    x_webhook_token: str | None = Header(default=None),
) -> dict:
    if not _same(token or x_webhook_token, get_settings().webhook_hmac):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido")

    if connection_state(payload) is not None:
        return _apply_session_alert(payload)

    if is_delivery_event(payload):
        return _apply_delivery_receipt(payload)

    msg = parse_inbound(payload)
    if msg is None or msg.from_me:
        return {"status": "ignorado"}

    kind = "arquivo" if msg.has_media else "texto"
    with system_session() as session:
        tenant_id = _tenant_for_instance(session, msg.instance)
    if tenant_id is None:
        record_message("entrada", "aceita", "instancia_desconhecida", kind, "falha")
        return {"status": "instancia_desconhecida"}

    record_message("entrada", "aceita", "webhook", kind, "ok")
    buffer_key = debounce_push(str(tenant_id), msg)
    process_inbound.apply_async(
        args=[str(tenant_id), buffer_key], countdown=get_settings().inbound_debounce_seconds + 1
    )
    return {"status": "enfileirado"}


def _tenant_for_instance(session: Session, instance: str):
    needle = [{"instance": instance}]
    return session.scalar(
        select(Tenant.id).where(
            Tenant.active.is_(True),
            or_(
                Tenant.whatsapp_instance == instance,
                Tenant.whatsapp_senders.contains(needle),
            ),
        )
    )


def _apply_session_alert(payload: EvolutionWebhook) -> dict:
    state = connection_state(payload)
    if not session_is_down(state):
        return {"status": "sessao_ok"}
    data = payload.data if isinstance(payload.data, dict) else {}
    reason = data.get("statusReason", data.get("reason"))
    with system_session() as session:
        tenant_id = _tenant_for_instance(session, payload.instance)
    if tenant_id is None:
        return {"status": "instancia_desconhecida"}
    with tenant_session(tenant_id) as session:
        opened = alert_session_down(session, tenant_id, payload.instance, state or "close", reason)
    return {"status": "alerta_sessao", "opened": opened}


def _apply_delivery_receipt(payload: EvolutionWebhook) -> dict:
    updates = parse_delivery_updates(payload)
    if not updates:
        return {"status": "ignorado"}
    with system_session() as session:
        tenant_id = _tenant_for_instance(session, payload.instance)
    if tenant_id is None:
        return {"status": "instancia_desconhecida"}
    with tenant_session(tenant_id) as session:
        changed = apply_delivery_updates(session, updates)
    return {"status": "recibo", "updated": changed}


@issuer_router.post("/emissor", status_code=status.HTTP_202_ACCEPTED)
async def issuer_webhook(
    request: Request,
    asaas_access_token: str | None = Header(default=None),
    x_webhook_token: str | None = Header(default=None),
) -> dict:
    token = asaas_access_token or x_webhook_token
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token ausente")
    with system_session() as session:
        tenant_id = session.scalar(select(Tenant.id).where(Tenant.issuer_webhook_token == token))
    if tenant_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido")

    handle_issuer_event.delay(str(tenant_id), await request.json())
    return {"status": "enfileirado"}


class BankTransactionIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_at: datetime
    e2e_id: str | None = None
    txid: str | None = None
    payer_doc: str | None = None
    payer_name: str | None = None
    payer_bank: str | None = None


class BankWebhookIn(BaseModel):
    transactions: list[BankTransactionIn]


@bank_router.post("/banco", status_code=status.HTTP_202_ACCEPTED)
async def bank_webhook(
    request: Request,
    x_tenant_id: UUID = Header(),
    x_signature: str = Header(),
) -> dict:
    """Formato normalizado de extrato/PIX. Assinatura: HMAC-SHA256 do corpo, em hex."""
    body = await request.body()
    expected = hmac.new(get_settings().webhook_hmac.encode(), body, hashlib.sha256).hexdigest()
    if not _same(x_signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "assinatura inválida")

    data = BankWebhookIn.model_validate_json(body)
    created: list[str] = []
    with tenant_session(x_tenant_id) as session:
        for tx in data.transactions:
            raw = {"source": "webhook_banco", **tx.model_dump(mode="json")}
            payment = register_bank_payment(
                session, x_tenant_id,
                BankPaymentIn(**tx.model_dump(), raw=raw),
                PaymentOrigin.WEBHOOK,
            )
            if payment is not None:
                created.append(str(payment.id))

    for payment_id in created:
        reconcile.delay(str(x_tenant_id), payment_id)
    duplicates = len(data.transactions) - len(created)
    return {"status": "ok", "registered": len(created), "duplicates": duplicates}
