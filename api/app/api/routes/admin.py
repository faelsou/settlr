"""Onboarding de tenant pela agência (FLUXOS.md §3). Configuração, não projeto."""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.policy import DEFAULT_NEGOTIATION_POLICY
from app.api.deps import CurrentUser, require_agency
from app.channels.whatsapp import EvolutionClient
from app.core.audit import audit
from app.core.config import get_settings
from app.core.db import SessionLocal, set_tenant
from app.core.senders import fold_primary, listed_senders
from app.dunning.legal import MISSING_OPINION, production_without_opinion
from app.dunning.official import commit_activation, read_evolution
from app.dunning.rules import DEFAULT_ALLOWED_HOURS, DEFAULT_DUNNING_RULES
from app.models import Tenant

router = APIRouter(prefix="/admin/tenants", tags=["agencia"])


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")
    whatsapp_instance: str | None = None
    whatsapp_number: str | None = None
    issuer_provider: str | None = None
    issuer_config: dict = {}
    legal_basis: str | None = None


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    active: bool
    whatsapp_instance: str | None
    issuer_provider: str | None
    issuer_webhook_token: str | None
    missing: list[str]


def missing_requirements(tenant: Tenant) -> list[str]:
    """Nenhum tenant entra em produção sem política, régua, horário, número, base legal e parecer."""
    checks = {
        "política de negociação": tenant.negotiation_policy,
        "régua": tenant.dunning_rules,
        "horário permitido": tenant.allowed_hours,
        "instância do WhatsApp": tenant.whatsapp_instance,
        "base legal (LGPD)": tenant.legal_basis,
    }
    missing = [name for name, value in checks.items() if not value]
    settings = get_settings()
    if production_without_opinion(settings.env, settings.legal_opinion_ref):
        missing.append(MISSING_OPINION)
    return missing


def _ensure_unique_instances(session, tenant: Tenant) -> None:
    names = [item["instance"] for item in listed_senders(tenant)]
    others = session.scalars(select(Tenant).where(Tenant.id != tenant.id)).all()
    taken = {item["instance"] for other in others for item in listed_senders(other)}
    for name in names:
        if name in taken:
            raise HTTPException(422, f"instância já usada por outra empresa: {name}")


def activate_record(tenant: Tenant) -> list[str]:
    """O que ainda impede ligar a conta. Vazio quando a ativação gravou o tenant."""
    if missing := missing_requirements(tenant):
        return missing
    state, catalog = read_evolution(EvolutionClient(), tenant.whatsapp_instance or "")
    return commit_activation(tenant, state, catalog)


def _out(t: Tenant) -> TenantOut:
    return TenantOut(
        id=t.id, name=t.name, slug=t.slug, active=t.active, whatsapp_instance=t.whatsapp_instance,
        issuer_provider=t.issuer_provider, issuer_webhook_token=t.issuer_webhook_token,
        missing=missing_requirements(t),
    )


@router.get("", response_model=list[TenantOut])
def list_tenants(_: CurrentUser = Depends(require_agency)) -> list[TenantOut]:
    with SessionLocal() as session:
        return [_out(t) for t in session.scalars(select(Tenant).order_by(Tenant.name))]


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantCreate, user: CurrentUser = Depends(require_agency)) -> TenantOut:
    with SessionLocal() as session, session.begin():
        tenant = Tenant(
            **body.model_dump(),
            active=False,
            negotiation_policy=DEFAULT_NEGOTIATION_POLICY,
            dunning_rules=DEFAULT_DUNNING_RULES,
            allowed_hours=DEFAULT_ALLOWED_HOURS,
            reconciliation_rules={},
            issuer_webhook_token=secrets.token_urlsafe(32) if body.issuer_provider else None,
        )
        fold_primary(tenant)
        _ensure_unique_instances(session, tenant)
        session.add(tenant)
        session.flush()
        set_tenant(session, tenant.id)
        audit(session, tenant_id=tenant.id, actor=user.actor, action="cria_tenant",
              entity="tenant", entity_id=tenant.id, after=body.model_dump(exclude={"issuer_config"}))
        return _out(tenant)


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    whatsapp_instance: str | None = None
    whatsapp_number: str | None = None
    issuer_provider: str | None = None
    issuer_config: dict | None = None
    legal_basis: str | None = None


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: UUID, body: TenantUpdate, user: CurrentUser = Depends(require_agency)
) -> TenantOut:
    with SessionLocal() as session, session.begin():
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(404, "tenant não encontrado")
        changes = body.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(tenant, key, value)
        if "whatsapp_instance" in changes or "whatsapp_number" in changes:
            fold_primary(tenant)
            _ensure_unique_instances(session, tenant)
        if tenant.issuer_provider and not tenant.issuer_webhook_token:
            tenant.issuer_webhook_token = secrets.token_urlsafe(32)
        set_tenant(session, tenant.id)
        audit(session, tenant_id=tenant.id, actor=user.actor, action="atualiza_tenant",
              entity="tenant", entity_id=tenant.id,
              after={k: v for k, v in changes.items() if k != "issuer_config"})
        return _out(tenant)


@router.post("/{tenant_id}/activate", response_model=TenantOut)
def activate_tenant(tenant_id: UUID, user: CurrentUser = Depends(require_agency)) -> TenantOut:
    with SessionLocal() as session, session.begin():
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(404, "tenant não encontrado")
        if missing := activate_record(tenant):
            raise HTTPException(422, {"missing": missing})
        set_tenant(session, tenant.id)
        audit(session, tenant_id=tenant.id, actor=user.actor, action="ativa_tenant",
              entity="tenant", entity_id=tenant.id)
        return _out(tenant)
