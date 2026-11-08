"""Tools do agente (FLUXOS.md §7). Todas tipadas e só devolvem o que a política permite.

O grafo chama as tools de forma determinística; o LLM nunca recebe uma tool que
grave dinheiro sem passar pelas validações daqui.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from langchain_core.tools import tool
from pydantic import BaseModel
from sqlalchemy import select

from app.agent.policy import Installment, NegotiationPolicy, build_payment_options
from app.core.audit import audit
from app.core.db import tenant_session
from app.dunning.promises import register_promise as _register_promise
from app.ingest.issuers import IssuedCharge, get_adapter
from app.models import Agreement, Approval, Conversation, Debtor, Invoice, Tenant
from app.models.enums import (
    OPEN_INVOICE_STATUSES,
    ApprovalStatus,
    ConversationState,
    InvoiceStatus,
)
from app.reconciliation.service import set_invoice_status

NEGOTIABLE = OPEN_INVOICE_STATUSES


def _installment_invoice(
    session,
    tenant_id: UUID,
    debtor_id: UUID,
    parent_id: UUID,
    agreement_id: UUID,
    inst: Installment,
    charge: IssuedCharge,
    total: int,
) -> Invoice:
    """Grava a parcela com o código do emissor. Se o webhook chegou antes, completa a linha."""
    description = f"Acordo parcela {inst.number}/{total}"
    existing = session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.external_id == charge.external_id,
        )
    ).first()
    if existing is not None:
        existing.parent_id = parent_id
        existing.agreement_id = agreement_id
        existing.description = existing.description or description
        existing.pix_copy_paste = charge.pix_copy_paste or existing.pix_copy_paste
        existing.digitable_line = charge.digitable_line or existing.digitable_line
        existing.payment_url = charge.payment_url or existing.payment_url
        existing.txid = charge.txid
        if existing.status == InvoiceStatus.ABERTO:
            set_invoice_status(existing, InvoiceStatus.EM_COBRANCA)
        return existing

    new = Invoice(
        tenant_id=tenant_id,
        debtor_id=debtor_id,
        external_id=charge.external_id,
        description=description,
        amount=inst.amount,
        amount_paid=Decimal("0"),
        due_date=inst.due_date,
        status=InvoiceStatus.EM_COBRANCA,
        txid=charge.txid,
        digitable_line=charge.digitable_line,
        pix_copy_paste=charge.pix_copy_paste,
        payment_url=charge.payment_url,
        parent_id=parent_id,
        agreement_id=agreement_id,
    )
    session.add(new)
    return new


class DebtorRef(BaseModel):
    tenant_id: UUID
    debtor_id: UUID


class PolicyRef(BaseModel):
    tenant_id: UUID


class OptionsInput(BaseModel):
    total_open: Decimal
    policy: dict
    today: date


class PromiseInput(BaseModel):
    tenant_id: UUID
    debtor_id: UUID
    promised_date: date
    today: date


class AgreementInput(BaseModel):
    tenant_id: UUID
    debtor_id: UUID
    invoice_ids: list[UUID]
    option_id: str
    today: date


class HumanRequestInput(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    thread_id: str
    reason: str
    payload: dict


def _invoice_dict(inv: Invoice) -> dict:
    return {
        "id": str(inv.id),
        "description": inv.description or f"título {inv.external_id}",
        "amount_open": str(inv.amount_open),
        "due_date": inv.due_date.isoformat(),
        "status": inv.status,
        "payment_url": inv.payment_url,
        "pix_copy_paste": inv.pix_copy_paste,
    }


@tool(args_schema=DebtorRef)
def get_debtor_invoices(tenant_id: UUID, debtor_id: UUID) -> list[dict]:
    """Títulos em aberto do devedor."""
    with tenant_session(tenant_id) as session:
        invoices = session.scalars(
            select(Invoice)
            .where(Invoice.debtor_id == debtor_id, Invoice.status.in_(NEGOTIABLE))
            .order_by(Invoice.due_date)
        ).all()
        return [_invoice_dict(i) for i in invoices if i.amount_open > 0]


@tool(args_schema=PolicyRef)
def get_negotiation_policy(tenant_id: UUID) -> dict:
    """Política de negociação do tenant (entrada mínima, parcelas, desconto)."""
    with tenant_session(tenant_id) as session:
        return session.get(Tenant, tenant_id).negotiation_policy or {}


@tool(args_schema=OptionsInput)
def build_options(total_open: Decimal, policy: dict, today: date) -> list[dict]:
    """Gera as opções válidas de pagamento. Determinístico: o LLM só escolhe entre elas."""
    options = build_payment_options(total_open, NegotiationPolicy.from_json(policy), today)
    return [{**o.to_dict(), "label": o.describe()} for o in options]


@tool(args_schema=PromiseInput)
def register_promise(tenant_id: UUID, debtor_id: UUID, promised_date: date, today: date) -> int:
    """Registra promessa de pagamento e pausa a régua até a data + 1."""
    with tenant_session(tenant_id) as session:
        tenant = session.get(Tenant, tenant_id)
        return len(_register_promise(session, tenant, debtor_id, promised_date, today, "agente"))


@tool(args_schema=AgreementInput)
def create_agreement(
    tenant_id: UUID, debtor_id: UUID, invoice_ids: list[UUID], option_id: str, today: date
) -> dict:
    """Cria o acordo e as parcelas. Recalcula as opções a partir do banco e recusa
    qualquer `option_id` que não esteja entre elas."""
    with tenant_session(tenant_id) as session:
        tenant = session.get(Tenant, tenant_id)
        invoices = session.scalars(
            select(Invoice)
            .where(Invoice.id.in_(invoice_ids), Invoice.debtor_id == debtor_id)
            .where(Invoice.status.in_(NEGOTIABLE))
            .with_for_update()
        ).all()
        if len(invoices) != len(invoice_ids):
            raise ValueError("títulos mudaram desde a proposta")

        total = sum((i.amount_open for i in invoices), Decimal("0"))
        options = build_payment_options(
            total, NegotiationPolicy.from_json(tenant.negotiation_policy), today,
        )
        option = next((o for o in options if o.id == option_id), None)
        if option is None:
            raise ValueError(f"opção fora da política: {option_id}")
        if not tenant.issuer_provider:
            raise ValueError("tenant sem emissor")

        debtor = session.get(Debtor, debtor_id)
        if debtor is None:
            raise ValueError("devedor não encontrado")
        adapter = get_adapter(tenant.issuer_provider, tenant.issuer_config or {})
        issued: list[IssuedCharge] = []
        try:
            for inst in option.installments:
                issued.append(adapter.issue(
                    name=debtor.name,
                    document=debtor.document,
                    phone=debtor.phone,
                    email=debtor.email,
                    amount=inst.amount,
                    due_date=inst.due_date,
                    description=f"Acordo parcela {inst.number}/{len(option.installments)}",
                ))

            agreement = Agreement(
                tenant_id=tenant_id,
                debtor_id=debtor_id,
                source_invoice_ids=[i.id for i in invoices],
                conditions=option.to_dict(),
                accepted_at=datetime.now(UTC),
            )
            session.add(agreement)
            session.flush()

            for inv in invoices:
                if inv.status != InvoiceStatus.EM_NEGOCIACAO:
                    set_invoice_status(inv, InvoiceStatus.EM_NEGOCIACAO)
                set_invoice_status(inv, InvoiceStatus.RENEGOCIADO)

            parent = invoices[0]
            created = []
            for inst, charge in zip(option.installments, issued, strict=True):
                if not charge.pix_copy_paste and not charge.digitable_line:
                    raise ValueError("emissor não devolveu PIX nem boleto")
                new = _installment_invoice(
                    session, tenant_id, debtor_id, parent.id, agreement.id, inst, charge,
                    len(option.installments),
                )
                created.append(new)
            session.flush()

            audit(session, tenant_id=tenant_id, actor="agente", action="cria_acordo",
                  entity="agreement", entity_id=agreement.id,
                  after={"option": option.to_dict(), "source": [str(i.id) for i in invoices]})
        except Exception:
            for charge in issued:
                adapter.cancel(charge.external_id)
            raise

        return {
            "agreement_id": str(agreement.id),
            "option": option.to_dict(),
            "label": option.describe(),
            "invoices": [_invoice_dict(i) for i in created],
        }


@tool(args_schema=HumanRequestInput)
def request_human(
    tenant_id: UUID, conversation_id: UUID, thread_id: str, reason: str, payload: dict
) -> str:
    """Registra pedido de aprovação humana e pausa a conversa."""
    with tenant_session(tenant_id) as session:
        approval = Approval(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            reason=reason,
            payload=payload,
            status=ApprovalStatus.PENDENTE,
        )
        session.add(approval)
        conv = session.get(Conversation, conversation_id)
        conv.state = ConversationState.AGUARDANDO_APROVACAO
        session.flush()
        audit(session, tenant_id=tenant_id, actor="agente", action="pede_aprovacao",
              entity="approval", entity_id=approval.id, after={"reason": reason})
        return str(approval.id)
