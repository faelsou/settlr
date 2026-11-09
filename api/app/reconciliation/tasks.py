from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import system_session, tenant_session
from app.core.logging import get_logger
from app.models import Payment, Tenant
from app.reconciliation.feeds import pull_tenant
from app.reconciliation.service import reconcile_payment
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.reconciliation.tasks.reconcile", max_retries=5, default_retry_delay=5)
def reconcile(tenant_id: str, payment_id: str) -> str:
    with tenant_session(UUID(tenant_id)) as session:
        tenant = session.get(Tenant, UUID(tenant_id))
        payment = session.get(Payment, UUID(payment_id))
        result = reconcile_payment(session, payment, tenant)
        log.info("reconcile.done", payment_id=payment_id, decision=result.decision, layer=result.layer)
        return result.decision


@celery_app.task(name="app.reconciliation.tasks.pull_statements")
def pull_statements() -> int:
    """O Beat dispara. Cada tenant busca o extrato na própria task."""
    with system_session() as session:
        ids = session.scalars(select(Tenant.id).where(Tenant.active.is_(True)))
        tenants = [str(tenant_id) for tenant_id in ids]
    for tenant_id in tenants:
        pull_statements_tenant.delay(tenant_id)
    return len(tenants)


@celery_app.task(
    name="app.reconciliation.tasks.pull_statements_tenant",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    max_retries=5,
)
def pull_statements_tenant(tenant_id: str) -> dict:
    tid = UUID(tenant_id)
    today = datetime.now(UTC).date()
    since = today - timedelta(days=get_settings().statement_lookback_days)
    with tenant_session(tid) as session:
        tenant = session.get(Tenant, tid)
        if tenant is None or not tenant.active:
            return {"created": 0, "duplicates": 0, "sources": []}
        result = pull_tenant(session, tenant, since=since, today=today)
        created = list(result.created)
        summary = {
            "created": len(created),
            "duplicates": result.duplicates,
            "sources": result.sources,
        }
    for payment_id in created:
        reconcile.delay(tenant_id, payment_id)
    log.info("statement.done", tenant_id=tenant_id, **summary)
    return summary
