"""Aviso ao dono da PME quando a fila humana ganha um item.

O destino é o e-mail ou o WhatsApp interno cadastrados no tenant. Não passa
por `send_to_debtor` e não entra na conversa de cobrança. Contato de devedor
em opt-out nunca recebe este aviso.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.email import send_email
from app.channels.whatsapp import EvolutionClient
from app.core.audit import audit
from app.core.logging import get_logger
from app.core.phones import contact_phones, normalize_br_phone
from app.models import Debtor, Tenant

log = get_logger(__name__)

QUEUE_LABELS = {
    "pagamento_nao_identificado": "exceção",
    "sugestao_match": "exceção",
    "diferenca_valor": "exceção",
    "leitura_baixa_confianca": "exceção",
    "transcricao_indisponivel": "áudio sem transcrição",
    "contestacao": "contestação",
    "fila_humana": "título em D+30",
    "sessao_canal": "sessão do canal",
    "aprovacao": "aprovação fora da política",
}


def queue_label(kind: str) -> str:
    return QUEUE_LABELS.get(kind, kind)


def format_stalled(opened_at: datetime, now: datetime) -> str:
    """Texto de quanto tempo o item está parado, sempre começando por 'há'."""
    start = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=UTC)
    current = now if now.tzinfo else now.replace(tzinfo=UTC)
    minutes = max(0, int((current - start).total_seconds() // 60))
    if minutes < 1:
        return "há menos de 1 minuto"
    if minutes < 60:
        unit = "minuto" if minutes == 1 else "minutos"
        return f"há {minutes} {unit}"
    hours = minutes // 60
    if hours < 48:
        unit = "hora" if hours == 1 else "horas"
        return f"há {hours} {unit}"
    days = hours // 24
    unit = "dia" if days == 1 else "dias"
    return f"há {days} {unit}"


def notice_copy(kind: str, opened_at: datetime, now: datetime) -> tuple[str, str, str]:
    label = queue_label(kind)
    stalled = format_stalled(opened_at, now)
    subject = f"Fila humana parada: {label}"
    body = f"Tipo: {label}. Está parado {stalled}."
    return label, subject, body


def _norm_phone(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    try:
        return normalize_br_phone(str(value))
    except ValueError:
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return digits or None


def _opted_out_emails(debtors: list[Debtor]) -> set[str]:
    return {
        debtor.email.strip().casefold()
        for debtor in debtors
        if debtor.opt_out and debtor.email and debtor.email.strip()
    }


def _opted_out_phones(debtors: list[Debtor]) -> set[str]:
    found: set[str] = set()
    for debtor in debtors:
        if not debtor.opt_out:
            continue
        for number in contact_phones(debtor.phone, debtor.phones):
            normalized = _norm_phone(number)
            if normalized:
                found.add(normalized)
    return found


def hits_opt_out(channel: str, destination: str, debtors: list[Debtor]) -> bool:
    if channel == "email":
        return destination.strip().casefold() in _opted_out_emails(debtors)
    phone = _norm_phone(destination)
    return bool(phone and phone in _opted_out_phones(debtors))


def notify_human_queue(
    session: Session,
    *,
    tenant_id: UUID,
    kind: str,
    entity: str,
    entity_id: UUID,
    opened_at: datetime | None,
    now: datetime | None = None,
) -> str:
    """Dispara o aviso. Falha de envio não desfaz o item da fila."""
    try:
        return _notify(
            session,
            tenant_id=tenant_id,
            kind=kind,
            entity=entity,
            entity_id=entity_id,
            opened_at=opened_at,
            now=now or datetime.now(UTC),
        )
    except Exception:
        log.warning("fila_humana.aviso_falhou", kind=kind, entity=entity, exc_info=True)
        return "falhou"


def _notify(
    session: Session,
    *,
    tenant_id: UUID,
    kind: str,
    entity: str,
    entity_id: UUID,
    opened_at: datetime | None,
    now: datetime,
) -> str:
    tenant = session.get(Tenant, tenant_id)
    if not isinstance(tenant, Tenant):
        return "sem_destino"

    moment = opened_at or now
    label, subject, body = notice_copy(kind, moment, now)
    debtors = list(
        session.scalars(
            select(Debtor).where(Debtor.tenant_id == tenant_id, Debtor.opt_out.is_(True))
        ).all()
    )
    email = (tenant.owner_email or "").strip()
    phone = (tenant.owner_phone or "").strip()
    channel, destination = _choose(tenant, email, phone, debtors)
    if channel in {"sem_destino", "recusado"} or destination is None:
        action = "aviso_fila_recusado" if channel == "recusado" else "aviso_fila_sem_destino"
        after: dict[str, str] = {"tipo": label}
        if channel == "recusado":
            after["motivo"] = "opt_out"
        audit(
            session, tenant_id=tenant_id, actor="sistema", action=action,
            entity=entity, entity_id=entity_id, after=after,
        )
        return channel

    stalled = format_stalled(moment, now)
    if channel == "email":
        try:
            send_email(destination, subject, body)
        except Exception:
            phone_ok = (
                bool(phone)
                and bool(tenant.whatsapp_instance)
                and not hits_opt_out("whatsapp", phone, debtors)
            )
            if not phone_ok:
                raise
            EvolutionClient().send_text(tenant.whatsapp_instance or "", phone, body)
            channel = "whatsapp"
            log.warning("fila_humana.email_falhou", tenant_id=str(tenant_id))
    else:
        EvolutionClient().send_text(tenant.whatsapp_instance or "", destination, body)

    audit(
        session, tenant_id=tenant_id, actor="sistema", action="avisa_fila_humana",
        entity=entity, entity_id=entity_id,
        after={"tipo": label, "parado": stalled, "canal": channel},
    )
    return channel


def _choose(
    tenant: Tenant, email: str, phone: str, debtors: list[Debtor],
) -> tuple[str, str | None]:
    """E-mail do dono, senão WhatsApp interno. Opt-out do devedor elimina o destino."""
    if email and not hits_opt_out("email", email, debtors):
        return "email", email
    if phone and not hits_opt_out("whatsapp", phone, debtors):
        if tenant.whatsapp_instance:
            return "whatsapp", phone
        return "sem_destino", None
    if email or phone:
        return "recusado", None
    return "sem_destino", None
