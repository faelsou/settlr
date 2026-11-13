"""Envio 1:1 ao devedor com registro da mensagem.

Texto livre sai por aqui: resposta do agente, do operador e do comprovante.
A régua não usa este caminho. Disparo proativo vai por template oficial.

Nota de voz só sai quando o chamador pede e o horário do tenant permite.
O texto dessa resposta fica na conversa mesmo assim. Fora do horário, ou se
a síntese falhar, a mesma frase sai escrita. Grupo não recebe voz.

A linha nasce `pendente` antes da chamada HTTP. Timeout de transporte não apaga
o registro: a transação segue e a reconciliação acha a mensagem.
"""

from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.delivery import ACEITO, PENDENTE
from app.channels.metrics import outbound_context, record_message
from app.channels.speech import synthesize
from app.channels.whatsapp import GROUP_SUFFIX, EvolutionClient
from app.core.phones import contact_phones
from app.dunning.rules import AllowedHours, within_allowed_hours
from app.models import Conversation, Debtor, Message, Tenant
from app.models.enums import MessageDirection


def get_or_create_conversation(session: Session, tenant_id: UUID, debtor: Debtor) -> Conversation:
    conv = session.scalars(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id, Conversation.debtor_id == debtor.id
        )
    ).first()
    if conv is None:
        numbers = contact_phones(debtor.phone, debtor.phones)
        number = numbers[0] if numbers else debtor.phone
        conv = Conversation(
            tenant_id=tenant_id, debtor_id=debtor.id, wa_jid=f"{number}@s.whatsapp.net"
        )
        session.add(conv)
        session.flush()
    return conv


def log_message(
    session: Session,
    conv: Conversation,
    direction: MessageDirection,
    author: str,
    body: str | None,
    *,
    invoice_id: UUID | None = None,
    media_key: str | None = None,
    wa_message_id: str | None = None,
    delivery_status: str | None = None,
) -> Message:
    msg = Message(
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        invoice_id=invoice_id,
        direction=direction,
        author=author,
        body=body,
        media_key=media_key,
        wa_message_id=wa_message_id,
        delivery_status=delivery_status,
    )
    session.add(msg)
    return msg


def voice_reply_allowed(tenant: Tenant, conv: Conversation, now: datetime) -> bool:
    """Voz só na resposta 1:1, dentro do horário do tenant. Grupo fica de fora."""
    if (conv.wa_jid or "").endswith(GROUP_SUFFIX):
        return False
    tz = getattr(tenant, "timezone", None) or "America/Sao_Paulo"
    hours = AllowedHours.from_json(getattr(tenant, "allowed_hours", None))
    return within_allowed_hours(now, hours, tz)


def send_to_debtor(
    session: Session,
    tenant: Tenant,
    conv: Conversation,
    text: str,
    *,
    author: str = "agente",
    invoice_id: UUID | None = None,
    client: EvolutionClient | None = None,
    voice: bool = False,
    now: datetime | None = None,
) -> Message:
    context = outbound_context(author, conv.intent)
    if conv.wa_jid.endswith(GROUP_SUFFIX):
        record_message("saida", "enviada", context, "audio" if voice else "texto", "falha")
        raise ValueError("nunca cobrar em grupo")
    if not tenant.whatsapp_instance:
        record_message("saida", "enviada", context, "audio" if voice else "texto", "falha")
        raise ValueError("tenant sem instância de WhatsApp")

    msg = log_message(
        session, conv, MessageDirection.OUT, author, text,
        invoice_id=invoice_id, delivery_status=PENDENTE,
    )
    session.flush()
    number = conv.wa_jid.split("@", 1)[0]
    sender = client or EvolutionClient()
    moment = now or datetime.now(UTC)
    try:
        message_id, kind = _dispatch(sender, tenant, conv, number, text, voice=voice, now=moment)
    except (httpx.TimeoutException, httpx.TransportError):
        record_message("saida", "enviada", context, "audio" if voice else "texto", "falha")
        return msg
    except Exception:
        record_message("saida", "enviada", context, "audio" if voice else "texto", "falha")
        raise
    msg.wa_message_id = message_id
    msg.delivery_status = ACEITO
    record_message("saida", "enviada", context, kind, "ok")
    return msg


def _dispatch(
    sender, tenant, conv, number: str, text: str, *, voice: bool, now: datetime,
) -> tuple[str | None, str]:
    if voice and voice_reply_allowed(tenant, conv, now):
        audio = synthesize(text)
        if audio:
            return sender.send_audio(tenant.whatsapp_instance, number, audio), "audio"
    return sender.send_text(tenant.whatsapp_instance, number, text), "texto"
