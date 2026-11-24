"""SETL-68: token sem papel válido é recusado. SETL-69: só o dono configura a política."""

from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db, require_owner
from app.core.config import get_settings
from app.core.roles import CONFIGURE_ROLES, can_configure, can_settle
from app.services.cadastro import app

TENANT = uuid4()


def _bearer(meta: dict) -> str:
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "user-1",
            "email": "pessoa@empresa.test",
            "aud": settings.jwt_audience,
            "app_metadata": meta,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return f"Bearer {token}"


@pytest.fixture
def client():
    def _sem_banco():
        yield None

    app.dependency_overrides[get_db] = _sem_banco
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "meta",
    [
        {"tenant_id": str(TENANT)},
        {"tenant_id": str(TENANT), "role": None},
        {"tenant_id": str(TENANT), "role": ""},
        {"tenant_id": str(TENANT), "role": "superadmin"},
        {},
    ],
    ids=["sem-role", "role-nulo", "role-vazio", "role-desconhecido", "sem-app-metadata"],
)
def test_token_sem_papel_valido_recebe_403(meta):
    with pytest.raises(HTTPException) as erro:
        get_current_user(_bearer(meta))
    assert erro.value.status_code == 403


@pytest.mark.parametrize("role", ["dono", "financeiro", "atendente", "operador", "agencia"])
def test_papel_conhecido_passa(role):
    user = get_current_user(_bearer({"tenant_id": str(TENANT), "role": role}))
    assert user.role == role


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/settings"), ("put", "/settings"), ("put", "/settings/whatsapp")],
)
def test_rota_autenticada_recusa_token_sem_papel(client, method, path):
    response = client.request(
        method, path, headers={"Authorization": _bearer({"tenant_id": str(TENANT)})}, json={}
    )
    assert response.status_code == 403


def test_so_o_dono_configura():
    assert {"dono"} == CONFIGURE_ROLES
    assert can_configure("dono")
    for role in ("operador", "financeiro", "atendente", "agencia"):
        assert not can_configure(role)
    # A baixa não muda: operador continua confirmando pagamento.
    assert can_settle("operador")


@pytest.mark.parametrize("role", ["operador", "financeiro", "atendente"])
@pytest.mark.parametrize(
    "path", ["/settings", "/settings/whatsapp", "/settings/activate"]
)
def test_quem_nao_e_dono_recebe_403_ao_configurar(client, role, path):
    method = "post" if path.endswith("/activate") else "put"
    response = getattr(client, method)(
        path,
        headers={"Authorization": _bearer({"tenant_id": str(TENANT), "role": role})},
        json={},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "só o dono configura a política"


def test_dono_passa_pelo_guarda():
    user = get_current_user(_bearer({"tenant_id": str(TENANT), "role": "dono"}))
    assert require_owner(user) is user
