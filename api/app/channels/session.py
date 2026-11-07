"""Alerta de sessão do número. Não entra na fila de mensagens do devedor.

Sessão caída perde o canal inteiro. Olhar mensagem por mensagem chega tarde.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.delivery import normalize_event
from app.channels.whatsapp import EvolutionWebhook
from app.core.logging import get_logger
from app.models import ReviewException
from app.models.enums import ExceptionStatus, ExceptionType
from app.reconciliation.service import open_exception

log = get_logger(__name__)

CLOSED_STATES = {"close", "closed", "refused", "disconnected"}


def connection_state(payload: EvolutionWebhook) -> str | None:
    if normalize_event(payload.event) != "connection.update":
        return None
    data = payload.data if isinstance(payload.data, dict) else {}
    raw = data.get("state") or data.get("status") or data.get("connection")
    if raw is None:
        return None
    return str(raw).strip().lower()


def session_is_down(state: str | None) -> bool:
    return state in CLOSED_STATES


def alert_session_down(
    session: Session,
    tenant_id: UUID,
    instance: str,
    state: str,
    reason: Any = None,
) -> bool:
    """Abre uma exceção do canal, sem conversa e sem mensagem. Repetido não duplica."""
    existing = session.scalars(
        select(ReviewException).where(
            ReviewException.tenant_id == tenant_id,
            ReviewException.type == ExceptionType.SESSAO_CANAL,
            ReviewException.status == ExceptionStatus.ABERTA,
        )
    ).all()
    for exc in existing:
        if (exc.details or {}).get("instance") == instance:
            return False
    open_exception(
        session,
        tenant_id,
        ExceptionType.SESSAO_CANAL,
        details={
            "instance": instance,
            "state": state,
            "reason": reason,
            "motivo": "sessão do WhatsApp caída",
        },
    )
    log.warning("whatsapp.session_down", instance=instance, state=state, reason=reason)
    return True
