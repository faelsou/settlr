"""Aplica as decisões do matcher no banco: baixa, match provisório ou exceção."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, event, or_, select
from sqlalchemy.orm import Session

from app.channels.queue_notice import notify_human_queue
from app.core.audit import audit
from app.core.logging import get_logger
from app.core.redis import redis_lock
from app.models import Debtor, Invoice, Match, Payment, Promise, ReviewException, Tenant
from app.models.enums import (
    OPEN_INVOICE_STATUSES,
    ExceptionStatus,
    ExceptionType,
    InvoiceStatus,
    MatchMethod,
    PaymentOrigin,
    PaymentStatus,
)
from app.models.states import check_invoice, check_payment
from app.reconciliation.matcher import (
    Allocation,
    Decision,
    InvoiceCandidate,
    MatchResult,
    PaymentData,
    ReconciliationRules,
    document_matches,
    match_payment,
)

log = get_logger(__name__)

DECISION_TO_EXCEPTION = {
    Decision.SUGGESTION: ExceptionType.SUGESTAO_MATCH,
    Decision.AMOUNT_MISMATCH: ExceptionType.DIFERENCA_VALOR,
    Decision.UNIDENTIFIED: ExceptionType.PAGAMENTO_NAO_IDENTIFICADO,
}


def set_payment_status(payment: Payment, new: PaymentStatus) -> None:
    check_payment(payment.status, new)
    payment.status = new


def set_invoice_status(invoice: Invoice, new: InvoiceStatus) -> None:
    check_invoice(invoice.status, new)
    invoice.status = new


def load_candidates(
    session: Session, payment: Payment, rules: ReconciliationRules
) -> list[InvoiceCandidate]:
    paid_on = payment.paid_at.date()
    window = (
        Invoice.due_date.between(
            paid_on - timedelta(days=rules.days_after_due),
            paid_on + timedelta(days=rules.days_before_due),
        )
    )
    filters = [window]
    if payment.txid or payment.e2e_id:
        filters.append(Invoice.txid.in_([k for k in (payment.txid, payment.e2e_id) if k]))
    if payment.debtor_id:
        filters.append(Invoice.debtor_id == payment.debtor_id)

    rows = session.execute(
        select(Invoice, Debtor)
        .join(Debtor, Debtor.id == Invoice.debtor_id)
        .where(Invoice.tenant_id == payment.tenant_id)
        .where(Invoice.status.in_(OPEN_INVOICE_STATUSES))
        .where(or_(*filters))
    ).all()

    return [
        InvoiceCandidate(
            id=inv.id,
            debtor_id=inv.debtor_id,
            amount_open=inv.amount_open,
            due_date=inv.due_date,
            debtor_doc=debtor.document,
            debtor_name=debtor.name,
            txid=inv.txid,
        )
        for inv, debtor in rows
    ]


def to_payment_data(payment: Payment) -> PaymentData:
    return PaymentData(
        amount=payment.amount,
        paid_on=payment.paid_at.date(),
        e2e_id=payment.e2e_id,
        txid=payment.txid,
        payer_doc=payment.payer_doc,
        payer_name=payment.payer_name,
        debtor_id=payment.debtor_id,
    )


def _schedule_issuer_settlement(session: Session, tenant_id: UUID, invoice_id: UUID) -> None:
    """A fila do cadastro marca a cobrança no emissor só depois que a baixa commitou."""
    pending = session.info.setdefault("issuer_settle", [])
    key = (str(tenant_id), str(invoice_id))
    if key not in pending:
        pending.append(key)
    if session.info.get("issuer_settle_hook"):
        return
    session.info["issuer_settle_hook"] = True

    def _after_commit(sess: Session) -> None:
        by_tenant: dict[str, list[str]] = {}
        for tid, iid in sess.info.get("issuer_settle") or []:
            bucket = by_tenant.setdefault(tid, [])
            if iid not in bucket:
                bucket.append(iid)
        if not by_tenant:
            return
        try:
            from app.ingest.tasks import settle_issuer_charges

            for tid, ids in by_tenant.items():
                settle_issuer_charges.delay(tid, ids)
        except Exception:
            log.exception("issuer.settle_enqueue_failed", tenant_id=str(tenant_id))

    event.listen(session, "after_commit", _after_commit, once=True)


def _fulfil_promises(session: Session, invoice: Invoice, today: date) -> None:
    pending = session.scalars(
        select(Promise).where(Promise.invoice_id == invoice.id, Promise.fulfilled.is_(None))
    ).all()
    for promise in pending:
        promise.fulfilled = today <= promise.promised_date + timedelta(days=1)
        promise.checked_at = datetime.now(UTC)


def apply_allocations(
    session: Session,
    payment: Payment,
    allocations: list[Allocation],
    method: MatchMethod,
    score: float,
    actor: str,
) -> None:
    """Baixa definitiva. Exige pagamento confirmado pelo banco."""
    if payment.bank_confirmed_at is None:
        raise ValueError("baixa definitiva exige confirmação do banco")

    session.execute(delete(Match).where(Match.payment_id == payment.id, Match.provisional.is_(True)))
    remaining = payment.amount
    today = datetime.now(UTC).date()

    for alloc in allocations:
        invoice = session.scalars(
            select(Invoice).where(Invoice.id == alloc.invoice_id).with_for_update()
        ).one()
        applied = min(alloc.amount, invoice.amount_open, remaining)
        if applied <= 0:
            continue
        before = {"status": invoice.status, "amount_paid": invoice.amount_paid}
        invoice.amount_paid += applied
        remaining -= applied
        if invoice.amount_open <= 0:
            set_invoice_status(invoice, InvoiceStatus.PAGO)
            _fulfil_promises(session, invoice, today)
            _schedule_issuer_settlement(session, payment.tenant_id, invoice.id)
        else:
            set_invoice_status(invoice, InvoiceStatus.PARCIALMENTE_PAGO)

        session.add(
            Match(
                tenant_id=payment.tenant_id,
                payment_id=payment.id,
                invoice_id=invoice.id,
                amount_applied=applied,
                method=method,
                score=score,
                provisional=False,
                confirmed_by=actor,
            )
        )
        audit(
            session, tenant_id=payment.tenant_id, actor=actor, action="baixa",
            entity="invoice", entity_id=invoice.id, before=before,
            after={"status": invoice.status, "amount_paid": invoice.amount_paid,
                   "payment_id": payment.id, "method": method},
        )

    set_payment_status(payment, PaymentStatus.CONCILIADO)


def open_exception(
    session: Session,
    tenant_id: UUID,
    type_: ExceptionType,
    *,
    payment_id: UUID | None = None,
    invoice_id: UUID | None = None,
    conversation_id: UUID | None = None,
    details: dict | None = None,
) -> ReviewException:
    exc = ReviewException(
        tenant_id=tenant_id,
        type=type_,
        status=ExceptionStatus.ABERTA,
        payment_id=payment_id,
        invoice_id=invoice_id,
        conversation_id=conversation_id,
        details=details or {},
    )
    session.add(exc)
    session.flush()
    audit(
        session, tenant_id=tenant_id, actor="sistema", action="abre_excecao",
        entity="exception", entity_id=exc.id, after={"type": type_, **(details or {})},
    )
    kind = type_.value if isinstance(type_, ExceptionType) else str(type_)
    notify_human_queue(
        session, tenant_id=tenant_id, kind=kind, entity="exception",
        entity_id=exc.id, opened_at=exc.created_at,
    )
    return exc


def _provisional(session: Session, payment: Payment, result: MatchResult) -> None:
    session.execute(delete(Match).where(Match.payment_id == payment.id, Match.provisional.is_(True)))
    for alloc in result.allocations:
        session.add(
            Match(
                tenant_id=payment.tenant_id,
                payment_id=payment.id,
                invoice_id=alloc.invoice_id,
                amount_applied=alloc.amount,
                method=result.method,
                score=result.score,
                provisional=True,
            )
        )


def reconcile_payment(session: Session, payment: Payment, tenant: Tenant) -> MatchResult:
    rules = ReconciliationRules.from_json(tenant.reconciliation_rules)
    result = match_payment(to_payment_data(payment), load_candidates(session, payment, rules), rules)

    if payment.status == PaymentStatus.AGUARDANDO_BANCO:
        # Comprovante sem banco nunca baixa: só indica o título provável no painel.
        if result.decision in (Decision.AUTO, Decision.PARTIAL):
            _provisional(session, payment, result)
        return result

    if payment.status != PaymentStatus.CONFIRMADO:
        return result

    with redis_lock(f"payment:{payment.id}"):
        if result.decision in (Decision.AUTO, Decision.PARTIAL):
            apply_allocations(session, payment, result.allocations, result.method, result.score, "sistema")
        else:
            set_payment_status(payment, PaymentStatus.EM_EXCECAO)
            open_exception(
                session, payment.tenant_id, DECISION_TO_EXCEPTION[result.decision],
                payment_id=payment.id,
                details={"reason": result.reason, "layer": result.layer,
                         "suggestions": result.suggestions},
            )
    return result


@dataclass(frozen=True)
class BankPaymentIn:
    amount: Decimal
    paid_at: datetime
    e2e_id: str | None = None
    txid: str | None = None
    payer_doc: str | None = None
    payer_name: str | None = None
    payer_bank: str | None = None
    raw: dict | None = None


def _find_receipt_twin(session: Session, tenant_id: UUID, data: BankPaymentIn) -> Payment | None:
    """Comprovante sem E2E aguardando banco com mesmo valor, data próxima e documento."""
    candidates = session.scalars(
        select(Payment).where(
            Payment.tenant_id == tenant_id,
            Payment.status == PaymentStatus.AGUARDANDO_BANCO,
            Payment.e2e_id.is_(None),
            Payment.amount == data.amount,
            Payment.paid_at.between(data.paid_at - timedelta(days=1), data.paid_at + timedelta(days=1)),
        )
    ).all()
    if data.payer_doc:
        candidates = [
            p for p in candidates
            if p.payer_doc and (document_matches(p.payer_doc, data.payer_doc)
                                or document_matches(data.payer_doc, p.payer_doc))
        ]
    return candidates[0] if len(candidates) == 1 else None


def register_bank_payment(
    session: Session, tenant_id: UUID, data: BankPaymentIn, origin: PaymentOrigin
) -> Payment | None:
    """Registra entrada vinda do banco/emissor. Se já existe comprovante do mesmo
    pagamento, confirma o comprovante em vez de criar outro registro. Devolve None
    quando é reenvio de algo já registrado pelo banco."""
    now = datetime.now(UTC)
    lock_key = f"bank:{tenant_id}:{data.e2e_id or data.txid or f'{data.amount}:{data.paid_at:%Y%m%d%H%M}'}"

    with redis_lock(lock_key):
        existing = None
        if data.e2e_id:
            existing = session.scalars(
                select(Payment).where(Payment.tenant_id == tenant_id, Payment.e2e_id == data.e2e_id)
            ).first()
        if existing is None:
            existing = _find_receipt_twin(session, tenant_id, data)

        if existing is not None:
            if existing.bank_confirmed_at is not None:
                return None
            set_payment_status(existing, PaymentStatus.CONFIRMADO)
            existing.bank_confirmed_at = now
            existing.e2e_id = existing.e2e_id or data.e2e_id
            existing.txid = existing.txid or data.txid
            existing.raw = {**existing.raw, "bank": data.raw or {}}
            audit(session, tenant_id=tenant_id, actor="sistema", action="confirma_comprovante",
                  entity="payment", entity_id=existing.id, after={"origin": origin})
            return existing

        payment = Payment(
            tenant_id=tenant_id,
            origin=origin,
            status=PaymentStatus.CONFIRMADO,
            amount=data.amount,
            paid_at=data.paid_at,
            e2e_id=data.e2e_id,
            txid=data.txid,
            payer_doc=data.payer_doc,
            payer_name=data.payer_name,
            payer_bank=data.payer_bank,
            bank_confirmed_at=now,
            raw=data.raw or {},
        )
        session.add(payment)
        session.flush()
        audit(session, tenant_id=tenant_id, actor="sistema", action="registra_pagamento",
              entity="payment", entity_id=payment.id,
              after={"origin": origin, "amount": data.amount, "e2e_id": data.e2e_id})
        return payment
