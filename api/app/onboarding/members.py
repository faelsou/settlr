"""Convite de quem entra na conta. O e-mail leva um link e não leva senha."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.email import send_email
from app.core.config import get_settings
from app.core.db import set_tenant
from app.core.logging import get_logger
from app.core.roles import COMPANY_ROLES
from app.models import Tenant, TenantMember

log = get_logger(__name__)

ACTIVE = "ativo"
INVITED = "convidado"
INVITE_TTL = timedelta(days=7)


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    domain = value.split("@")[-1] if "@" in value else ""
    if "@" not in value or "." not in domain:
        raise ValueError("e-mail inválido")
    return value


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(tenant_id: UUID) -> str:
    return f"{tenant_id}~{secrets.token_urlsafe(32)}"


def parse_token(token: str) -> UUID:
    tenant, _, secret = token.partition("~")
    if not secret:
        raise ValueError("convite inválido")
    return UUID(tenant)


def active_member(session: Session, email: str) -> TenantMember | None:
    email = email.strip().lower()
    return session.scalars(
        select(TenantMember).where(TenantMember.email == email, TenantMember.status == ACTIVE)
    ).first()


def ensure_active_member(session: Session, tenant_id: UUID, email: str, role: str) -> TenantMember:
    """Garante o dono do seed e de quem acaba de criar a conta. Não rebaixa quem já entrou."""
    email = email.strip().lower()
    found = session.scalars(select(TenantMember).where(TenantMember.email == email)).first()
    if found is not None:
        return found
    member = TenantMember(
        tenant_id=tenant_id,
        email=email,
        role=role,
        status=ACTIVE,
        accepted_at=datetime.now(UTC),
    )
    session.add(member)
    return member


def invite_copy(company: str, role: str, link: str) -> tuple[str, str]:
    subject = f"Convite para {company} no Settlr"
    body = (
        f"{company} convidou você para o Settlr como {role}.\n\n"
        "Abra o link abaixo. Ele é só seu. Não há credencial para repassar: "
        "cada pessoa entra pelo próprio convite.\n\n"
        f"{link}\n"
    )
    return subject, body


def deliver_invite(to: str, subject: str, body: str) -> bool:
    """True quando o SMTP aceitou. Fora de produção, sem SMTP, o convite fica registrado."""
    try:
        send_email(to, subject, body)
    except RuntimeError as exc:
        if get_settings().env == "prod":
            raise HTTPException(503, "não foi possível enviar o convite") from exc
        log.warning("convite.sem_smtp", to=to, motivo=str(exc))
        return False
    return True


def create_invite(session: Session, tenant: Tenant, email: str, role: str) -> tuple[TenantMember, bool]:
    if role not in COMPANY_ROLES:
        raise ValueError("papel inválido")
    email = email.strip().lower()
    member = session.scalars(select(TenantMember).where(TenantMember.email == email)).first()
    if member is not None and member.status == ACTIVE:
        raise ValueError("essa pessoa já entra nesta conta")
    token = new_token(tenant.id)
    expires = datetime.now(UTC) + INVITE_TTL
    if member is None:
        member = TenantMember(
            tenant_id=tenant.id,
            email=email,
            role=role,
            status=INVITED,
            invite_token_hash=_hash(token),
            invite_expires_at=expires,
        )
        session.add(member)
    else:
        member.role = role
        member.status = INVITED
        member.invite_token_hash = _hash(token)
        member.invite_expires_at = expires
        member.accepted_at = None
    link = f"{get_settings().panel_base_url.rstrip('/')}/convite/{token}"
    subject, body = invite_copy(tenant.name, role, link)
    delivered = deliver_invite(email, subject, body)
    return member, delivered


def accept_invite(session: Session, token: str) -> TenantMember:
    try:
        tenant_id = parse_token(token)
    except ValueError as exc:
        raise HTTPException(404, "convite não encontrado") from exc
    set_tenant(session, tenant_id)
    member = session.scalars(
        select(TenantMember).where(TenantMember.invite_token_hash == _hash(token))
    ).first()
    if member is None or member.tenant_id != tenant_id:
        raise HTTPException(404, "convite não encontrado")
    if member.invite_expires_at is not None and member.invite_expires_at < datetime.now(UTC):
        raise HTTPException(410, "convite expirado")
    member.status = ACTIVE
    member.accepted_at = datetime.now(UTC)
    member.invite_token_hash = None
    member.invite_expires_at = None
    return member
