"""Inbound do WhatsApp (FLUXOS.md §6) e roteamento por intenção."""

import re
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.orm import Session

from app.agent.intent import classify_intent
from app.agent.tasks import run_agent_turn
from app.channels.metrics import record_file, record_message, route_context
from app.channels.outbound import get_or_create_conversation, log_message, send_to_debtor
from app.channels.turn import claim_turn, release_turn
from app.channels.whatsapp import EvolutionClient, debounce_drain
from app.core.audit import audit
from app.core.db import tenant_session
from app.core.logging import get_logger
from app.dunning.promises import PromiseRejected, register_promise
from app.models import Conversation, Debtor, Invoice, Message, Tenant
from app.models.enums import (
    OPEN_INVOICE_STATUSES,
    ConversationState,
    ExceptionType,
    Intent,
    InvoiceStatus,
    MessageDirection,
)
from app.receipts.service import stage_receipt_bytes
from app.receipts.tasks import process_whatsapp_receipt
from app.reconciliation.service import open_exception, set_invoice_status
from app.workers.celery_app import celery_app

log = get_logger(__name__)

AGENT_INTENTS = {Intent.PARCELAR_DESCONTO, Intent.DUVIDA}


def phone_variants(phone: str) -> list[str]:
    """O WhatsApp às vezes entrega celular brasileiro sem o nono dígito."""
    variants = {phone}
    if phone.startswith("55") and len(phone) == 12:
        variants.add(phone[:4] + "9" + phone[4:])
    if phone.startswith("55") and len(phone) == 13 and phone[4] == "9":
        variants.add(phone[:4] + phone[5:])
    return list(variants)


WAITING_FOR_REPLY = (
    ConversationState.AGUARDANDO_IDENTIDADE,
    ConversationState.AGUARDANDO_COMPROVANTE,
    ConversationState.AGENTE,
)


def _matches_phone(phone: str):
    variants = phone_variants(phone)
    return or_(Debtor.phone.in_(variants), Debtor.phones.op("&&")(pg_array(variants)))


def find_debtor(session: Session, tenant_id: UUID, phone: str) -> Debtor | None:
    return session.scalars(
        select(Debtor).where(Debtor.tenant_id == tenant_id, _matches_phone(phone))
    ).first()


def conversation_for_phone(session: Session, tenant_id: UUID, phone: str) -> Conversation | None:
    """Quando vários cadastros compartilham o número, a conversa que espera
    resposta (identidade, comprovante) ganha da primeira da lista."""
    debtors = list(
        session.scalars(
            select(Debtor).where(Debtor.tenant_id == tenant_id, _matches_phone(phone))
        )
    )
    if not debtors:
        return None
    convs = list(
        session.scalars(
            select(Conversation).where(Conversation.tenant_id == tenant_id, Conversation.debtor_id.in_([d.id for d in debtors]))
        )
    )
    waiting = [c for c in convs if c.state in WAITING_FOR_REPLY]
    pool = waiting or [c for c in convs if c.state != ConversationState.ENCERRADA]
    if pool:
        return max(pool, key=lambda c: (c.state == ConversationState.AGUARDANDO_IDENTIDADE, c.updated_at))
    return None


def quoted_outbound(session: Session, tenant_id: UUID, quoted_id: str | None) -> Message | None:
    """Mensagem nossa que a pessoa citou ao responder."""
    if not quoted_id:
        return None
    return session.scalars(
        select(Message).where(Message.tenant_id == tenant_id, Message.wa_message_id == quoted_id)
    ).first()


class TurnInProgress(Exception):
    """Outro caminho (webhook ou reconciliação) já ficou com o turno desta mensagem."""


def fresh_inbound(session: Session, messages) -> list:
    """Mensagem cujo `wa_message_id` já está no banco não dispara outro turno."""
    fresh = []
    for msg in messages:
        if msg.message_id and session.scalar(
            select(Message.id).where(Message.wa_message_id == msg.message_id)
        ):
            continue
        fresh.append(msg)
    return fresh


