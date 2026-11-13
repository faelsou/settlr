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
from app.channels.speech import hear
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
UNHEARD_REPLY = "Não consegui ouvir o áudio. Nossa equipe vai conferir e retornar."


def message_kind(msg) -> str:
    if msg.is_audio:
        return "audio"
    if msg.is_receipt:
        return "arquivo"
    return "texto"


def turn_text(messages, heard: dict[str, str | None]) -> tuple[str, bool]:
    """Texto do turno e se ele nasceu de uma transcrição.

    Áudio sem transcrição não entra. Legenda escrita no áudio entra, porque
    a pessoa digitou. Comprovante não vira frase.
    """
    parts: list[str] = []
    voice = False
    for msg in messages:
        if msg.is_audio:
            spoken = (heard.get(msg.message_id) or "").strip()
            caption = (msg.text or "").strip()
            if spoken:
                parts.append(spoken)
                voice = True
            if caption and caption != spoken:
                parts.append(caption)
            continue
        if msg.is_receipt:
            continue
        caption = (msg.text or "").strip()
        if caption:
            parts.append(caption)
    return "\n".join(parts).strip(), voice


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
    if not msg.is_receipt:
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
        if msg.is_receipt and msg.message_id and msg.message_id not in media_keys:
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
                # Grupo do cliente: só aceitamos comprovante. Áudio não vai ao OCR
                # e não recebe resposta de cobrança, em texto nem em voz.
                for msg in pending:
                    if msg.is_receipt:
                        process_whatsapp_receipt.delay(
                            tenant_id, msg.instance, msg.key, msg.message_id,
                            None, None, None, media_keys.get(msg.message_id),
                        )
                    record_message("entrada", "roteada", "grupo", message_kind(msg), "ok")
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
                        "entrada", "roteada", "contato_desconhecido", message_kind(msg), "falha",
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

            heard = _hear_pending(tenant_id, pending)
            transcripts = {mid: item[0] for mid, item in heard.items()}
            text, voice = turn_text(pending, transcripts)
            replied_unheard = False
            for msg in pending:
                cited = quoted_outbound(session, tid, msg.quoted_id) or quoted
                invoice_id = cited.invoice_id if cited else None
                if msg.is_audio:
                    spoken = (transcripts.get(msg.message_id) or "").strip()
                    caption = (msg.text or "").strip()
                    reply = not text and not spoken and not caption and not replied_unheard
                    _record_audio(
                        session, tenant, conv, msg, heard.get(msg.message_id), invoice_id,
                        reply=reply,
                    )
                    replied_unheard = replied_unheard or reply
                elif msg.is_receipt:
                    process_whatsapp_receipt.delay(
                        tenant_id, msg.instance, msg.key, msg.message_id,
                        str(conv.id), str(debtor.id), None, media_keys.get(msg.message_id),
                    )
                elif msg.text:
                    log_message(
                        session, conv, MessageDirection.IN, "devedor", msg.text,
                        invoice_id=invoice_id, wa_message_id=msg.message_id,
                    )

            if not text:
                failed_audio = any(
                    msg.is_audio and not (transcripts.get(msg.message_id) or "").strip()
                    for msg in pending
                )
                outcome, turn = (
                    ("sem_transcricao", None) if failed_audio else ("sem_texto_ou_humano", None)
                )
            else:
                outcome, turn = continue_after_inbound(
                    session, tenant, debtor, conv, text, reply_voice=voice,
                )
            context = route_context(outcome, conv.intent)
            for msg in pending:
                if msg.is_receipt:
                    record_message("entrada", "roteada", "comprovante", "arquivo", "ok")
                elif msg.is_audio or msg.text:
                    record_message("entrada", "roteada", context, message_kind(msg), "ok")

        if turn is not None:
            run_agent_turn.delay(
                tenant_id, *turn, claimed_for[1] if claimed_for else None, voice,
            )
        return outcome
    except TurnInProgress:
        raise
    except Exception:
        if claimed_for is not None:
            release_turn(*claimed_for)
        raise


