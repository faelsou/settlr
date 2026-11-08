"""Recibo de entrega do WhatsApp (`messages.update`).

HTTP 200 da Evolution é aceite, não entrega. O recibo é que grava
`entregue`, `lido` ou `falhou`. Status terminal não regride.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.metrics import record_message
from app.channels.whatsapp import EvolutionWebhook
from app.models import DunningEvent, Message

ACEITO = "aceito"
ENTREGUE = "entregue"
LIDO = "lido"
FALHOU = "falhou"
PENDENTE = "pendente"
ENVIADO = "enviado"
SEM_RECIBO = "sem_recibo"
ARQUIVO_RECEBIDO = "recebido"
ARQUIVO_AUSENTE = "nao_recebido"
RECEIPT_BODY = "[comprovante]"

# `enviado` é o valor antigo, do tempo em que HTTP 200 encerrava a etapa.
# `sem_recibo` fica no mesmo degrau de `aceito`: ainda não chegou, mas a etapa segue presa.
_RANK = {PENDENTE: 1, ACEITO: 2, ENVIADO: 2, SEM_RECIBO: 2, ENTREGUE: 3, LIDO: 4}

_EVOLUTION_STATUS = {
    "ERROR": FALHOU,
    "FAILED": FALHOU,
    "FAIL": FALHOU,
    "PENDING": PENDENTE,
    "SERVER_ACK": ACEITO,
    "DELIVERY_ACK": ENTREGUE,
    "READ": LIDO,
    "PLAYED": LIDO,
    "0": FALHOU,
    "1": PENDENTE,
    "2": ACEITO,
    "3": ENTREGUE,
    "4": LIDO,
    "5": LIDO,
}


def normalize_event(event: str) -> str:
    return event.lower().replace("_", ".")


def file_state(body: str | None, media_key: str | None) -> str | None:
    """Cópia no storage, ou comprovante que chegou sem essa cópia. Texto não tem arquivo."""
    if media_key:
        return ARQUIVO_RECEBIDO
    if (body or "").strip() == RECEIPT_BODY:
        return ARQUIVO_AUSENTE
    return None


def counts_as_dispatched(delivery_status: str) -> bool:
    """Etapa que ainda segura a régua. Falha libera o mesmo passo no mesmo canal."""
    return delivery_status != FALHOU


def advance_status(current: str | None, new: str) -> str | None:
    """Próximo status, ou None quando o evento repete ou tenta regredir um terminal."""
    if new == current:
        return None
    if current == FALHOU or current == LIDO:
        return None
    if new == FALHOU:
        if current in (ENTREGUE, LIDO):
            return None
        return FALHOU
    if new == SEM_RECIBO:
        if current in (ACEITO, ENVIADO, PENDENTE):
            return SEM_RECIBO
        return None
    if current is None:
        return new
    if _RANK.get(new, 0) > _RANK.get(current, 0):
        return new
    return None


def map_evolution_status(raw: Any) -> str | None:
    if raw is None or isinstance(raw, bool):
        return None
    return _EVOLUTION_STATUS.get(str(raw).strip().upper())


@dataclass(frozen=True)
class DeliveryUpdate:
    message_id: str
    status: str


def is_delivery_event(payload: EvolutionWebhook) -> bool:
    return normalize_event(payload.event) == "messages.update"


def _one_update(item: dict[str, Any]) -> DeliveryUpdate | None:
    key = item.get("key") if isinstance(item.get("key"), dict) else {}
    update = item.get("update") if isinstance(item.get("update"), dict) else {}
    message_id = item.get("messageId") or item.get("keyId") or key.get("id")
    raw_status = item.get("status", update.get("status"))
    status = map_evolution_status(raw_status)
    if not message_id or status is None:
        return None
    return DeliveryUpdate(message_id=str(message_id), status=status)


def parse_delivery_updates(payload: EvolutionWebhook) -> list[DeliveryUpdate]:
    if not is_delivery_event(payload):
        return []
    raw_items: list[Any]
    if isinstance(payload.data, list):
        raw_items = payload.data
    else:
        raw_items = [payload.data]
    updates: list[DeliveryUpdate] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        parsed = _one_update(item)
        if parsed is not None:
            updates.append(parsed)
    return updates


def apply_delivery_updates(session: Session, updates: list[DeliveryUpdate]) -> int:
    """Espelha o recibo em `messages` e, quando for da régua, em `dunning_events`."""
    changed = 0
    for update in updates:
        messages = session.scalars(
            select(Message).where(Message.wa_message_id == update.message_id)
        ).all()
        events = session.scalars(
            select(DunningEvent).where(DunningEvent.message_id == update.message_id)
        ).all()
        advanced = False
        for row in (*messages, *events):
            nxt = advance_status(row.delivery_status, update.status)
            if nxt is None:
                continue
            row.delivery_status = nxt
            changed += 1
            advanced = True
        if advanced:
            result = "falha" if update.status == FALHOU else "ok"
            record_message("saida", "recibo", update.status, "texto", result)
    return changed