def cache_inbound_media(tenant_id: str, msg) -> str | None:
    """Baixa a mídia na chegada e grava no MinIO antes de enfileirar o OCR."""
    if not msg.has_media:
        return None
    try:
        data, mimetype = EvolutionClient().get_media(msg.instance, msg.key)
    except Exception:
        record_file("recebido", "download")
        log.exception("inbound.media_cache_failed", message_id=msg.message_id)
        return None
    content_type = (mimetype or "application/octet-stream").split(";")[0].strip()
    return stage_receipt_bytes(tenant_id, data, content_type)


@celery_app.task(name="app.channels.tasks.process_inbound")
def process_inbound(tenant_id: str, buffer_key: str) -> str:
    messages = debounce_drain(buffer_key)
    if not messages:
        return "aguardando_rajada" if messages is None else "vazio"

    tid = UUID(tenant_id)
    first = messages[0]

    try:
        return _route_buffered(tenant_id, tid, messages, first)
    except TurnInProgress:
        return "turno_em_andamento"
    except Exception:
        record_message("entrada", "roteada", "roteamento", "texto", "falha")
        raise


def _route_buffered(tenant_id: str, tid: UUID, messages, first) -> str:
    media_keys: dict[str, str] = {}
    for msg in messages:
        if msg.has_media and msg.message_id and msg.message_id not in media_keys:
            key = cache_inbound_media(tenant_id, msg)
            if key:
                media_keys[msg.message_id] = key

    claimed_for: tuple[UUID, str] | None = None
    try:
        with tenant_session(tid) as session:
            pending = fresh_inbound(session, messages)
            if not pending:
                return "ja_gravada"
            first = pending[0]
            tenant = session.get(Tenant, tid)

            if first.is_group:
                # Grupo do cliente: só aceitamos comprovante. Nunca respondemos cobrança em grupo.
                for msg in pending:
                    if msg.has_media:
                        process_whatsapp_receipt.delay(
                            tenant_id, msg.instance, msg.key, msg.message_id,
                            None, None, None, media_keys.get(msg.message_id),
                        )
                    record_message(
                        "entrada", "roteada", "grupo",
                        "arquivo" if msg.has_media else "texto", "ok",
                    )
                return "grupo"

            quoted = quoted_outbound(session, tid, first.quoted_id)
            conv = session.get(Conversation, quoted.conversation_id) if quoted is not None else None
            if conv is None:
                conv = conversation_for_phone(session, tid, first.phone)
                quoted = None
            debtor = session.get(Debtor, conv.debtor_id) if conv is not None else find_debtor(session, tid, first.phone)
            if debtor is None:
                log.info("inbound.unknown_contact", tenant_id=tenant_id)
                for msg in pending:
                    record_message(
                        "entrada", "roteada", "contato_desconhecido",
                        "arquivo" if msg.has_media else "texto", "falha",
                    )
                return "contato_desconhecido"

            conv = conv or get_or_create_conversation(session, tid, debtor)
            token = first.message_id or ""
            if token and not claim_turn(conv.id, token):
                raise TurnInProgress
            if token:
                claimed_for = (conv.id, token)
            if first.remote_jid.endswith("@s.whatsapp.net"):
                conv.wa_jid = first.remote_jid
            for msg in pending:
                cited = quoted_outbound(session, tid, msg.quoted_id) or quoted
                if msg.has_media:
                    process_whatsapp_receipt.delay(
                        tenant_id, msg.instance, msg.key, msg.message_id,
                        str(conv.id), str(debtor.id), None, media_keys.get(msg.message_id),
                    )
                elif msg.text:
                    log_message(
                        session, conv, MessageDirection.IN, "devedor", msg.text,
                        invoice_id=cited.invoice_id if cited else None,
                        wa_message_id=msg.message_id,
                    )

            text = "\n".join(m.text for m in pending if m.text and not m.has_media).strip()
            outcome, turn = continue_after_inbound(session, tenant, debtor, conv, text)
            context = route_context(outcome, conv.intent)
            for msg in pending:
                if msg.has_media:
                    record_message("entrada", "roteada", "comprovante", "arquivo", "ok")
                elif msg.text:
                    record_message("entrada", "roteada", context, "texto", "ok")

        if turn is not None:
            run_agent_turn.delay(tenant_id, *turn, claimed_for[1] if claimed_for else None)
        return outcome
    except TurnInProgress:
        raise
    except Exception:
        if claimed_for is not None:
            release_turn(*claimed_for)
        raise


