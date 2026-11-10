from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.channels.delivery import file_state


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Me(BaseModel):
    id: str
    email: str
    tenant_id: UUID | None
    role: str
    tenant_name: str | None = None


class Page[T](BaseModel):
    items: list[T]
    total: int


class DebtorOut(ORM):
    id: UUID
    name: str
    document: str
    phone: str | None
    phones: list[str] = []
    email: str | None
    opt_out: bool

    @model_validator(mode="after")
    def _phones(self) -> "DebtorOut":
        ordered: list[str] = []
        for number in [*(self.phones or []), self.phone]:
            if number and number not in ordered:
                ordered.append(number)
        self.phones = ordered
        self.phone = ordered[0] if ordered else None
        return self


class InvoiceOut(ORM):
    id: UUID
    external_id: str
    description: str | None
    amount: Decimal
    amount_paid: Decimal
    due_date: date
    status: str
    txid: str | None
    parent_id: UUID | None
    agreement_id: UUID | None
    has_payment_code: bool
    debtor: DebtorOut


class DunningEventOut(ORM):
    step: str
    channel: str
    sent_at: datetime
    delivery_status: str


class MessageOut(ORM):
    id: UUID
    direction: str
    author: str
    body: str | None
    invoice_id: UUID | None
    created_at: datetime
    delivery_status: str | None = None
    file_status: str | None = None


def message_out(message) -> MessageOut:
    """Status de entrega e do arquivo saem da linha. A chave do storage fica no banco."""
    return MessageOut(
        id=message.id,
        direction=message.direction,
        author=message.author,
        body=message.body,
        invoice_id=message.invoice_id,
        created_at=message.created_at,
        delivery_status=message.delivery_status,
        file_status=file_state(message.body, message.media_key),
    )


class DeliveryOut(BaseModel):
    id: UUID
    conversation_id: UUID
    invoice_id: UUID | None
    debtor_name: str
    direction: str
    body: str | None
    delivery_status: str | None
    file_status: str | None
    created_at: datetime


class PromiseOut(ORM):
    promised_date: date
    fulfilled: bool | None
    created_at: datetime


class MatchOut(ORM):
    payment_id: UUID
    invoice_id: UUID
    amount_applied: Decimal
    method: str
    score: float
    provisional: bool
    confirmed_by: str


class InstallmentOut(ORM):
    id: UUID
    external_id: str
    description: str | None
    amount: Decimal
    due_date: date
    status: str


class InvoiceDetail(InvoiceOut):
    dunning_events: list[DunningEventOut]
    messages: list[MessageOut]
    promises: list[PromiseOut]
    matches: list[MatchOut]
    installments: list[InstallmentOut] = []


class PaymentOut(ORM):
    id: UUID
    origin: str
    status: str
    amount: Decimal
    paid_at: datetime
    e2e_id: str | None
    payer_doc: str | None
    payer_name: str | None
    payer_bank: str | None
    has_receipt: bool
    bank_confirmed: bool
    extraction_confidence: float | None
    matches: list[MatchOut]
    created_at: datetime


class ExceptionOut(ORM):
    id: UUID
    type: str
    status: str
    payment: PaymentOut | None
    invoice_id: UUID | None
    conversation_id: UUID | None
    details: dict[str, Any]
    assignee: str | None
    resolution: str | None
    created_at: datetime
    resolved_at: datetime | None


class AllocationIn(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0)


class ManualReceiptIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_at: datetime
    e2e_id: str | None = None
    payer_doc: str | None = None
    payer_name: str | None = None


class ConfirmExceptionIn(BaseModel):
    allocations: list[AllocationIn] = []
    receipt: ManualReceiptIn | None = None
    contestation: Literal["cobranca", "devedor"] | None = None
    note: str | None = None


class RejectExceptionIn(BaseModel):
    discard_payment: bool = False
    note: str | None = None


class ConversationOut(ORM):
    id: UUID
    debtor: DebtorOut
    intent: str | None
    state: str
    summary: str | None
    identity_verified: bool
    assigned_to: str | None
    updated_at: datetime


class SendMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ApprovalOut(ORM):
    id: UUID
    conversation_id: UUID
    debtor: DebtorOut
    reason: str
    payload: dict[str, Any]
    status: str
    decided_by: str | None
    created_at: datetime


class DecideApprovalIn(BaseModel):
    approved: bool
    message: str = Field(min_length=1, max_length=2000)


class ImportResultOut(BaseModel):
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    errors: list[str] = []


class Metrics(BaseModel):
    period_start: date
    period_end: date
    recovery_rate: float | None
    overdue_amount: Decimal
    recovered_amount: Decimal
    avg_days_late: float | None
    baseline_avg_days_late: float | None
    promises_made: int
    promises_kept: int
    promise_kept_rate: float | None
    payments_reconciled: int
    auto_reconciled: int
    auto_reconciliation_rate: float | None
    exceptions_open: int
    avg_exception_resolution_hours: float | None
