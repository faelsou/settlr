"""Processamento de comprovante (FLUXOS.md §9): hash → dedupe → LLM → validação → payment."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.audit import audit
from app.core.config import get_settings
from app.models import Payment, Tenant
from app.models.enums import ExceptionType, PaymentOrigin, PaymentStatus
from app.reconciliation.matcher import Decision, document_matches
from app.reconciliation.service import open_exception, reconcile_payment
from app.receipts.extractor import extract_receipt
from app.receipts.schemas import ReceiptExtraction
from app.receipts.validation import validate_extraction

EXTENSIONS = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_BY_EXT = {ext: mime for mime, ext in EXTENSIONS.items()}


def stage_receipt_bytes(tenant_id: UUID | str, data: bytes, content_type: str) -> str:
    """Grava a cópia no MinIO antes de qualquer leitura. A chave é o hash do arquivo."""
    content_type = content_type.split(";")[0].strip() or "application/octet-stream"
    file_hash = hashlib.sha256(data).hexdigest()
    ext = EXTENSIONS.get(content_type, "bin")
    key = f"{tenant_id}/{file_hash}.{ext}"
    storage.put_object(key, data, content_type)
    return key


def content_type_from_key(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower()
    return _BY_EXT.get(ext, "application/octet-stream")


@dataclass
class ReceiptOutcome:
    status: str  # duplicado | ja_recebido | baixa_confianca | aguardando_banco
    payment_id: UUID | None = None
    problems: list[str] = field(default_factory=list)
    provisional_match: bool = False


def _find_bank_twin(session: Session, tenant_id: UUID, data: ReceiptExtraction) -> Payment | None:
    """Pagamento que o banco já informou antes do comprovante chegar."""
    if data.e2e_id:
        found = session.scalars(
            select(Payment).where(Payment.tenant_id == tenant_id, Payment.e2e_id == data.e2e_id.strip())
        ).first()
        if found:
            return found
    if data.amount is None or data.paid_at is None:
        return None
    candidates = session.scalars(
        select(Payment).where(
            Payment.tenant_id == tenant_id,
            Payment.bank_confirmed_at.is_not(None),
            Payment.file_hash.is_(None),
            Payment.amount == data.amount,
            Payment.paid_at.between(data.paid_at - timedelta(days=1), data.paid_at + timedelta(days=1)),
        )
    ).all()
    if data.payer_doc:
        candidates = [p for p in candidates if p.payer_doc and document_matches(data.payer_doc, p.payer_doc)]
    return candidates[0] if len(candidates) == 1 else None


def process_receipt(
    session: Session,
    tenant: Tenant,
    data: bytes,
    content_type: str,
    *,
    debtor_id: UUID | None = None,
    source: dict | None = None,
    extractor: Callable[[bytes, str], ReceiptExtraction] = extract_receipt,
    file_key: str | None = None,
) -> ReceiptOutcome:
    file_hash = hashlib.sha256(data).hexdigest()
    duplicate = session.scalars(
        select(Payment.id).where(Payment.tenant_id == tenant.id, Payment.file_hash == file_hash)
    ).first()
    if duplicate:
        return ReceiptOutcome("duplicado", duplicate)

    content_type = content_type.split(";")[0].strip()
    if file_key is None:
        file_key = stage_receipt_bytes(tenant.id, data, content_type)

    extraction = extractor(data, content_type)
    now = datetime.now(UTC)
    problems = validate_extraction(extraction, now, get_settings().receipt_min_confidence)
    if problems:
        open_exception(
            session, tenant.id, ExceptionType.LEITURA_BAIXA_CONFIANCA,
            details={
                "file_key": file_key,
                "content_type": content_type,
                "problems": problems,
                "extraction": extraction.model_dump(mode="json"),
                "debtor_id": str(debtor_id) if debtor_id else None,
                "source": source or {},
            },
        )
        return ReceiptOutcome("baixa_confianca", problems=problems)

    twin = _find_bank_twin(session, tenant.id, extraction)
    if twin is not None:
        twin.file_hash = twin.file_hash or file_hash
        twin.file_key = twin.file_key or file_key
        twin.content_type = twin.content_type or content_type
        twin.debtor_id = twin.debtor_id or debtor_id
        twin.raw = {**twin.raw, "receipt": extraction.model_dump(mode="json")}
        return ReceiptOutcome("ja_recebido", twin.id)

    payment = Payment(
        tenant_id=tenant.id,
        origin=PaymentOrigin.COMPROVANTE,
        status=PaymentStatus.AGUARDANDO_BANCO,
        amount=extraction.amount,
        paid_at=extraction.paid_at if extraction.paid_at.tzinfo else extraction.paid_at.replace(tzinfo=UTC),
        e2e_id=extraction.e2e_id.strip() if extraction.e2e_id else None,
        payer_doc=extraction.payer_doc,
        payer_name=extraction.payer_name,
        payer_bank=extraction.bank,
        debtor_id=debtor_id,
        file_hash=file_hash,
        file_key=file_key,
        content_type=content_type,
        extraction_confidence=extraction.confidence,
        raw={"receipt": extraction.model_dump(mode="json"), "source": source or {}},
    )
    session.add(payment)
    session.flush()
    audit(session, tenant_id=tenant.id, actor="sistema", action="registra_comprovante",
          entity="payment", entity_id=payment.id,
          after={"amount": payment.amount, "e2e_id": payment.e2e_id})

    result = reconcile_payment(session, payment, tenant)
    return ReceiptOutcome(
        "aguardando_banco", payment.id,
        provisional_match=result.decision in (Decision.AUTO, Decision.PARTIAL),
    )
