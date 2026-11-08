"""Convite de dono, financeiro e atendente. O link vai por e-mail."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_owner
from app.api.routes.auth import TokenOut, issue_access_token
from app.core.audit import audit
from app.core.db import SessionLocal
from app.core.roles import COMPANY_ROLES
from app.models import Tenant, TenantMember
from app.onboarding.members import accept_invite, create_invite, normalize_email

router = APIRouter(prefix="/members", tags=["equipe"])


class MemberOut(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    delivered: bool | None = None


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    role: str

    @field_validator("email")
    @classmethod
    def _mail(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in COMPANY_ROLES:
            raise ValueError("papel inválido")
        return value


class AcceptIn(BaseModel):
    token: str = Field(min_length=8, max_length=400)


def _out(member: TenantMember) -> MemberOut:
    return MemberOut(id=member.id, email=member.email, role=member.role, status=member.status)


@router.get("", response_model=list[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_owner),
) -> list[MemberOut]:
    rows = db.scalars(select(TenantMember).order_by(TenantMember.email)).all()
    return [_out(row) for row in rows]


@router.post("/invites", response_model=MemberOut, status_code=201)
def invite(
    body: InviteIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_owner),
) -> MemberOut:
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(404, "empresa não encontrada")
    try:
        member, delivered = create_invite(db, tenant, body.email, body.role)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.flush()
    audit(
        db, tenant_id=tenant.id, actor=user.actor, action="convida_usuario",
        entity="member", entity_id=member.id, after={"email": member.email, "role": member.role},
    )
    return MemberOut(id=member.id, email=member.email, role=member.role, status=member.status, delivered=delivered)


@router.post("/accept", response_model=TokenOut)
def accept(body: AcceptIn) -> TokenOut:
    with SessionLocal() as session, session.begin():
        member = accept_invite(session, body.token.strip())
        tenant = session.get(Tenant, member.tenant_id)
        if tenant is None:
            raise HTTPException(404, "empresa não encontrada")
        audit(
            session, tenant_id=tenant.id, actor=f"humano:{member.email}",
            action="aceita_convite", entity="member", entity_id=member.id,
            after={"role": member.role},
        )
        return issue_access_token(email=member.email, tenant=tenant, role=member.role)
