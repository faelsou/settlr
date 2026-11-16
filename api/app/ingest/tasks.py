from uuid import UUID

import httpx

from app.core.db import tenant_session
from app.core.logging import get_logger
from app.ingest.issuers import get_adapter
from app.ingest.schemas import InvoiceIn
from app.ingest.service import import_invoices, upsert_invoice
from app.ingest.settlement import plan_issuer_settlements, record_issuer_settlement
from app.models import Tenant
from app.models.enums import PaymentOrigin
from app.reconciliation.service import register_bank_payment
from app.reconciliation.tasks import reconcile
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.ingest.tasks.import_invoices")
def import_invoices_task(tenant_id: str, rows: list[dict], actor: str) -> dict:
    invoices = [InvoiceIn(**row) for row in rows]
    with tenant_session(UUID(tenant_id)) as session:
        result = import_invoices(session, UUID(tenant_id), invoices, actor)
    log.info("ingest.done", tenant_id=tenant_id, created=result.created, updated=result.updated)
    return result.model_dump()


@celery_app.task(
    name="app.ingest.tasks.handle_issuer_event",
    autoretry_for=(httpx.TransportError,), retry_backoff=True, max_retries=5,
)
def handle_issuer_event(tenant_id: str, body: dict | list) -> str:
    tid = UUID(tenant_id)
    payment_ids: list[str] = []
    outcomes: list[str] = []
    with tenant_session(tid) as session:
        tenant = session.get(Tenant, tid)
        if tenant is None:
            raise ValueError("tenant ausente")
        adapter = get_adapter(tenant.issuer_provider, tenant.issuer_config or {})
        for parsed in adapter.events(body):
            if isinstance(parsed, InvoiceIn):
                upsert_invoice(session, tid, parsed, actor=f"emissor:{tenant.issuer_provider}")
                outcomes.append("invoice")
                continue
            payment = register_bank_payment(session, tid, parsed, PaymentOrigin.WEBHOOK)
            if payment is None:
                outcomes.append("duplicate")
            else:
                payment_ids.append(str(payment.id))
                outcomes.append("payment")

    for payment_id in payment_ids:
        reconcile.delay(tenant_id, payment_id)
    if not outcomes:
        return "ignored"
    return outcomes[0] if len(outcomes) == 1 else ",".join(outcomes)


@celery_app.task(
    name="app.ingest.tasks.settle_issuer_charges",
    autoretry_for=(httpx.TransportError,),
    retry_backoff=True,
    max_retries=5,
)
def settle_issuer_charges(tenant_id: str, invoice_ids: list[str]) -> str:
    """Depois da baixa no Settlr, marca a cobrança como paga no emissor do piloto."""
    tid = UUID(tenant_id)
    ids = [UUID(invoice_id) for invoice_id in invoice_ids]
    with tenant_session(tid) as session:
        tenant = session.get(Tenant, tid)
        if tenant is None or not tenant.issuer_provider:
            return "sem_emissor"
        provider = tenant.issuer_provider
        config = dict(tenant.issuer_config or {})
        work, skipped = plan_issuer_settlements(session, tenant, ids)
        for invoice_id, reason in skipped:
            record_issuer_settlement(
                session, tid, invoice_id, charge_id=None, result=reason,
            )

    outcomes: list[str] = [reason for _, reason in skipped]
    if not work:
        log.info("issuer.settled", tenant_id=tenant_id, results=outcomes)
        return ",".join(outcomes) if outcomes else "nada"

    adapter = get_adapter(provider, config)
    done: list[tuple] = []
    for item in work:
        status = adapter.mark_paid(item.charge_id, item.paid_on, item.value)
        done.append((item, "paga" if status == "paid" else "ja_recebida"))

    with tenant_session(tid) as session:
        for item, status in done:
            record_issuer_settlement(
                session, tid, item.invoice_id, charge_id=item.charge_id, result=status,
                paid_on=item.paid_on, value=item.value,
            )
    outcomes.extend(status for _, status in done)
    log.info("issuer.settled", tenant_id=tenant_id, results=outcomes)
    return ",".join(outcomes)
