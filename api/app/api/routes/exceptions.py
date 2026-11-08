"""Fila de exceções (FLUXOS.md §11). Toda decisão humana passa por aqui e vai ao audit_log."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.routes.payments import payments_out
from app.api.schemas import ConfirmExceptionIn, ExceptionOut, Page, RejectExceptionIn
from app.core import storage
from app.core.audit import audit
from app.core.roles import can_settle
from app.models import Invoice, Payment, ReviewException, Tenant
from app.models.enums import (
    ExceptionStatus,
    ExceptionType,
    InvoiceStatus,
    MatchMethod,
    PaymentOrigin,
    PaymentStatus,
)
from app.reconciliation.matcher import Allocation
from app.reconciliation.service import (
    apply_allocations,
    open_exception,
    reconcile_payment,
    set_invoice_status,
    set_payment_status,
)

router = APIRouter(prefix="/exceptions", tags=["excecoes"])

PAYMENT_TYPES = {
    ExceptionType.SUGESTAO_MATCH,
    ExceptionType.PAGAMENTO_NAO_IDENTIFICADO,
    ExceptionType.DIFERENCA_VALOR,
}


def _out(db: Session, items: list[ReviewException]) -> list[ExceptionOut]:
    payment_ids = [e.payment_id for e in items if e.payment_id]
    payments = {}
    if payment_ids:
        loaded = db.scalars(select(Payment).where(Payment.id.in_(payment_ids))).all()
        payments = {p.id: p for p in payments_out(db, list(loaded))}
    return [
        ExceptionOut(
            id=e.id, type=e.type, status=e.status, payment=payments.get(e.payment_id),
            invoice_id=e.invoice_id, conversation_id=e.conversation_id, details=e.details,
            assignee=e.assignee, resolution=e.resolution, created_at=e.created_at,
            resolved_at=e.resolved_at,
        )
        for e in items
    ]


def _get_open(db: Session, exception_id: UUID) -> ReviewException:
    exc = db.scalars(
        select(ReviewException).where(ReviewException.id == exception_id).with_for_update()
    ).first()
    if exc is None:
        raise HTTPException(404, "exceção não encontrada")
    if exc.status != ExceptionStatus.ABERTA:
        raise HTTPException(409, "exceção já tratada")
    return exc


def _close(db: Session, exc: ReviewException, status: ExceptionStatus, user: CurrentUser, note: str | None):
    exc.status = status
    exc.assignee = user.email
    exc.resolution = note
    exc.resolved_at = datetime.now(UTC)
    audit(db, tenant_id=exc.tenant_id, actor=user.actor, action=f"excecao_{status}",
          entity="exception", entity_id=exc.id, after={"type": exc.type, "note": note})


@router.get("", response_model=Page[ExceptionOut])
def list_exceptions(
    status: ExceptionStatus = ExceptionStatus.ABERTA,
    type: ExceptionType | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Page[ExceptionOut]:
    query = select(ReviewException).where(ReviewException.status == status)
    if type:
        query = query.where(ReviewException.type == type)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(ReviewException.created_at).limit(limit).offset(offset)).all()
    return Page(items=_out(db, list(items)), total=total or 0)


@router.get("/{exception_id}/file")
def get_exception_file(exception_id: UUID, db: Session = Depends(get_db)) -> Response:
    """Arquivo do comprovante que a leitura não conseguiu promover a pagamento."""
    exc = db.get(ReviewException, exception_id)
    if exc is None:
        raise HTTPException(404, "exceção não encontrada")
    key = (exc.details or {}).get("file_key")
    if not key:
        raise HTTPException(404, "comprovante não encontrado")
    content_type = (exc.details or {}).get("content_type") or "application/octet-stream"
    return Response(storage.get_object(key), media_type=content_type)


@router.post("/{exception_id}/confirm", response_model=ExceptionOut)
def confirm_exception(
    exception_id: UUID,
    body: ConfirmExceptionIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> ExceptionOut:
    exc = _get_open(db, exception_id)
    if exc.type in PAYMENT_TYPES and not can_settle(user.role):
        raise HTTPException(403, "atendente não confirma baixa")

    if exc.type in PAYMENT_TYPES:
        if not body.allocations:
            raise HTTPException(422, "informe os títulos para a baixa")
        payment = db.get(Payment, exc.payment_id)
        if payment.bank_confirmed_at is None:
            raise HTTPException(409, "pagamento ainda sem confirmação do banco")
        if sum(a.amount for a in body.allocations) > payment.amount:
            raise HTTPException(422, "valor alocado maior que o pagamento")
        apply_allocations(
            db, payment, [Allocation(a.invoice_id, a.amount) for a in body.allocations],
            MatchMethod.MANUAL, 1.0, user.actor,
        )

    elif exc.type == ExceptionType.LEITURA_BAIXA_CONFIANCA:
        if body.receipt is None:
            raise HTTPException(422, "informe os dados corrigidos do comprovante")
        details = exc.details
        payment = Payment(
            tenant_id=exc.tenant_id,
            origin=PaymentOrigin.COMPROVANTE,
            status=PaymentStatus.AGUARDANDO_BANCO,
            amount=body.receipt.amount,
            paid_at=body.receipt.paid_at,
            e2e_id=body.receipt.e2e_id,
            payer_doc=body.receipt.payer_doc,
            payer_name=body.receipt.payer_name,
            debtor_id=UUID(details["debtor_id"]) if details.get("debtor_id") else None,
            file_key=details.get("file_key"),
            content_type=details.get("content_type"),
            raw={"manual_review": user.email, "extraction": details.get("extraction")},
        )
        db.add(payment)
        db.flush()
        exc.payment_id = payment.id
        reconcile_payment(db, payment, db.get(Tenant, exc.tenant_id))

    elif exc.type == ExceptionType.CONTESTACAO:
        if body.contestation is None:
            raise HTTPException(422, "informe a favor de quem a contestação foi resolvida")
        new_status = (
            InvoiceStatus.EM_COBRANCA if body.contestation == "cobranca" else InvoiceStatus.CANCELADO
        )
        contested = db.scalars(
            select(Invoice).where(
                Invoice.debtor_id == UUID(exc.details["debtor_id"]),
                Invoice.status == InvoiceStatus.CONTESTADO,
            )
        ).all()
        for invoice in contested:
            set_invoice_status(invoice, new_status)
            audit(db, tenant_id=exc.tenant_id, actor=user.actor, action="resolve_contestacao",
                  entity="invoice", entity_id=invoice.id, after={"status": new_status})

    _close(db, exc, ExceptionStatus.RESOLVIDA, user, body.note)
    db.flush()
    return _out(db, [exc])[0]


@router.post("/{exception_id}/reject", response_model=ExceptionOut)
def reject_exception(
    exception_id: UUID,
    body: RejectExceptionIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> ExceptionOut:
    exc = _get_open(db, exception_id)
    _close(db, exc, ExceptionStatus.REJEITADA, user, body.note)

    if exc.payment_id:
        payment = db.get(Payment, exc.payment_id)
        if body.discard_payment:
            set_payment_status(payment, PaymentStatus.DESCARTADO)
        elif exc.type == ExceptionType.SUGESTAO_MATCH:
            # Sugestão errada: o pagamento volta para investigação sem candidato.
            open_exception(db, exc.tenant_id, ExceptionType.PAGAMENTO_NAO_IDENTIFICADO,
                           payment_id=payment.id, details={"reason": "sugestão rejeitada"})

    db.flush()
    return _out(db, [exc])[0]
