"""Métricas do painel (fase 4)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.schemas import Metrics
from app.models import Invoice, Match, Payment, Promise, ReviewException, Tenant
from app.models.enums import ExceptionStatus, InvoiceStatus, PaymentStatus

router = APIRouter(prefix="/metrics", tags=["metricas"])


def _ratio(a: float | Decimal, b: float | Decimal) -> float | None:
    return round(float(a) / float(b), 4) if b else None


@router.get("", response_model=Metrics)
def get_metrics(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> Metrics:
    end = end or datetime.now(UTC).date()
    start = start or end - timedelta(days=30)
    start_dt = datetime.combine(start, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end, time.max, tzinfo=UTC)

    # Recuperação: valor aplicado após o vencimento ÷ valor vencido no período.
    overdue = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.due_date.between(start, end),
            Invoice.due_date < end,
            Invoice.status.not_in([InvoiceStatus.CANCELADO, InvoiceStatus.RENEGOCIADO]),
        )
    ) or Decimal("0")
    late = (
        select(Match.amount_applied, Payment.paid_at, Invoice.due_date)
        .join(Payment, Payment.id == Match.payment_id)
        .join(Invoice, Invoice.id == Match.invoice_id)
        .where(Match.provisional.is_(False))
        .where(Invoice.due_date.between(start, end))
        .where(cast(Payment.paid_at, Date) > Invoice.due_date)
        .subquery()
    )
    recovered = db.scalar(select(func.coalesce(func.sum(late.c.amount_applied), 0))) or Decimal("0")
    avg_days_late = db.scalar(select(func.avg(cast(late.c.paid_at, Date) - late.c.due_date)))

    promises = db.execute(
        select(
            func.count(),
            func.count().filter(Promise.fulfilled.is_(True)),
        ).where(Promise.created_at.between(start_dt, end_dt), Promise.fulfilled.is_not(None))
    ).one()

    reconciled = db.execute(
        select(
            func.count(func.distinct(Payment.id)),
            func.count(func.distinct(case((Match.confirmed_by == "sistema", Payment.id)))),
        )
        .join(Match, Match.payment_id == Payment.id)
        .where(Payment.status == PaymentStatus.CONCILIADO, Match.provisional.is_(False))
        .where(Payment.paid_at.between(start_dt, end_dt))
    ).one()

    exceptions_open = db.scalar(
        select(func.count()).where(ReviewException.status == ExceptionStatus.ABERTA)
    ) or 0
    avg_resolution = db.scalar(
        select(func.avg(func.extract("epoch", ReviewException.resolved_at - ReviewException.created_at)))
        .where(ReviewException.resolved_at.between(start_dt, end_dt))
    )

    tenant = db.get(Tenant, user.tenant_id)
    raw_baseline = None if tenant is None else tenant.baseline_avg_days_late
    baseline = None if raw_baseline is None else float(raw_baseline)

    return Metrics(
        period_start=start,
        period_end=end,
        recovery_rate=_ratio(recovered, overdue),
        overdue_amount=overdue,
        recovered_amount=recovered,
        avg_days_late=float(avg_days_late) if avg_days_late is not None else None,
        baseline_avg_days_late=baseline,
        promises_made=promises[0],
        promises_kept=promises[1],
        promise_kept_rate=_ratio(promises[1], promises[0]),
        payments_reconciled=reconciled[0],
        auto_reconciled=reconciled[1],
        auto_reconciliation_rate=_ratio(reconciled[1], reconciled[0]),
        exceptions_open=exceptions_open,
        avg_exception_resolution_hours=round(float(avg_resolution) / 3600, 2) if avg_resolution else None,
    )
