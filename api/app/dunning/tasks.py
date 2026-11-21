from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from celery.exceptions import Retry
from sqlalchemy import select

from app.core.db import SessionLocal, set_tenant, system_session, tenant_session
from app.core.logging import get_logger
from app.dunning.rules import AllowedHours, within_allowed_hours
from app.dunning.service import (
    RateLimited,
    eligible_invoice_ids,
    email_subject,
    process_invoice,
    step_text,
)
from app.models import Debtor, DunningEvent, Invoice, Promise, Tenant
from app.models.enums import DUNNING_STATUSES, InvoiceStatus
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
        if not within_allowed_hours(now, AllowedHours.from_json(tenant.allowed_hours), tenant.timezone):
            return {"skipped": "fora_do_horario"}
        today = now.astimezone(ZoneInfo(tenant.timezone)).date()
        invoice_ids = eligible_invoice_ids(session, tenant, today)
        requeued = requeue_pending_emails(session, now)

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

    if requeued:
        counts["email_reagendado"] = requeued
    log.info("dunning.done", tenant_id=tenant_id, **counts)
    return counts


# A task envia em segundos; pendente mais velho que isso perdeu a task.
EMAIL_STALE_AFTER = timedelta(minutes=15)
EMAIL_MAX_RETRIES = 6
# Maior que a soma dos backoffs (~63 min): a chave só some quando a task termina.
EMAIL_CLAIM_TTL = 2 * 3600


def requeue_pending_emails(session, now: datetime) -> int:  # noqa: ANN001
    """E-mail da régua que ficou `pendente` (broker fora, SMTP fora) volta para a fila."""
    from app.channels.delivery import PENDENTE
    from app.channels.email import smtp_configured

    if not smtp_configured():
        return 0
    stale = session.execute(
        select(DunningEvent.tenant_id, DunningEvent.id).where(
            DunningEvent.channel == "email",
            DunningEvent.delivery_status == PENDENTE,
            DunningEvent.sent_at < now - EMAIL_STALE_AFTER,
        )
    ).all()
    requeued = 0
    for tenant_id, event_id in stale:
        if claim_email(str(event_id)):
            send_dunning_email.delay(str(tenant_id), str(event_id))
            requeued += 1
    return requeued


def claim_email(event_id: str) -> bool:
    """Uma task por e-mail na fila: a varredura não empilha cópias de quem está em backoff."""
    from app.core.redis import get_redis

    return bool(get_redis().set(f"dunning:email:{event_id}", 1, nx=True, ex=EMAIL_CLAIM_TTL))


def release_email(event_id: str) -> None:
    from app.core.redis import get_redis

    get_redis().delete(f"dunning:email:{event_id}")


@celery_app.task(
    name="app.dunning.tasks.send_dunning_email", bind=True, max_retries=EMAIL_MAX_RETRIES,
)
def send_dunning_email(self, tenant_id: str, event_id: str) -> str:
    try:
        result = _send_dunning_email(self, tenant_id, event_id)
    except Retry:
        raise
    except Exception:
        release_email(event_id)
        raise
    release_email(event_id)
    return result


def _send_dunning_email(self, tenant_id: str, event_id: str) -> str:  # noqa: ANN001
    """Envia o e-mail de uma etapa da régua. Só envia evento `pendente`, sob trava.

    - aceito: o servidor SMTP aceitou (não é entrega, como o HTTP 200 da Evolution).
    - falhou: recusa definitiva (5xx do destinatário) ou retries esgotados.
    - SMTP ausente ou login recusado: fica `pendente`; a varredura da régua reagenda.
    """
    import smtplib

    from app.channels.delivery import ACEITO, FALHOU, PENDENTE
    from app.channels.email import is_permanent, send_email, smtp_configured
    from app.channels.metrics import record_message
    from app.core.audit import audit

    tid, eid = UUID(tenant_id), UUID(event_id)
    with tenant_session(tid) as session:
        event = session.scalars(
            select(DunningEvent).where(DunningEvent.id == eid).with_for_update()
        ).first()
        if event is None or event.delivery_status != PENDENTE:
            return "ja_tratado"
        if not smtp_configured():
            return "adiado"
        invoice = session.get(Invoice, event.invoice_id)
        debtor = session.get(Debtor, invoice.debtor_id)
        tenant = session.get(Tenant, tid)
        text = step_text(tenant, invoice, debtor, event.step)

        def close(status: str, reason: str, message_id: str | None = None) -> str:
            event.delivery_status = status
            if message_id:
                event.message_id = message_id[:120]
            audit(session, tenant_id=tid, actor="regua", action="entrega_email",
                  entity="invoice", entity_id=invoice.id,
                  after={"step": event.step, "delivery_status": status, "reason": reason,
                         "message_id": event.message_id})
            result = "ok" if status == ACEITO else "falha"
            record_message("saida", "enviada", "regua", "texto", result)
            return status

        # Título pago, devedor que pediu para parar ou e-mail apagado: não envia.
        if (
            invoice.status not in DUNNING_STATUSES
            or debtor.opt_out
            or not debtor.email
            or text is None
        ):
            return close(FALHOU, "nao_cabe_mais")

        try:
            message_id = send_email(debtor.email, email_subject(invoice), text)
        except (smtplib.SMTPException, OSError) as exc:
            if isinstance(exc, smtplib.SMTPAuthenticationError):
                log.error("dunning.email_login_failed", tenant_id=tenant_id)
                return "adiado"
            if is_permanent(exc):
                return close(FALHOU, f"recusa:{exc.__class__.__name__}")
            if self.request.retries >= self.max_retries:
                return close(FALHOU, f"retries_esgotados:{exc.__class__.__name__}")
            log.warning("dunning.email_retry", event_id=event_id, error=exc.__class__.__name__,
                        attempt=self.request.retries + 1)
            raise self.retry(countdown=min(3600, 60 * 2 ** self.request.retries)) from None
        return close(ACEITO, "smtp_aceitou", message_id)


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
