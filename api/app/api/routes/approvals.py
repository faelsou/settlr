from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tasks import resume_agent
from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.schemas import ApprovalOut, DebtorOut, DecideApprovalIn
from app.models import Approval, Conversation, Debtor
from app.models.enums import ApprovalStatus

router = APIRouter(prefix="/approvals", tags=["aprovacoes"])


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status: ApprovalStatus = ApprovalStatus.PENDENTE, db: Session = Depends(get_db)
) -> list[ApprovalOut]:
    rows = db.execute(
        select(Approval, Debtor)
        .join(Conversation, Conversation.id == Approval.conversation_id)
        .join(Debtor, Debtor.id == Conversation.debtor_id)
        .where(Approval.status == status)
        .order_by(Approval.created_at)
    ).all()
    return [
        ApprovalOut(
            id=a.id, conversation_id=a.conversation_id, debtor=DebtorOut.model_validate(d),
            reason=a.reason, payload=a.payload, status=a.status, decided_by=a.decided_by,
            created_at=a.created_at,
        )
        for a, d in rows
    ]


@router.post("/{approval_id}/decide", status_code=202)
def decide(
    approval_id: UUID,
    body: DecideApprovalIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> dict:
    """Retoma o grafo pausado. A mensagem é enviada ao devedor pelo agente."""
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(404, "aprovação não encontrada")
    if approval.status != ApprovalStatus.PENDENTE:
        raise HTTPException(409, "aprovação já decidida")
    resume_agent.delay(
        str(user.tenant_id), str(approval_id), body.approved, body.message, user.actor
    )
    return {"status": "enfileirado"}
