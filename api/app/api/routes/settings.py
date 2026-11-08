"""Configurações do tenant (fase 4): política, régua, horários, templates e conciliação."""

from datetime import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.policy import DEFAULT_NEGOTIATION_POLICY
from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.core.audit import audit
from app.core.phones import normalize_br_phone
from app.core.senders import apply_senders, listed_senders, normalize_senders
from app.dunning.official import preserve_approved
from app.dunning.rules import DEFAULT_ALLOWED_HOURS, DEFAULT_DUNNING_RULES
from app.models import Tenant
from app.reconciliation.matcher import ReconciliationRules

_RECON_DEFAULTS = ReconciliationRules()
DEFAULT_RECONCILIATION_RULES = {
    "days_before_due": _RECON_DEFAULTS.days_before_due,
    "days_after_due": _RECON_DEFAULTS.days_after_due,
    "name_similarity_min": _RECON_DEFAULTS.name_similarity_min,
    "max_invoices_in_sum": _RECON_DEFAULTS.max_invoices_in_sum,
    "allow_partial": _RECON_DEFAULTS.allow_partial,
    "max_overpay_pct": str(_RECON_DEFAULTS.max_overpay_pct),
    "max_underpay_pct": str(_RECON_DEFAULTS.max_underpay_pct),
}

router = APIRouter(prefix="/settings", tags=["configuracoes"])


class NegotiationPolicyIn(BaseModel):
    max_discount_pct_cash: Decimal = Field(ge=0, le=100)
    min_down_payment_pct: Decimal = Field(ge=0, le=100)
    max_installments: int = Field(ge=1, le=48)
    min_installment_amount: Decimal = Field(ge=0)
    installment_interval_days: int = Field(ge=7, le=90)
    monthly_interest_pct: Decimal = Field(ge=0, le=20)
    first_due_in_days: int = Field(ge=0, le=30)
    max_promise_days: int = Field(ge=1, le=60)


class StepIn(BaseModel):
    key: str = Field(max_length=16)
    offset: int = Field(ge=-30, le=120)
    channels: list[str] = []
    template: str | None = None
    handoff: bool = False

    @field_validator("channels")
    @classmethod
    def _channels(cls, v: list[str]) -> list[str]:
        unknown = set(v) - {"whatsapp", "email"}
        if unknown:
            raise ValueError(f"canais desconhecidos: {sorted(unknown)}")
        return v


class WhatsappTemplateIn(BaseModel):
    name: str
    language: str = "pt_BR"
    params: list[str] = []


