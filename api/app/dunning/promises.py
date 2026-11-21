"""Promessas de pagamento (FLUXOS.md §8)."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.policy import NegotiationPolicy, validate_promise_date
from app.core.audit import audit
from app.models import Invoice, Promise, Tenant
from app.models.enums import InvoiceStatus
from app.reconciliation.service import set_invoice_status

PROMISABLE = (InvoiceStatus.EM_COBRANCA, InvoiceStatus.ABERTO, InvoiceStatus.PARCIALMENTE_PAGO,
              InvoiceStatus.PROMESSA)


class PromiseRejected(ValueError):
    pass


def register_promise(
    session: Session, tenant: Tenant, debtor_id: UUID, promised: date, today: date, actor: str
) -> list[Promise]:
    """Registra a promessa para os títulos vencidos do devedor e pausa a régua."""
    reason = validate_promise_date(
        promised, today, NegotiationPolicy.from_json(tenant.negotiation_policy)
    )
    if reason:
        raise PromiseRejected(reason)

    invoices = session.scalars(
        select(Invoice).where(
            Invoice.debtor_id == debtor_id,
            Invoice.status.in_(PROMISABLE),
            Invoice.due_date <= promised,
        )
    ).all()

    promises = []
    for invoice in invoices:
        promise = Promise(tenant_id=tenant.id, invoice_id=invoice.id, promised_date=promised)
        session.add(promise)
        promises.append(promise)
        set_invoice_status(invoice, InvoiceStatus.PROMESSA)
        audit(session, tenant_id=tenant.id, actor=actor, action="registra_promessa",
              entity="invoice", entity_id=invoice.id, after={"promised_date": promised})
    return promises
