"""A empresa cria a conta pela tela: política, régua, horário, WhatsApp e base legal."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.agent.policy import DEFAULT_NEGOTIATION_POLICY
from app.api.routes.admin import _ensure_unique_instances, missing_requirements
from app.api.routes.auth import TokenOut, issue_access_token
from app.api.routes.settings import AllowedHoursIn, DunningRulesIn, NegotiationPolicyIn
from app.core.audit import audit
from app.core.db import SessionLocal, set_tenant
from app.core.phones import normalize_br_phone
from app.core.senders import fold_primary
from app.dunning.rules import DEFAULT_ALLOWED_HOURS, DEFAULT_DUNNING_RULES
from app.models import Tenant
from app.onboarding.members import ensure_active_member, normalize_email

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingDefaults(BaseModel):
    negotiation_policy: NegotiationPolicyIn
    dunning_rules: DunningRulesIn
    allowed_hours: AllowedHoursIn
    timezone: str = "America/Sao_Paulo"


class OnboardingIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")
    owner_email: str
    whatsapp_instance: str | None = None
    whatsapp_number: str | None = None
    legal_basis: str | None = None
    negotiation_policy: NegotiationPolicyIn
    dunning_rules: DunningRulesIn
    allowed_hours: AllowedHoursIn
    timezone: str = "America/Sao_Paulo"

    @field_validator("owner_email")
    @classmethod
    def _owner(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("legal_basis")
    @classmethod
    def _legal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("whatsapp_instance", "whatsapp_number")
    @classmethod
    def _blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class OnboardingOut(TokenOut):
    active: bool
    missing: list[str]


@router.get("/defaults", response_model=OnboardingDefaults)
def defaults() -> OnboardingDefaults:
    return OnboardingDefaults(
        negotiation_policy=DEFAULT_NEGOTIATION_POLICY,
        dunning_rules=DEFAULT_DUNNING_RULES,
        allowed_hours=DEFAULT_ALLOWED_HOURS,
    )


@router.post("", response_model=OnboardingOut, status_code=201)
def create_company(body: OnboardingIn) -> OnboardingOut:
    number = None
    if body.whatsapp_instance or body.whatsapp_number:
        if not body.whatsapp_instance or not body.whatsapp_number:
            raise HTTPException(422, "preencha a instância e o número do WhatsApp")
        try:
            number = normalize_br_phone(body.whatsapp_number)
        except ValueError as exc:
            raise HTTPException(422, "número de WhatsApp inválido") from exc

    with SessionLocal() as session, session.begin():
        taken = session.scalars(select(Tenant).where(Tenant.slug == body.slug)).first()
        if taken is not None:
            raise HTTPException(409, "apelido já usado")
        tenant = Tenant(
            name=body.name.strip(),
            slug=body.slug,
            active=False,
            timezone=body.timezone,
            negotiation_policy=body.negotiation_policy.model_dump(mode="json"),
            dunning_rules=body.dunning_rules.model_dump(mode="json"),
            allowed_hours=body.allowed_hours.model_dump(mode="json"),
            reconciliation_rules={},
            whatsapp_instance=body.whatsapp_instance,
            whatsapp_number=number,
            issuer_config={},
            bank_feed={},
            legal_basis=body.legal_basis,
            owner_email=body.owner_email,
        )
        fold_primary(tenant)
        _ensure_unique_instances(session, tenant)
        session.add(tenant)
        session.flush()
        set_tenant(session, tenant.id)
        ensure_active_member(session, tenant.id, body.owner_email, "dono")
        audit(
            session, tenant_id=tenant.id, actor=f"humano:{body.owner_email}",
            action="cria_tenant", entity="tenant", entity_id=tenant.id,
            after={"slug": body.slug, "name": tenant.name},
        )
        token = issue_access_token(email=body.owner_email, tenant=tenant, role="dono")
        return OnboardingOut(
            **token.model_dump(),
            active=tenant.active,
            missing=missing_requirements(tenant),
        )
