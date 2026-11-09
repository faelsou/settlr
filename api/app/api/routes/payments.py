from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.schemas import ImportResultOut, MatchOut, Page, PaymentOut
from app.core import storage
from app.models import Match, Payment
from app.models.enums import PaymentOrigin
from app.reconciliation.export import render_accountant_csv, settlement_rows
from app.reconciliation.service import register_bank_payment
from app.reconciliation.statement import parse_statement
from app.reconciliation.tasks import reconcile

router = APIRouter(prefix="/payments", tags=["pagamentos"])


def payments_out(session: Session, payments: list[Payment]) -> list[PaymentOut]:
    ids = [p.id for p in payments]
    matches: dict[UUID, list[Match]] = {}
    if ids:
        for m in session.scalars(select(Match).where(Match.payment_id.in_(ids))):
            matches.setdefault(m.payment_id, []).append(m)
    return [
        PaymentOut(
            id=p.id,
            origin=p.origin,
            status=p.status,
            amount=p.amount,
            paid_at=p.paid_at,
            e2e_id=p.e2e_id,
            payer_doc=p.payer_doc,
            payer_name=p.payer_name,
            payer_bank=p.payer_bank,
            has_receipt=p.file_key is not None,
            bank_confirmed=p.bank_confirmed_at is not None,
            extraction_confidence=p.extraction_confidence,
            matches=[MatchOut.model_validate(m) for m in matches.get(p.id, [])],
            created_at=p.created_at,
        )
        for p in payments
    ]


@router.get("", response_model=Page[PaymentOut])
def list_payments(
    status: str | None = None,
    origin: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Page[PaymentOut]:
    query = select(Payment)
    if status:
        query = query.where(Payment.status == status)
    if origin:
        query = query.where(Payment.origin == origin)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Payment.paid_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=payments_out(db, list(items)), total=total or 0)


@router.get("/export")
def export_settlements(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> Response:
    """CSV do período para o contador. Só entra baixa definitiva."""
    if end < start:
        raise HTTPException(422, "o fim do período é anterior ao início")
    if (end - start).days > 366:
        raise HTTPException(422, "o período passa de um ano")
    if user.tenant_id is None:
        raise HTTPException(403, "usuário sem tenant")
    body = render_accountant_csv(settlement_rows(db, user.tenant_id, start, end))
    filename = f"baixas-{start.isoformat()}-{end.isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{payment_id}/receipt")
def get_receipt(payment_id: UUID, db: Session = Depends(get_db)) -> Response:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.file_key is None:
        raise HTTPException(404, "comprovante não encontrado")
    return Response(storage.get_object(payment.file_key), media_type=payment.content_type)


@router.post("/import", response_model=ImportResultOut)
async def import_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> ImportResultOut:
    """Exceção: OFX ou CSV quando não há Open Finance nem extrato do emissor."""
    try:
        transactions = parse_statement(file.filename or "", await file.read())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    created: list[str] = []
    for tx in transactions:
        payment = register_bank_payment(db, user.tenant_id, tx, PaymentOrigin.EXTRATO)
        if payment is not None:
            created.append(str(payment.id))
    db.commit()

    for payment_id in created:
        reconcile.delay(str(user.tenant_id), payment_id)
    return ImportResultOut(created=len(created), duplicates=len(transactions) - len(created))