class DunningRulesIn(BaseModel):
    steps: list[StepIn]
    templates: dict[str, str] = {}
    whatsapp_templates: dict[str, WhatsappTemplateIn] = {}
    rate_per_minute: int = Field(20, ge=1, le=120)
    text_version: str = ""

    @model_validator(mode="after")
    def _check(self) -> "DunningRulesIn":
        keys = [s.key for s in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("etapas com chave repetida")
        known = set(DEFAULT_DUNNING_RULES["templates"]) | set(self.templates)
        for step in self.steps:
            if not step.handoff and step.template not in known:
                raise ValueError(f"etapa {step.key} usa template inexistente: {step.template}")
        return self


class AllowedHoursIn(BaseModel):
    start: time
    end: time
    weekdays: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "AllowedHoursIn":
        if self.start >= self.end:
            raise ValueError("início precisa ser antes do fim")
        if not set(self.weekdays) <= set(range(7)):
            raise ValueError("dias da semana vão de 0 (segunda) a 6 (domingo)")
        return self


class ReconciliationRulesIn(BaseModel):
    days_before_due: int = Field(10, ge=0, le=90)
    days_after_due: int = Field(60, ge=0, le=365)
    name_similarity_min: float = Field(0.82, ge=0.5, le=1)
    max_invoices_in_sum: int = Field(4, ge=1, le=8)
    allow_partial: bool = True
    max_overpay_pct: Decimal = Field(Decimal("2"), ge=0, le=50)
    max_underpay_pct: Decimal = Field(Decimal("0"), ge=0, le=20)


class WhatsappSenderOut(BaseModel):
    instance: str
    number: str = ""


class WhatsappSendersIn(BaseModel):
    senders: list[dict] = Field(default_factory=list)

    @field_validator("senders")
    @classmethod
    def _senders(cls, value: list[dict]) -> list[dict]:
        try:
            return normalize_senders(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class TenantSettings(BaseModel):
    timezone: str
    negotiation_policy: NegotiationPolicyIn
    dunning_rules: DunningRulesIn
    allowed_hours: AllowedHoursIn
    reconciliation_rules: ReconciliationRulesIn
    whatsapp_senders: list[WhatsappSenderOut] = []
    owner_email: str = ""
    owner_phone: str = ""

    @field_validator("owner_email")
    @classmethod
    def _owner_email(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        domain = value.split("@")[-1] if "@" in value else ""
        if "@" not in value or "." not in domain:
            raise ValueError("e-mail do dono inválido")
        return value

    @field_validator("owner_phone")
    @classmethod
    def _owner_phone(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        try:
            return normalize_br_phone(value) or ""
        except ValueError as exc:
            raise ValueError("WhatsApp interno inválido") from exc


def current_settings(tenant: Tenant) -> TenantSettings:
    return TenantSettings(
        timezone=tenant.timezone,
        negotiation_policy={**DEFAULT_NEGOTIATION_POLICY, **(tenant.negotiation_policy or {})},
        dunning_rules=tenant.dunning_rules or DEFAULT_DUNNING_RULES,
        allowed_hours=tenant.allowed_hours or DEFAULT_ALLOWED_HOURS,
        reconciliation_rules={**DEFAULT_RECONCILIATION_RULES, **(tenant.reconciliation_rules or {})},
        whatsapp_senders=listed_senders(tenant),
        owner_email=tenant.owner_email or "",
        owner_phone=tenant.owner_phone or "",
    )


@router.get("", response_model=TenantSettings)
def get_settings_(
    db: Session = Depends(get_db), user: CurrentUser = Depends(require_tenant_user)
) -> TenantSettings:
    return current_settings(db.get(Tenant, user.tenant_id))


@router.put("", response_model=TenantSettings)
def update_settings(
    body: TenantSettings,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> TenantSettings:
    tenant = db.get(Tenant, user.tenant_id)
    before = current_settings(tenant).model_dump(mode="json")
    data = body.model_dump(mode="json")
    data["dunning_rules"] = preserve_approved(tenant.dunning_rules, data["dunning_rules"])
    tenant.timezone = data["timezone"]
    tenant.negotiation_policy = data["negotiation_policy"]
    tenant.dunning_rules = data["dunning_rules"]
    tenant.allowed_hours = data["allowed_hours"]
    tenant.reconciliation_rules = data["reconciliation_rules"]
    tenant.owner_email = data["owner_email"] or None
    tenant.owner_phone = data["owner_phone"] or None
    audit(db, tenant_id=tenant.id, actor=user.actor, action="atualiza_configuracoes",
          entity="tenant", entity_id=tenant.id, before=before, after=data)
    return current_settings(tenant)


def _instances_taken(db: Session, tenant_id, instances: list[str]) -> str | None:
    if not instances:
        return None
    others = db.scalars(select(Tenant).where(Tenant.id != tenant_id)).all()
    taken = {item["instance"] for other in others for item in listed_senders(other)}
    for name in instances:
        if name in taken:
            return name
    return None


@router.put("/whatsapp", response_model=list[WhatsappSenderOut])
def update_whatsapp_senders(
    body: WhatsappSendersIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> list[dict]:
    """Substitui os números de disparo. O primeiro envia. Apagar um que caiu
    promove o seguinte. No máximo cinco."""
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(404, "empresa não encontrada")
    clash = _instances_taken(db, tenant.id, [item["instance"] for item in body.senders])
    if clash:
        raise HTTPException(422, f"instância já usada por outra empresa: {clash}")
    before = listed_senders(tenant)
    apply_senders(tenant, body.senders)
    audit(
        db, tenant_id=tenant.id, actor=user.actor, action="atualiza_whatsapp_disparo",
        entity="tenant", entity_id=tenant.id,
        before={"senders": before}, after={"senders": body.senders},
    )
    return body.senders
