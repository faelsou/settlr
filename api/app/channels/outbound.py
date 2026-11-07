"""Envio 1:1 ao devedor com registro da mensagem. Todo texto que sai passa por aqui."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.metrics import outbound_context, record_message
from app.channels.whatsapp import GROUP_SUFFIX, EvolutionClient
from app.core.phones import contact_phones
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


def send_to_debtor(
    session: Session,
    tenant: Tenant,
    conv: Conversation,
    text: str,
    *,
    author: str = "agente",
    invoice_id: UUID | None = None,
    client: EvolutionClient | None = None,
) -> str | None:
    context = outbound_context(author, conv.intent)
    try:
        if conv.wa_jid.endswith(GROUP_SUFFIX):
            raise ValueError("nunca cobrar em grupo")
        if not tenant.whatsapp_instance:
            raise ValueError("tenant sem instância de WhatsApp")
        number = conv.wa_jid.split("@", 1)[0]
        message_id = (client or EvolutionClient()).send_text(tenant.whatsapp_instance, number, text)
    except Exception:
        record_message("saida", "enviada", context, "texto", "falha")
        raise
    log_message(
        session, conv, MessageDirection.OUT, author, text,
        invoice_id=invoice_id, wa_message_id=message_id,
    )
    record_message("saida", "enviada", context, "texto", "ok")
    return message_id
