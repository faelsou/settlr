from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, set_tenant
from app.core.roles import can_configure


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    tenant_id: UUID | None
    role: str

    @property
    def actor(self) -> str:
        return f"humano:{self.email}"


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    """Valida o JWT do Supabase Auth. O tenant vem de `app_metadata.tenant_id`,
    que só o backend/agência consegue gravar."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token ausente")
    settings = get_settings()
    try:
        claims = jwt.decode(
            authorization[7:],
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido") from exc

    meta = claims.get("app_metadata") or {}
    tenant = meta.get("tenant_id")
    return CurrentUser(
        id=claims["sub"],
        email=claims.get("email", claims["sub"]),
        tenant_id=UUID(tenant) if tenant else None,
        role=meta.get("role", "operador"),
    )


def require_tenant_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "usuário sem tenant")
    return user


def require_agency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "agencia":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas a agência")
    return user


def require_owner(user: CurrentUser = Depends(require_tenant_user)) -> CurrentUser:
    if not can_configure(user.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "só o dono configura a política")
    return user


def get_db(user: CurrentUser = Depends(require_tenant_user)) -> Iterator[Session]:
    """Sessão transacional já escopada ao tenant do usuário (RLS)."""
    with SessionLocal() as session, session.begin():
        set_tenant(session, user.tenant_id)
        yield session
