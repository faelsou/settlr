from uuid import UUID

import httpx

from app.channels.delivery import RECEIPT_BODY
from app.channels.metrics import record_file
from app.channels.outbound import log_message, send_to_debtor
from app.channels.turn import claim_once, release_once
from app.channels.whatsapp import EvolutionClient
from app.core import storage
from app.core.db import tenant_session
from app.core.logging import get_logger
from app.models import Conversation, Tenant
from app.models.enums import ConversationState, MessageDirection
from app.receipts.service import content_type_from_key, process_receipt, stage_receipt_bytes
from app.workers.celery_app import celery_app

log = get_logger(__name__)

REPLIES = {
    "duplicado": "Este comprovante já tinha sido recebido. Obrigado!",
    "ja_recebido": "Recebemos seu comprovante e o pagamento já consta para nós. Obrigado!",
    "aguardando_banco": (
        "Recebemos seu comprovante, obrigado! Assim que o banco confirmar a entrada, "
        "damos baixa e avisamos por aqui."
    ),
    "baixa_confianca": (
        "Recebemos o arquivo, mas não conseguimos ler todos os dados. Nossa equipe vai "
        "conferir e retornar em breve."
    ),
}


@celery_app.task(
    bind=True, autoretry_for=(httpx.TransportError,), retry_backoff=True, max_retries=3,
    name="app.receipts.tasks.process_whatsapp_receipt",
)
def process_whatsapp_receipt(
    self,
    tenant_id: str,
    instance: str,
    message_key: dict,
    message_id: str,
    conversation_id: str | None = None,
    debtor_id: str | None = None,
    message_raw: dict | None = None,
    media_key: str | None = None,
) -> str:
    token = f"receipt:{message_id}"
    if not claim_once(token):
        return "duplicado"
    try:
        data, content_type, media_key = load_receipt_bytes(
            tenant_id, instance, message_key, message_raw, media_key,
        )
    except Exception:
        release_once(token)
        record_file("recebido", "download")
        raise
    try:
        return _store_receipt(
            tenant_id, data, content_type, message_id, conversation_id, debtor_id, media_key,
        )
    except Exception:
        release_once(token)
        raise


def load_receipt_bytes(
    tenant_id: str,
    instance: str,
    message_key: dict,
    message_raw: dict | None,
    media_key: str | None,
) -> tuple[bytes, str, str]:
    """A cópia no MinIO existe antes do OCR. Se a chegada já gravou, lê de lá."""
    if media_key:
        try:
            return storage.get_object(media_key), content_type_from_key(media_key), media_key
        except Exception:
            log.warning("receipt.stored_copy_missing", media_key=media_key)
    data, mimetype = EvolutionClient().get_media(instance, message_key, raw=message_raw)
    content_type = mimetype.split(";")[0].strip()
    key = stage_receipt_bytes(tenant_id, data, content_type)
    return data, content_type, key


def _store_receipt(
    tenant_id: str,
    data: bytes,
    content_type: str,
    message_id: str,
    conversation_id: str | None,
    debtor_id: str | None,
    file_key: str | None = None,
) -> str:
    with tenant_session(UUID(tenant_id)) as session:
        tenant = session.get(Tenant, UUID(tenant_id))
        try:
            outcome = process_receipt(
                session, tenant, data, content_type,
                debtor_id=UUID(debtor_id) if debtor_id else None,
                source={"channel": "whatsapp", "message_id": message_id},
                file_key=file_key,
            )
        except Exception:
            record_file("recebido", "processamento")
            raise
        log.info("receipt.processed", tenant_id=tenant_id, status=outcome.status,
                 payment_id=str(outcome.payment_id) if outcome.payment_id else None)
        status = outcome.status

        if conversation_id:
            conv = session.get(Conversation, UUID(conversation_id))
            log_message(session, conv, MessageDirection.IN, "devedor", RECEIPT_BODY,
                        wa_message_id=message_id, media_key=file_key)
            if conv.state == ConversationState.AGUARDANDO_COMPROVANTE:
                conv.state = ConversationState.AGENTE
            if conv.state != ConversationState.HUMANO:
                send_to_debtor(session, tenant, conv, REPLIES.get(status, REPLIES["aguardando_banco"]))
    record_file("recebido", status)
    return status
