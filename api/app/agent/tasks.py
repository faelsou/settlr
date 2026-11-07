from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.agent import runner
from app.channels.outbound import send_to_debtor
from app.core.audit import audit
from app.core.db import tenant_session
from app.core.logging import get_logger
from app.models import Approval, Conversation, Debtor, Tenant
from app.models.enums import ApprovalStatus, ConversationState
from app.workers.celery_app import celery_app

log = get_logger(__name__)

OUTCOME_STATE = {
    "identidade_falhou": ConversationState.HUMANO,
    "aguardando_aprovacao": ConversationState.AGUARDANDO_APROVACAO,
}


def _deliver(tenant_id: UUID, conversation_id: UUID, result: dict) -> None:
    with tenant_session(tenant_id) as session:
        tenant = session.get(Tenant, tenant_id)
        conv = session.get(Conversation, conversation_id)
        conv.state = OUTCOME_STATE.get(result.get("outcome", ""), ConversationState.AGENTE)
        if result.get("awaiting_identity"):
            conv.state = ConversationState.AGUARDANDO_IDENTIDADE
        conv.identity_verified = bool(result.get("identity_verified"))
        conv.identity_attempts = result.get("identity_attempts", 0)
        for text in result.get("replies", []):
            send_to_debtor(session, tenant, conv, text, author="agente")


@celery_app.task(name="app.agent.tasks.run_agent_turn")
def run_agent_turn(
    tenant_id: str,
    conversation_id: str,
    text: str,
    intent: str,
    turn_token: str | None = None,
) -> str:
    tid, cid = UUID(tenant_id), UUID(conversation_id)
    try:
        with tenant_session(tid) as session:
            tenant = session.get(Tenant, tid)
            conv = session.get(Conversation, cid)
            debtor = session.get(Debtor, conv.debtor_id)
            state = {
                "tenant_id": tenant_id,
                "tenant_name": tenant.name,
                "conversation_id": conversation_id,
                "debtor_id": str(debtor.id),
                "debtor_document": debtor.document,
                "thread_id": conversation_id,
                "today": datetime.now(ZoneInfo(tenant.timezone)).date().isoformat(),
                "text": text,
                "intent": intent,
            }

        result = runner.run_turn(state)
        _deliver(tid, cid, result)
    except Exception:
        if turn_token:
            from app.channels.turn import release_turn

            release_turn(cid, turn_token)
        raise
    log.info("agent.turn", conversation_id=conversation_id, outcome=result.get("outcome"))
    return result.get("outcome", "")


@celery_app.task(name="app.agent.tasks.resume_agent")
def resume_agent(tenant_id: str, approval_id: str, approved: bool, message: str, actor: str) -> str:
    tid = UUID(tenant_id)
    with tenant_session(tid) as session:
        approval = session.get(Approval, UUID(approval_id))
        if approval.status != ApprovalStatus.PENDENTE:
            return approval.status
        approval.status = ApprovalStatus.APROVADA if approved else ApprovalStatus.REJEITADA
        approval.decided_by = actor
        approval.decided_at = datetime.now(UTC)
        audit(session, tenant_id=tid, actor=actor, action="decide_aprovacao",
              entity="approval", entity_id=approval.id,
              after={"approved": approved, "message": message})
        thread_id, conversation_id = approval.thread_id, approval.conversation_id

    result = runner.resume(thread_id, {"approved": approved, "message": message})
    _deliver(tid, conversation_id, result)
    return result.get("outcome", "")
