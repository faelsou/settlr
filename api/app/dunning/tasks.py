from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import SessionLocal, set_tenant, system_session, tenant_session
from app.core.logging import get_logger
from app.dunning.rules import AllowedHours, within_allowed_hours
from app.dunning.service import RateLimited, eligible_invoice_ids, process_invoice
from app.models import Invoice, Promise, Tenant
from app.models.enums import InvoiceStatus
from app.reconciliation.service import set_invoice_status
from app.workers.celery_app import celery_app

log = get_logger(__name__)


def _active_tenants() -> list[str]:
    with system_session() as session:
        return [str(t) for t in session.scalars(select(Tenant.id).where(Tenant.active.is_(True)))]


@celery_app.task(name="app.dunning.tasks.run_dunning")
def run_dunning() -> int:
    """Publicada pelo Beat. Só distribui: cada tenant roda numa task própria."""
    tenants = _active_tenants()
    for tenant_id in tenants:
        run_dunning_tenant.delay(tenant_id)
    return len(tenants)


@celery_app.task(name="app.dunning.tasks.run_dunning_tenant", bind=True, max_retries=None)
def run_dunning_tenant(self, tenant_id: str) -> dict:
    tid = UUID(tenant_id)
    now = datetime.now(UTC)

    with tenant_session(tid) as session:
        tenant = session.get(Tenant, tid)
        if not within_allowed_hours(
            now, AllowedHours.from_json(tenant.allowed_hours), tenant.timezone
        ):
            return {"skipped": "fora_do_horario"}
        today = now.astimezone(ZoneInfo(tenant.timezone)).date()
        invoice_ids = eligible_invoice_ids(session, tenant, today)

    counts: dict[str, int] = {}
    for invoice_id in invoice_ids:
        # Uma transação por título: falha num envio não desfaz os anteriores.
        try:
            with SessionLocal() as session, session.begin():
                set_tenant(session, tid)
                tenant = session.get(Tenant, tid)
                outcome = process_invoice(session, tenant, invoice_id, today)
        except RateLimited:
            log.info("dunning.rate_limited", tenant_id=tenant_id)
            raise self.retry(countdown=60) from None
        except Exception:
            log.exception("dunning.invoice_failed", tenant_id=tenant_id, invoice_id=str(invoice_id))
            counts["error"] = counts.get("error", 0) + 1
            continue
        counts[outcome.action] = counts.get(outcome.action, 0) + 1

    log.info("dunning.done", tenant_id=tenant_id, **counts)
    return counts


@celery_app.task(name="app.dunning.tasks.check_promises")
def check_promises() -> int:
    """Promessa vencida sem pagamento conciliado vira quebrada e a régua retoma."""
    broken = 0
    for tenant_id in _active_tenants():
        with tenant_session(UUID(tenant_id)) as session:
            tenant = session.get(Tenant, UUID(tenant_id))
            today = datetime.now(ZoneInfo(tenant.timezone)).date()
            due = session.scalars(
                select(Promise).where(
                    Promise.fulfilled.is_(None),
                    Promise.promised_date < today - timedelta(days=1),
                )
            ).all()
            for promise in due:
                promise.fulfilled = False
                promise.checked_at = datetime.now(UTC)
                invoice = session.get(Invoice, promise.invoice_id)
                if invoice.status == InvoiceStatus.PROMESSA:
                    set_invoice_status(invoice, InvoiceStatus.EM_COBRANCA)
                broken += 1
    return broken
