from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.schemas import (
    ConversationOut,
    DebtorOut,
    DeliveryOut,
    MessageOut,
    Page,
    SendMessageIn,
    message_out,
)
from app.channels.delivery import file_state
from app.channels.outbound import send_to_debtor
from app.channels.queue import deliveries_statement
from app.core.audit import audit
from app.models import Conversation, Debtor, Message, Tenant
from app.models.enums import ConversationState

router = APIRouter(prefix="/conversations", tags=["conversas"])


def _out(conv: Conversation, debtor: Debtor) -> ConversationOut:
    return ConversationOut(
        id=conv.id, debtor=DebtorOut.model_validate(debtor), intent=conv.intent, state=conv.state,
        summary=conv.summary, identity_verified=conv.identity_verified,
        assigned_to=conv.assigned_to, updated_at=conv.updated_at,
    )


def _get(db: Session, conversation_id: UUID) -> tuple[Conversation, Debtor]:
    row = db.execute(
        select(Conversation, Debtor)
        .join(Debtor, Debtor.id == Conversation.debtor_id)
        .where(Conversation.id == conversation_id)
    ).first()
    if row is None:
        raise HTTPException(404, "conversa não encontrada")
    return row[0], row[1]


@router.get("", response_model=Page[ConversationOut])
def list_conversations(
    state: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Page[ConversationOut]:
    query = select(Conversation, Debtor).join(Debtor, Debtor.id == Conversation.debtor_id)
    if state:
        query = query.where(Conversation.state == state)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[_out(c, d) for c, d in rows], total=total or 0)


@router.get("/deliveries", response_model=Page[DeliveryOut])
def list_deliveries(
    falhou: bool = False,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Page[DeliveryOut]:
    """Fila do operador. O status já está em `messages`; esta rota não chama a Evolution."""
    query = deliveries_statement(failed_only=falhou)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.limit(limit).offset(offset)).all()
    return Page(
        items=[
            DeliveryOut(
                id=message.id,
                conversation_id=message.conversation_id,
                invoice_id=message.invoice_id,
                debtor_name=debtor_name,
                direction=message.direction,
                body=message.body,
                delivery_status=message.delivery_status,
                file_status=file_state(message.body, message.media_key),
                created_at=message.created_at,
            )
            for message, debtor_name in rows
        ],
        total=total,
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: UUID, db: Session = Depends(get_db)) -> list[MessageOut]:
    _get(db, conversation_id)
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    ).all()
    return [message_out(m) for m in messages]


@router.post("/{conversation_id}/takeover", response_model=ConversationOut)
def takeover(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> ConversationOut:
    conv, debtor = _get(db, conversation_id)
    before = {"state": conv.state, "assigned_to": conv.assigned_to}
    conv.state = ConversationState.HUMANO
    conv.assigned_to = user.email
    audit(db, tenant_id=conv.tenant_id, actor=user.actor, action="assume_conversa",
          entity="conversation", entity_id=conv.id, before=before, after={"state": conv.state})
    return _out(conv, debtor)


@router.post("/{conversation_id}/release", response_model=ConversationOut)
def release(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> ConversationOut:
    conv, debtor = _get(db, conversation_id)
    if conv.state == ConversationState.AGUARDANDO_APROVACAO:
        raise HTTPException(409, "decida a aprovação pendente antes de devolver ao agente")
    conv.state = ConversationState.AGENTE
    conv.assigned_to = None
    audit(db, tenant_id=conv.tenant_id, actor=user.actor, action="devolve_ao_agente",
          entity="conversation", entity_id=conv.id)
    return _out(conv, debtor)


@router.post("/{conversation_id}/messages", response_model=MessageOut)
def send_message(
    conversation_id: UUID,
    body: SendMessageIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> MessageOut:
    conv, debtor = _get(db, conversation_id)
    if conv.state != ConversationState.HUMANO:
        raise HTTPException(409, "assuma a conversa antes de enviar mensagens")
    if debtor.opt_out:
        raise HTTPException(409, "devedor pediu para não receber mensagens")
    send_to_debtor(db, db.get(Tenant, conv.tenant_id), conv, body.text, author=user.actor)
    db.flush()
    last = db.scalars(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.desc())
    ).first()
    return message_out(last)
