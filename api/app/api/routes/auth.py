"""Login do painel. Em produção o JWT vem do Supabase Auth; em dev a API emite o token."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal, set_tenant
from app.models import Tenant
from app.onboarding.members import active_member

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginIn(BaseModel):
    email: str = Field(default="operador@demo.local", min_length=3, max_length=200)
    tenant_slug: str = Field(default="demo", min_length=2, max_length=80)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: UUID
    tenant_name: str
    email: str
    role: str


def issue_access_token(*, email: str, tenant: Tenant, role: str) -> TokenOut:
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": email,
            "email": email,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=12)).timestamp()),
            "app_metadata": {"tenant_id": str(tenant.id), "role": role},
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    encoded = token if isinstance(token, str) else token.decode()
    return TokenOut(
        access_token=encoded,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        email=email,
        role=role,
    )


@router.post("/dev-login", response_model=TokenOut)
def dev_login(body: DevLoginIn) -> TokenOut:
    """Só existe fora de produção. O papel vem de quem já aceitou o convite,
    não do corpo do pedido."""
    settings = get_settings()
    if settings.env == "prod":
        raise HTTPException(404, "indisponível")

    with SessionLocal() as session, session.begin():
        tenant = session.scalars(select(Tenant).where(Tenant.slug == body.tenant_slug)).first()
        if tenant is None:
            raise HTTPException(404, "tenant não encontrado — rode python -m app.cli seed-demo")
        set_tenant(session, tenant.id)
        member = active_member(session, body.email)
        if member is None or member.tenant_id != tenant.id:
            raise HTTPException(403, "aceite o convite para entrar")
        return issue_access_token(email=member.email, tenant=tenant, role=member.role)