def continue_after_inbound(session, tenant, debtor, conv, text: str) -> tuple[str, tuple[str, str, str] | None]:
    """Roteia uma resposta já gravada. Devolve (outcome, turno_do_agente ou None)."""
    if not text or conv.state == ConversationState.HUMANO:
        return "sem_texto_ou_humano", None
    if conv.state == ConversationState.AGUARDANDO_APROVACAO:
        send_to_debtor(session, tenant, conv,
                       "Seu pedido está com nossa equipe. Retornamos assim que possível.")
        return "aguardando_aprovacao", None

    today = datetime.now(ZoneInfo(tenant.timezone)).date()

    if conv.state == ConversationState.AGUARDANDO_IDENTIDADE:
        conv_id = str(conv.id)
        intent = Intent(conv.intent) if conv.intent else Intent.DUVIDA
    elif re.fullmatch(r"\d{1,2}", text.strip()):
        # "6" depois de uma lista numerada é a opção, não um pedido para parar.
        intent = conv.intent or Intent.PARCELAR_DESCONTO
        conv.intent = intent
        return "agente", (str(conv.id), text.strip(), str(intent))
    else:
        result = classify_intent(text, today)
        intent = result.intent
        conv.intent = intent
        conv_id = str(conv.id)
        handled = _route_deterministic(session, tenant, debtor, conv, intent, result.promised_date, today)
        if handled:
            return handled, None

    return "agente", (conv_id, text, str(intent))


def _route_deterministic(session, tenant, debtor, conv, intent, promised_date, today) -> str | None:
    """Intenções que não passam pelo agente. Devolve None para seguir ao agente."""
    if intent == Intent.PARAR:
        debtor.opt_out = True
        debtor.opt_out_at = datetime.now(UTC)
        conv.state = ConversationState.ENCERRADA
        audit(session, tenant_id=tenant.id, actor="devedor", action="opt_out",
              entity="debtor", entity_id=debtor.id)
        send_to_debtor(session, tenant, conv,
                       "Entendido. Você não receberá mais mensagens automáticas de cobrança.")
        return "opt_out"

    if intent == Intent.HOSTIL_SENSIVEL:
        conv.state = ConversationState.HUMANO
        audit(session, tenant_id=tenant.id, actor="agente", action="escalona",
              entity="conversation", entity_id=conv.id, after={"intent": intent})
        send_to_debtor(session, tenant, conv,
                       "Entendo. Vou pedir para alguém da nossa equipe falar com você.")
        return "escalonado"

    if intent == Intent.CONTESTACAO:
        invoices = session.scalars(
            select(Invoice).where(Invoice.debtor_id == debtor.id, Invoice.status.in_(OPEN_INVOICE_STATUSES))
        ).all()
        for inv in invoices:
            if inv.status != InvoiceStatus.EM_NEGOCIACAO:
                set_invoice_status(inv, InvoiceStatus.CONTESTADO)
        open_exception(session, tenant.id, ExceptionType.CONTESTACAO, conversation_id=conv.id,
                       invoice_id=invoices[0].id if invoices else None,
                       details={"debtor_id": str(debtor.id)})
        conv.state = ConversationState.HUMANO
        send_to_debtor(session, tenant, conv,
                       "Obrigado por avisar. Vamos verificar com cuidado e nossa equipe retorna em breve.")
        return "contestacao"

    if intent == Intent.JA_PAGUEI:
        conv.state = ConversationState.AGUARDANDO_COMPROVANTE
        send_to_debtor(session, tenant, conv,
                       "Obrigado! Pode enviar o comprovante por aqui, em foto ou PDF?")
        return "pede_comprovante"

    if intent == Intent.VOU_PAGAR:
        if promised_date is None:
            send_to_debtor(session, tenant, conv, "Combinado! Em qual data você consegue pagar?")
            return "pede_data"
        try:
            register_promise(session, tenant, debtor.id, promised_date, today, "agente")
        except PromiseRejected as exc:
            send_to_debtor(session, tenant, conv, f"Não consigo registrar essa data: {exc}. Qual outra data?")
            return "promessa_recusada"
        send_to_debtor(session, tenant, conv,
                       f"Anotado! Fica combinado para {promised_date:%d/%m}. Se precisar de algo, é só chamar.")
        return "promessa"

    return None