def _hear_pending(tenant_id: str, pending) -> dict[str, tuple[str | None, str | None, str | None]]:
    heard: dict[str, tuple[str | None, str | None, str | None]] = {}
    for msg in pending:
        if msg.is_audio and msg.message_id and msg.message_id not in heard:
            heard[msg.message_id] = hear(tenant_id, msg.instance, msg.key)
    return heard


def _record_audio(session, tenant, conv, msg, heard, invoice_id, *, reply: bool):
    """Grava a transcrição. Sem ela, abre exceção e não inventa a frase."""
    transcript, media_key, content_type = heard or (None, None, None)
    spoken = (transcript or "").strip()
    caption = (msg.text or "").strip()
    body = spoken
    if caption and caption != spoken:
        body = f"{spoken}\n{caption}".strip() if spoken else caption
    stored = log_message(
        session, conv, MessageDirection.IN, "devedor", body or None,
        invoice_id=invoice_id, media_key=media_key, wa_message_id=msg.message_id,
    )
    if spoken:
        return stored
    open_exception(
        session, tenant.id, ExceptionType.TRANSCRICAO_INDISPONIVEL,
        invoice_id=invoice_id, conversation_id=conv.id,
        details={
            "motivo": "áudio sem transcrição utilizável",
            "message_id": msg.message_id,
            "file_key": media_key,
            "content_type": content_type,
        },
    )
    if reply:
        conv.state = ConversationState.HUMANO
        send_to_debtor(session, tenant, conv, UNHEARD_REPLY)
    return stored


def continue_after_inbound(
    session, tenant, debtor, conv, text: str, *, reply_voice: bool = False,
) -> tuple[str, tuple[str, str, str] | None]:
    """Roteia uma resposta já gravada. Devolve (outcome, turno_do_agente ou None)."""
    if not text or conv.state == ConversationState.HUMANO:
        return "sem_texto_ou_humano", None
    if conv.state == ConversationState.AGUARDANDO_APROVACAO:
        send_to_debtor(
            session, tenant, conv,
            "Seu pedido está com nossa equipe. Retornamos assim que possível.",
            voice=reply_voice,
        )
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
        handled = _route_deterministic(
            session, tenant, debtor, conv, intent, result.promised_date, today,
            reply_voice=reply_voice,
        )
        if handled:
            return handled, None

    return "agente", (conv_id, text, str(intent))


def _route_deterministic(
    session, tenant, debtor, conv, intent, promised_date, today, *, reply_voice: bool = False,
) -> str | None:
    """Intenções que não passam pelo agente. Devolve None para seguir ao agente."""
    def reply(text: str) -> None:
        send_to_debtor(session, tenant, conv, text, voice=reply_voice)

    if intent == Intent.PARAR:
        debtor.opt_out = True
        debtor.opt_out_at = datetime.now(UTC)
        conv.state = ConversationState.ENCERRADA
        audit(session, tenant_id=tenant.id, actor="devedor", action="opt_out",
              entity="debtor", entity_id=debtor.id)
        reply("Entendido. Você não receberá mais mensagens automáticas de cobrança.")
        return "opt_out"

    if intent == Intent.HOSTIL_SENSIVEL:
        conv.state = ConversationState.HUMANO
        audit(session, tenant_id=tenant.id, actor="agente", action="escalona",
              entity="conversation", entity_id=conv.id, after={"intent": intent})
        reply("Entendo. Vou pedir para alguém da nossa equipe falar com você.")
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
        reply("Obrigado por avisar. Vamos verificar com cuidado e nossa equipe retorna em breve.")
        return "contestacao"

    if intent == Intent.JA_PAGUEI:
        conv.state = ConversationState.AGUARDANDO_COMPROVANTE
        reply("Obrigado! Pode enviar o comprovante por aqui, em foto ou PDF?")
        return "pede_comprovante"

    if intent == Intent.VOU_PAGAR:
        if promised_date is None:
            reply("Combinado! Em qual data você consegue pagar?")
            return "pede_data"
        try:
            register_promise(session, tenant, debtor.id, promised_date, today, "agente")
        except PromiseRejected as exc:
            reply(f"Não consigo registrar essa data: {exc}. Qual outra data?")
            return "promessa_recusada"
        reply(f"Anotado! Fica combinado para {promised_date:%d/%m}. Se precisar de algo, é só chamar.")
        return "promessa"

    return None
