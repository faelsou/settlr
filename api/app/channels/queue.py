"""Fila de entrega do painel.

Lê `messages` no banco. A Evolution entra no webhook e na reconciliação,
nunca na montagem desta lista.
"""

from sqlalchemy import or_, select

from app.channels.delivery import FALHOU, RECEIPT_BODY
from app.models import Conversation, Debtor, Message
from app.models.enums import MessageDirection


def deliveries_statement(*, failed_only: bool):
    """Saída, mais entrada que é arquivo. `failed_only` deixa a falha de entrega."""
    query = (
        select(Message, Debtor.name)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Debtor, Debtor.id == Conversation.debtor_id)
        .where(
            or_(
                Message.direction == MessageDirection.OUT,
                Message.media_key.is_not(None),
                Message.body == RECEIPT_BODY,
            )
        )
        .order_by(Message.created_at.desc())
    )
    if failed_only:
        query = query.where(Message.delivery_status == FALHOU)
    return query
