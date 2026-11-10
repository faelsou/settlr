"""Baixa que volta ao emissor. Entra cobrança do Asaas (`pay_`) ou do Inter (UUID)."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.ingest.issuers import _INTER_CHARGE
from app.models import AuditLog, Invoice, Match, Payment, Tenant
from app.models.enums import InvoiceStatus

ASAAS_CHARGE = re.compile(r"^pay_[A-Za-z0-9]+$")


@dataclass(frozen=True)
class IssuerSettlement:
    invoice_id: UUID
    charge_id: str
    paid_on: date
    value: Decimal


def tenant_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def charge_id_for(provider: str | None, external_id: str | None, txid: str | None) -> str | None:
    pattern = {"asaas": ASAAS_CHARGE, "inter": _INTER_CHARGE}.get(provider or "")
    if pattern is None:
        return None
    for candidate in (external_id, txid):
        if candidate and pattern.fullmatch(candidate):
            return candidate
    return None


def paid_by_issuer(raw: dict | None, provider: str) -> bool:
    if not raw:
        return False
    if raw.get("provider") == provider:
        return True
    bank = raw.get("bank")
    return isinstance(bank, dict) and bank.get("provider") == provider


def _audited(session: Session, invoice_id: UUID) -> bool:
    found = session.scalars(
        select(AuditLog.id).where(
            AuditLog.action == "baixa_emissor",
            AuditLog.entity == "invoice",
            AuditLog.entity_id == str(invoice_id),
        )
    ).first()
    return found is not None


def record_issuer_settlement(
    session: Session,
    tenant_id: UUID,
    invoice_id: UUID,
    *,
    charge_id: str | None,
    result: str,
    paid_on: date | None = None,
    value: Decimal | None = None,
) -> None:
    if _audited(session, invoice_id):
        return
    after = {"resultado": result}
    if charge_id:
        after["charge_id"] = charge_id
    if paid_on is not None:
        after["data"] = paid_on.isoformat()
    if value is not None:
        after["valor"] = f"{value.quantize(Decimal('0.01'))}"
    audit(
        session, tenant_id=tenant_id, actor="sistema", action="baixa_emissor",
        entity="invoice", entity_id=invoice_id, after=after,
    )


def plan_issuer_settlements(
    session: Session, tenant: Tenant, invoice_ids: list[UUID],
) -> tuple[list[IssuerSettlement], list[tuple[UUID, str]]]:
    """Separa o que ainda precisa de HTTP do que o emissor já quitou ou não é cobrança dele."""
    provider = tenant.issuer_provider or ""
    zone = tenant_zone(tenant.timezone)
    work: list[IssuerSettlement] = []
    skipped: list[tuple[UUID, str]] = []
    for invoice_id in invoice_ids:
        invoice = session.get(Invoice, invoice_id)
        if invoice is None or invoice.status != InvoiceStatus.PAGO:
            skipped.append((invoice_id, "ignorado"))
            continue
        charge_id = charge_id_for(provider, invoice.external_id, invoice.txid)
        if charge_id is None:
            skipped.append((invoice_id, "sem_cobranca"))
            continue
        payments = session.execute(
            select(Payment)
            .join(Match, Match.payment_id == Payment.id)
            .where(Match.invoice_id == invoice.id, Match.provisional.is_(False))
        ).scalars().all()
        if any(paid_by_issuer(payment.raw, provider) for payment in payments):
            skipped.append((invoice_id, "ja_no_emissor"))
            continue
        if not payments:
            skipped.append((invoice_id, "ignorado"))
            continue
        latest = max(payments, key=lambda payment: payment.paid_at)
        paid_at = latest.paid_at
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=zone)
        work.append(
            IssuerSettlement(
                invoice_id=invoice.id,
                charge_id=charge_id,
                paid_on=paid_at.astimezone(zone).date(),
                value=invoice.amount,
            )
        )
    return work, skipped
