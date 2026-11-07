"""Reconciliação de saída: o recibo que o webhook não trouxe, e o `sem_recibo`.

Roda no mesmo ciclo de `pull_unseen_replies`, em dev e em produção, desde que
a chave da Evolution exista. A janela parte de 6 horas e o tenant pode
sobrescrever em `dunning_rules.receipt_window_hours`.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.channels.delivery import (
    ACEITO,
    ENVIADO,
    PENDENTE,
    SEM_RECIBO,
    DeliveryUpdate,
    advance_status,
    apply_delivery_updates,
    map_evolution_status,
)
from app.channels.whatsapp import EvolutionClient
from app.core.config import get_settings
from app.core.db import system_session, tenant_session
from app.core.logging import get_logger
from app.models import Conversation, Message, Tenant
from app.models.enums import MessageDirection

log = get_logger(__name__)

DEFAULT_RECEIPT_WINDOW = timedelta(hours=6)
OPEN_OUTBOUND = (PENDENTE, ACEITO, ENVIADO, SEM_RECIBO)


def reconciliation_enabled(settings=None) -> bool:
    """Produção entra no mesmo critério do dev: chave da Evolution preenchida."""
    settings = settings or get_settings()
    return bool(settings.evolution_api_key)


def receipt_window(rules: dict | None) -> timedelta:
    raw = (rules or {}).get("receipt_window_hours", 6)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        hours = 6
    if hours <= 0:
        hours = 6
    return timedelta(hours=hours)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def plan_outbound_fixes(
    rows: list[tuple[str, str, datetime]],
    records: list[dict[str, Any]],
    *,
    now: datetime,
    window: timedelta,
) -> list[tuple[str, str]]:
    """`(wa_message_id, status novo)` só quando o banco precisa mudar.

    `rows` traz o que está em `aceito`, `pendente`, `enviado` ou `sem_recibo`.
    O status visto na Evolution ganha da janela. Sem recibo depois da janela,
    `aceito` vira `sem_recibo` — ainda não é falha.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for raw in records:
        key = raw.get("key") if isinstance(raw.get("key"), dict) else {}
        message_id = key.get("id")
        if message_id:
            by_id[str(message_id)] = raw

    fixes: list[tuple[str, str]] = []
    for wa_id, current, created_at in rows:
        found = by_id.get(wa_id)
        seen = map_evolution_status(found.get("status")) if found else None
        advanced = advance_status(current, seen) if seen else None
        if advanced:
            fixes.append((wa_id, advanced))
            continue
        if current in (ACEITO, ENVIADO) and _aware(created_at) <= _aware(now) - window:
            nxt = advance_status(current, SEM_RECIBO)
            if nxt:
                fixes.append((wa_id, nxt))
    return fixes


def reconcile_outbound(client: EvolutionClient | None = None, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    with system_session() as session:
        tenants = [
            (tenant.id, tenant.whatsapp_instance, receipt_window(tenant.dunning_rules))
            for tenant in session.scalars(select(Tenant).where(Tenant.active.is_(True)))
            if tenant.whatsapp_instance
        ]
    if not tenants:
        return 0

    client = client or EvolutionClient()
    changed = 0
    for tenant_id, instance, window in tenants:
        with tenant_session(tenant_id) as session:
            rows = list(
                session.scalars(
                    select(Message).where(
                        Message.tenant_id == tenant_id,
                        Message.direction == MessageDirection.OUT,
                        Message.wa_message_id.is_not(None),
                        Message.delivery_status.in_(OPEN_OUTBOUND),
                    )
                )
            )
            if not rows:
                continue
            convs = {
                conv.id: conv
                for conv in session.scalars(
                    select(Conversation).where(
                        Conversation.id.in_({row.conversation_id for row in rows})
                    )
                )
            }
            by_jid: dict[str, list[Message]] = {}
            for row in rows:
                conv = convs.get(row.conversation_id)
                if conv is None or not row.wa_message_id or row.created_at is None:
                    continue
                by_jid.setdefault(conv.wa_jid, []).append(row)
            for jid, msgs in by_jid.items():
                try:
                    records = client.find_messages(instance, jid, limit=50)
                except Exception:
                    log.exception("outbound.reconcile_failed", instance=instance, jid=jid)
                    records = []
                pending = [
                    (msg.wa_message_id, msg.delivery_status or ACEITO, msg.created_at)
                    for msg in msgs
                ]
                planned = plan_outbound_fixes(pending, records, now=now, window=window)
                changed += apply_delivery_updates(
                    session, [DeliveryUpdate(wa_id, status) for wa_id, status in planned]
                )
    return changed
