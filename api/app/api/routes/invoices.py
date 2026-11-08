from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.schemas import (
    DunningEventOut,
    ImportResultOut,
    InstallmentOut,
    InvoiceDetail,
    InvoiceOut,
    MatchOut,
    Page,
    PromiseOut,
    message_out,
)
from app.dunning.payment import payment_code_clause
from app.ingest.service import import_invoices, parse_invoice_csv
from app.models import Conversation, Debtor, DunningEvent, Invoice, Match, Message, Promise
from app.models.enums import DUNNING_STATUSES

router = APIRouter(prefix="/invoices", tags=["titulos"])


@router.get("", response_model=Page[InvoiceOut])
def list_invoices(
    status: str | None = None,
    sem_pagamento: bool = Query(False, description="só títulos da régua sem PIX e sem boleto"),
    q: str | None = Query(None, description="nome ou documento do devedor"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Page[InvoiceOut]:
    query = select(Invoice).join(Debtor).options(joinedload(Invoice.debtor))
    if sem_pagamento:
        query = query.where(Invoice.status.in_(DUNNING_STATUSES)).where(~payment_code_clause())
    elif status:
        query = query.where(Invoice.status == status)
    if q:
        digits = "".join(c for c in q if c.isdigit())
        conditions = [Debtor.name.ilike(f"%{q}%"), Invoice.external_id == q]
        if digits:
            conditions.append(Debtor.document.like(f"{digits}%"))
        query = query.where(or_(*conditions))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Invoice.due_date.desc()).limit(limit).offset(offset)).all()
    return Page(items=[InvoiceOut.model_validate(i) for i in items], total=total or 0)


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: UUID, db: Session = Depends(get_db)) -> InvoiceDetail:
    invoice = db.scalars(
        select(Invoice).options(joinedload(Invoice.debtor)).where(Invoice.id == invoice_id)
    ).first()
    if invoice is None:
        raise HTTPException(404, "título não encontrado")

    events = db.scalars(
        select(DunningEvent).where(DunningEvent.invoice_id == invoice_id).order_by(DunningEvent.sent_at)
    ).all()
    conversation = db.scalars(
        select(Conversation).where(Conversation.debtor_id == invoice.debtor_id)
    ).first()
    if conversation is not None:
        messages = db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)
        ).all()
    else:
        messages = db.scalars(
            select(Message).where(Message.invoice_id == invoice_id).order_by(Message.created_at)
        ).all()
    promises = db.scalars(select(Promise).where(Promise.invoice_id == invoice_id)).all()
    matches = db.scalars(select(Match).where(Match.invoice_id == invoice_id)).all()
    if invoice.agreement_id:
        installments = db.scalars(
            select(Invoice).where(Invoice.agreement_id == invoice.agreement_id).order_by(Invoice.due_date)
        ).all()
    else:
        installments = db.scalars(
            select(Invoice).where(Invoice.parent_id == invoice.id).order_by(Invoice.due_date)
        ).all()

    return InvoiceDetail(
        **InvoiceOut.model_validate(invoice).model_dump(),
        dunning_events=[DunningEventOut.model_validate(e) for e in events],
        messages=[message_out(m) for m in messages],
        promises=[PromiseOut.model_validate(p) for p in promises],
        matches=[MatchOut.model_validate(m) for m in matches],
        installments=[InstallmentOut.model_validate(i) for i in installments],
    )


@router.post("/import", response_model=ImportResultOut)
async def import_invoice_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> ImportResultOut:
    """Planilha com colunas: referencia, nome, documento, telefone, email, valor,
    vencimento, descricao, txid, linha_digitavel, pix_copia_cola, link.
    Até 5 celulares: telefone2…telefone5, ou vários números em telefone separados por |."""
    rows, errors = parse_invoice_csv(await file.read())
    if errors:
        raise HTTPException(422, {"errors": errors})
    result = import_invoices(db, user.tenant_id, rows, user.actor)
    return ImportResultOut(created=result.created, updated=result.updated)
