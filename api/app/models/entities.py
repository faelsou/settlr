import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, Json, Money, TenantMixin, TimestampMixin
from app.models.enums import (
    ApprovalStatus,
    ConversationState,
    ExceptionStatus,
    InvoiceStatus,
    PaymentStatus,
)


class Tenant(IdMixin, TimestampMixin, Base):
    """Cliente da agência. Política, régua e horário são configuração, não código."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    negotiation_policy: Mapped[Json]
    dunning_rules: Mapped[Json]
    reconciliation_rules: Mapped[Json]
    allowed_hours: Mapped[Json]
    whatsapp_instance: Mapped[str | None] = mapped_column(String(120), unique=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    whatsapp_senders: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    issuer_provider: Mapped[str | None] = mapped_column(String(40))
    issuer_webhook_token: Mapped[str | None] = mapped_column(String(200), unique=True)
    issuer_config: Mapped[Json]
    legal_basis: Mapped[str | None] = mapped_column(Text)
    owner_email: Mapped[str | None] = mapped_column(String(200))
    owner_phone: Mapped[str | None] = mapped_column(String(20))


class Debtor(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "debtors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document"),
        Index("ix_debtors_tenant_phone", "tenant_id", "phone"),
        Index("ix_debtors_phones", "phones", postgresql_using="gin"),
    )

    name: Mapped[str] = mapped_column(String(200))
    document: Mapped[str] = mapped_column(String(14))
    phone: Mapped[str | None] = mapped_column(String(20))
    phones: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")
    email: Mapped[str | None] = mapped_column(String(200))
    opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="debtor")


class Invoice(IdMixin, TenantMixin, TimestampMixin, Base):
    """Título. É o centro do modelo: régua, conversas e pagamentos apontam para ele."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id"),
        Index("ix_invoices_tenant_status_due", "tenant_id", "status", "due_date"),
        Index("ix_invoices_tenant_txid", "tenant_id", "txid"),
    )

    debtor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debtors.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(300))
    amount: Mapped[Money]
    amount_paid: Mapped[Money] = mapped_column(default=Decimal("0"))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default=InvoiceStatus.ABERTO)
    txid: Mapped[str | None] = mapped_column(String(64))
    digitable_line: Mapped[str | None] = mapped_column(String(64))
    pix_copy_paste: Mapped[str | None] = mapped_column(Text)
    payment_url: Mapped[str | None] = mapped_column(String(500))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agreements.id"))

    debtor: Mapped[Debtor] = relationship(back_populates="invoices")

    @property
    def amount_open(self) -> Decimal:
        return self.amount - self.amount_paid

    @property
    def has_payment_code(self) -> bool:
        from app.dunning.payment import has_payment_code

        return has_payment_code(self.pix_copy_paste, self.digitable_line)


class DunningEvent(IdMixin, TenantMixin, Base):
    """Cada disparo da régua. A unicidade vale enquanto a entrega não falhou."""

    __tablename__ = "dunning_events"
    __table_args__ = (
        Index(
            "uq_dunning_events_step_aberto",
            "invoice_id",
            "step",
            "channel",
            unique=True,
            postgresql_where=text("delivery_status <> 'falhou'"),
        ),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    step: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    delivery_status: Mapped[str] = mapped_column(String(24), default="aceito")


class Conversation(IdMixin, TenantMixin, TimestampMixin, Base):
    """Estado do agente por devedor."""

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("tenant_id", "debtor_id"),)

    debtor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debtors.id"))
    wa_jid: Mapped[str] = mapped_column(String(64))
    intent: Mapped[str | None] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default=ConversationState.AGENTE)
    summary: Mapped[str | None] = mapped_column(Text)
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    identity_attempts: Mapped[int] = mapped_column(Integer, default=0)
    assigned_to: Mapped[str | None] = mapped_column(String(200))


class Message(IdMixin, TenantMixin, Base):
    """Toda mensagem de entrada e saída, ligada ao título quando houver."""

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    direction: Mapped[str] = mapped_column(String(4))
    author: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    media_key: Mapped[str | None] = mapped_column(String(300))
    wa_message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    delivery_status: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Promise(IdMixin, TenantMixin, Base):
    __tablename__ = "promises"

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    promised_date: Mapped[date] = mapped_column(Date)
    fulfilled: Mapped[bool | None] = mapped_column(Boolean)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Agreement(IdMixin, TenantMixin, Base):
    """Acordo de parcelamento. As parcelas são `invoices` com `agreement_id`."""

    __tablename__ = "agreements"

    debtor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debtors.id"))
    source_invoice_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    conditions: Mapped[Json]
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(IdMixin, TenantMixin, TimestampMixin, Base):
    """Pedido pausado pelo agente (`interrupt` do LangGraph) aguardando humano."""

    __tablename__ = "approvals"

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[Json]
    status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.PENDENTE)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(IdMixin, TenantMixin, TimestampMixin, Base):
    """Todo dinheiro que entra, venha de comprovante, extrato ou webhook."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "e2e_id", name="uq_payments_tenant_e2e"),
        UniqueConstraint("tenant_id", "file_hash", name="uq_payments_tenant_file_hash"),
        Index("ix_payments_tenant_status", "tenant_id", "status"),
    )

    origin: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default=PaymentStatus.RECEBIDO_BANCO)
    amount: Mapped[Money]
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    e2e_id: Mapped[str | None] = mapped_column(String(64))
    txid: Mapped[str | None] = mapped_column(String(64))
    payer_doc: Mapped[str | None] = mapped_column(String(20))
    payer_name: Mapped[str | None] = mapped_column(String(200))
    payer_bank: Mapped[str | None] = mapped_column(String(120))
    debtor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("debtors.id"))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    file_key: Mapped[str | None] = mapped_column(String(300))
    content_type: Mapped[str | None] = mapped_column(String(80))
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    bank_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[Json]


class Match(IdMixin, TenantMixin, Base):
    """Ligação N:N pagamento↔título. `provisional` = comprovante ainda sem banco."""

    __tablename__ = "matches"

    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_applied: Mapped[Money]
    method: Mapped[str] = mapped_column(String(24))
    score: Mapped[float] = mapped_column(Float, default=1.0)
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[str] = mapped_column(String(200), default="sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewException(IdMixin, TenantMixin, TimestampMixin, Base):
    """Fila de revisão humana."""

    __tablename__ = "exceptions"
    __table_args__ = (Index("ix_exceptions_tenant_status", "tenant_id", "status"),)

    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=ExceptionStatus.ABERTA)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    details: Mapped[Json]
    assignee: Mapped[str | None] = mapped_column(String(200))
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(IdMixin, Base):
    """Rastro para disputa e LGPD: quem, o quê, quando, antes/depois."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_tenant_entity", "tenant_id", "entity", "entity_id"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[Json]
    after: Mapped[Json]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
