"""Puxa respostas do WhatsApp que o webhook não conseguiu entregar.

A Evolution desta instalação fica em outro servidor e não alcança o localhost.
Quando a conversa está com o agente, a resposta entra no painel e o turno roda
aqui — sem depender do worker Celery, que no dev local costuma estar parado.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.agent.tasks import run_agent_turn
from app.channels.delivery import RECEIPT_BODY
from app.channels.metrics import record_message, route_context
from app.channels.outbound import get_or_create_conversation, log_message
from app.channels.tasks import (
    continue_after_inbound,
    conversation_for_phone,
    find_debtor,
    quoted_outbound,
)
from app.channels.turn import claim_turn, release_turn
from app.channels.whatsapp import EvolutionClient, InboundMessage, _contact_jid, inbound_from_record
from app.core.config import get_settings
from app.core.db import system_session, tenant_session
from app.core.logging import get_logger
from app.core.senders import listed_senders
from app.models import Conversation, Debtor, Message, Tenant
from app.models.enums import ConversationState, MessageDirection
from app.receipts.tasks import process_whatsapp_receipt

log = get_logger(__name__)

AGENT_STATES = {
    ConversationState.AGENTE,
    ConversationState.AGUARDANDO_IDENTIDADE,
    ConversationState.AGUARDANDO_COMPROVANTE,
}


def _poll_jids(chat: dict[str, Any]) -> list[str]:
    """O WhatsApp entrega a resposta num @lid e o telefone em remoteJidAlt.
    Precisamos consultar os dois: findMessages no telefone só devolve o que saiu daqui."""
    last = chat.get("lastMessage") or {}
    key = last.get("key") or {}
    found: list[str] = []
    for jid in (key.get("remoteJid"), key.get("remoteJidAlt"), chat.get("remoteJid")):
        if isinstance(jid, str) and "@" in jid and not jid.endswith("@g.us") and jid not in found:
            found.append(jid)
    return found


def _conversation_for(session, tenant: Tenant, inbound) -> Conversation | None:
    """Citação ganha do telefone: responder em cima da Carla fica na conversa da Carla,
    mesmo quando vários devedores compartilham o número."""
    quoted = quoted_outbound(session, tenant.id, inbound.quoted_id)
    if quoted is not None:
        conv = session.get(Conversation, quoted.conversation_id)
        if conv is not None and inbound.remote_jid.endswith("@s.whatsapp.net"):
            conv.wa_jid = inbound.remote_jid
        return conv
    if not inbound.remote_jid.endswith("@s.whatsapp.net"):
        return None
    conv = conversation_for_phone(session, tenant.id, inbound.phone)
    if conv is not None:
        conv.wa_jid = inbound.remote_jid
        return conv
    debtor = find_debtor(session, tenant.id, inbound.phone)
    if debtor is None:
        return None
    conv = get_or_create_conversation(session, tenant.id, debtor)
    conv.wa_jid = inbound.remote_jid
    return conv


def _store(
    session, tenant: Tenant, instance: str, raw: dict[str, Any],
) -> tuple[str, Conversation, str] | None:
    inbound = inbound_from_record(instance, raw)
    if inbound is None or inbound.from_me or inbound.is_group:
        return None
    if not inbound.text or not inbound.message_id:
        return None
    if session.scalar(select(Message.id).where(Message.wa_message_id == inbound.message_id)):
        return None

    conv = _conversation_for(session, tenant, inbound)
    if conv is None:
        return None

    quoted = quoted_outbound(session, tenant.id, inbound.quoted_id)
    msg = log_message(
        session, conv, MessageDirection.IN, "devedor", inbound.text,
        invoice_id=quoted.invoice_id if quoted else None,
        wa_message_id=inbound.message_id,
    )
    if inbound.timestamp:
        msg.created_at = datetime.fromtimestamp(int(inbound.timestamp), UTC)
        conv.updated_at = msg.created_at
    log.info("inbound.synced", instance=instance, message_id=inbound.message_id)
    record_message("entrada", "aceita", "sync", "texto", "ok")
    if conv.state == ConversationState.HUMANO:
        record_message("entrada", "roteada", "humano", "texto", "ok")
    return inbound.text, conv, inbound.message_id


def unanswered_inbound(rows: list[tuple[str, str | None, str | None]]) -> tuple[str, str] | None:
    """Junta o que o devedor disse desde a última saída.

    `rows` vem da mais nova para a mais antiga: (direção, texto, token).
    O comprovante não entra no texto. O token é o da mensagem mais recente,
    para o turno não disparar de novo.
    """
    pending: list[tuple[str, str]] = []
    for direction, body, token in rows:
        if direction == MessageDirection.OUT:
            break
        text = (body or "").strip()
        if direction == MessageDirection.IN and text and text != RECEIPT_BODY:
            pending.append((text, token or ""))
    if not pending:
        return None
    pending.reverse()
    return "\n".join(item[0] for item in pending), pending[-1][1]


def agent_follow(
    state: ConversationState,
    stored: list[tuple[str, str]],
    pending: tuple[str, str] | None,
) -> tuple[str, str] | None:
    """Texto e token do turno. Comprovante na mesma rodada não silencia a resposta."""
    if state == ConversationState.HUMANO:
        return None
    if stored:
        return pending or stored[-1]
    if state in AGENT_STATES and pending is not None:
        return pending
    return None


def _pending_text(session, conv: Conversation) -> tuple[str, str] | None:
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc())
    ).all()
    return unanswered_inbound([
        (msg.direction, msg.body, msg.wa_message_id or str(msg.id)) for msg in rows
    ])


def _handle_receipt(
    tenant_id: UUID,
    instance: str,
    inbound: InboundMessage,
    conversation_id: UUID,
    debtor_id: UUID,
    raw: dict[str, Any],
) -> None:
    token = f"receipt:{inbound.message_id}"
    if not claim_turn(conversation_id, token):
        return
    record_message("entrada", "aceita", "sync", "arquivo", "ok")
    record_message("entrada", "roteada", "comprovante", "arquivo", "ok")
    try:
        process_whatsapp_receipt(
            str(tenant_id),
            instance,
            inbound.key,
            inbound.message_id,
            str(conversation_id),
            str(debtor_id),
            raw,
        )
    except Exception:
        release_turn(conversation_id, token)
        log.exception("inbound.receipt_failed", message_id=inbound.message_id)


def _follow_up(tenant_id: UUID, conversation_id: UUID, text: str, token: str) -> None:
    if not get_settings().llm_api_key:
        log.warning("inbound.agent_skipped_no_llm", conversation_id=str(conversation_id))
        return
    if not claim_turn(conversation_id, token):
        return
    try:
        with tenant_session(tenant_id) as session:
            tenant = session.get(Tenant, tenant_id)
            conv = session.get(Conversation, conversation_id)
            debtor = session.get(Debtor, conv.debtor_id)
            outcome, turn = continue_after_inbound(session, tenant, debtor, conv, text)
            context = route_context(outcome, conv.intent)
    except Exception:
        record_message("entrada", "roteada", "roteamento", "texto", "falha")
        release_turn(conversation_id, token)
        log.exception("inbound.agent_failed", conversation_id=str(conversation_id))
        return
    record_message("entrada", "roteada", context, "texto", "ok")
    if turn is None:
        log.info("inbound.routed", conversation_id=str(conversation_id), outcome=outcome)
        return
    try:
        run_agent_turn(str(tenant_id), *turn, token)
    except Exception:
        release_turn(conversation_id, token)
        log.exception("inbound.agent_failed", conversation_id=str(conversation_id))


def pull_unseen_replies(client: EvolutionClient | None = None) -> int:
    """Grava respostas ausentes e, se a conversa está com o agente, responde."""
    with system_session() as session:
        tenants = [
            (t.id, sender["instance"])
            for t in session.scalars(select(Tenant).where(Tenant.active.is_(True)))
            for sender in listed_senders(t)
        ]
    if not tenants:
        return 0

    client = client or EvolutionClient()
    added = 0
    for tenant_id, instance in tenants:
        with tenant_session(tenant_id) as session:
            known = list(session.scalars(select(Conversation.wa_jid).where(Conversation.tenant_id == tenant_id)))
        try:
            chats = client.find_chats(instance)
        except Exception:
            log.exception("inbound.sync_chats_failed", instance=instance)
            chats = []
        extras = [chat.get("lastMessage") for chat in chats if chat.get("lastMessage")]
        jids: list[str] = []
        for jid in [*(jid for chat in chats for jid in _poll_jids(chat)), *known]:
            if jid and not jid.endswith("@g.us") and jid not in jids:
                jids.append(jid)
        for jid in jids:
            try:
                records = client.find_messages(instance, jid, limit=30)
            except Exception:
                log.exception("inbound.sync_messages_failed", instance=instance, jid=jid)
                records = []
            seen_ids = {(raw.get("key") or {}).get("id") for raw in records}
            for extra in extras:
                extra_id = (extra.get("key") or {}).get("id")
                extra_jid = _contact_jid(extra.get("key") or {})
                if extra_id and extra_id not in seen_ids and (
                    extra_jid == jid or (extra.get("key") or {}).get("remoteJid") == jid
                ):
                    records.append(extra)
                    seen_ids.add(extra_id)
            records = sorted(records, key=lambda raw: int(raw.get("messageTimestamp") or 0))
            follow: tuple[UUID, str, str] | None = None
            receipts: list[tuple[InboundMessage, UUID, UUID, dict[str, Any]]] = []
            with tenant_session(tenant_id) as session:
                tenant = session.get(Tenant, tenant_id)
                conv = session.scalars(
                    select(Conversation).where(Conversation.tenant_id == tenant_id, Conversation.wa_jid == jid)
                ).first()
                stored: list[tuple[str, str]] = []
                for raw in records:
                    inbound = inbound_from_record(instance, raw)
                    if inbound and inbound.has_media and not inbound.from_me:
                        owner = _conversation_for(session, tenant, inbound)
                        if owner is not None and not session.scalar(
                            select(Message.id).where(Message.wa_message_id == inbound.message_id)
                        ):
                            receipts.append((inbound, owner.id, owner.debtor_id, raw))
                            conv = owner
                    result = _store(session, tenant, instance, raw)
                    if result:
                        text, conv, message_id = result
                        stored.append((text, message_id))
                        added += 1
                if conv is None or conv.state == ConversationState.HUMANO:
                    continue
                choice = agent_follow(conv.state, stored, _pending_text(session, conv))
                follow = (conv.id, *choice) if choice else None
            for inbound, conv_id, debtor_id, raw in receipts:
                _handle_receipt(tenant_id, instance, inbound, conv_id, debtor_id, raw)
                added += 1
            if follow:
                _follow_up(tenant_id, *follow)
    return added
