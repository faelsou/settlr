"""SETL-19: a empresa cria a conta pela tela, com papéis e convite.

A ativação segue devolvendo 422 se faltar campo obrigatório. O atendente não
confirma baixa. O financeiro confirma. O dono configura a política. O convite
sai por e-mail, com link e sem senha.
"""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.schemas import ExceptionOut
from app.core.config import get_settings
from app.models import Tenant, TenantMember
from app.models.enums import ExceptionStatus, ExceptionType
from app.services.cadastro import app as cadastro_app
from app.services.conciliacao import app as conciliacao_app


class _Linhas:
    def __init__(self, rows: list) -> None:
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Memoria:
    """Sessão em memória. O filtro olha o SQL compilado para achar e-mail ou hash."""

    def __init__(self) -> None:
        self.tenants: list = []
        self.members: list = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def begin(self):
        return self

    def add(self, obj) -> None:
        if isinstance(obj, Tenant):
            self.tenants.append(obj)
        elif isinstance(obj, TenantMember):
            self.members.append(obj)

    def flush(self) -> None:
        for pool in (self.tenants, self.members):
            for obj in pool:
                if getattr(obj, "id", None) is None:
                    obj.id = uuid4()

    def get(self, model, key):
        pool = self.tenants if model is Tenant else self.members
        for obj in pool:
            if getattr(obj, "id", None) == key:
                return obj
        return None

    def scalars(self, query):
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        if "tenant_members" in sql:
            rows = list(self.members)
            if "invite_token_hash" in sql:
                rows = [m for m in rows if m.invite_token_hash and m.invite_token_hash in sql]
            elif "email =" in sql or "email=" in sql:
                rows = [m for m in self.members if m.email in sql]
            if "ativo" in sql:
                rows = [m for m in rows if m.status == "ativo"]
            return _Linhas(rows)
        return _Linhas(list(self.tenants))


def _token(role: str, tenant_id, email: str) -> str:
    settings = get_settings()
    encoded = jwt.encode(
        {
            "sub": email,
            "email": email,
            "aud": settings.jwt_audience,
            "app_metadata": {"role": role, "tenant_id": str(tenant_id)},
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return encoded if isinstance(encoded, str) else encoded.decode()


def _empresa(client: TestClient, *, legal: str | None = None) -> dict:
    defaults = client.get("/onboarding/defaults")
    assert defaults.status_code == 200, defaults.text
    body = {
        **defaults.json(),
        "name": "Clínica Norte",
        "slug": "clinica-norte",
        "owner_email": "dona@clinica.test",
        "whatsapp_instance": "norte",
        "whatsapp_number": "11988887777",
        "legal_basis": legal,
        "baseline_avg_days_late": 18.54,
    }
    created = client.post("/onboarding", json=body)
    assert created.status_code == 201, created.text
    return created.json()


def test_empresa_cria_pela_tela_e_ativacao_recusa_sem_base_legal(monkeypatch):
    memoria = _Memoria()
    monkeypatch.setattr("app.api.routes.onboarding.SessionLocal", lambda: memoria)
    monkeypatch.setattr("app.api.routes.onboarding.set_tenant", lambda *_a, **_k: None)
    monkeypatch.setattr("app.api.routes.onboarding.audit", lambda *_a, **_k: None)
    monkeypatch.setattr("app.onboarding.members.set_tenant", lambda *_a, **_k: None)
    monkeypatch.setattr("app.api.routes.members.SessionLocal", lambda: memoria)

    sent: dict[str, str] = {}

    def _grava_email(to: str, subject: str, body: str) -> None:
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr("app.onboarding.members.send_email", _grava_email)

    def _db():
        yield memoria

    cadastro_app.dependency_overrides[get_db] = _db
    client = TestClient(cadastro_app)
    try:
        conta = _empresa(client)
        assert conta["role"] == "dono"
        assert conta["email"] == "dona@clinica.test"
        assert "base legal (LGPD)" in conta["missing"]
        assert any(step["key"] == "D+5" for step in memoria.tenants[0].dunning_rules["steps"])
        assert memoria.tenants[0].negotiation_policy["max_installments"] == 6
        assert memoria.tenants[0].baseline_avg_days_late == 18.5

        headers = {"Authorization": f"Bearer {conta['access_token']}"}
        bloqueada = client.post("/settings/activate", headers=headers)
        assert bloqueada.status_code == 422
        assert "base legal (LGPD)" in bloqueada.json()["detail"]["missing"]
        assert memoria.tenants[0].active is False

        atual = client.get("/settings", headers=headers)
        assert atual.status_code == 200, atual.text
        corpo = atual.json()
        corpo["legal_basis"] = "execução de contrato"
        corpo["negotiation_policy"]["max_installments"] = 4
        gravada = client.put("/settings", headers=headers, json=corpo)
        assert gravada.status_code == 200, gravada.text
        assert gravada.json()["negotiation_policy"]["max_installments"] == 4
        assert "base legal (LGPD)" not in gravada.json()["missing"]

        caixa = _token("financeiro", conta["tenant_id"], "caixa@clinica.test")
        financeiro = {"Authorization": f"Bearer {caixa}"}
        recusada = client.put("/settings", headers=financeiro, json=corpo)
        assert recusada.status_code == 403
        assert recusada.json()["detail"] == "só o dono configura a política"

        convite = client.post(
            "/members/invites",
            headers=headers,
            json={"email": "caixa@clinica.test", "role": "financeiro"},
        )
        assert convite.status_code == 201, convite.text
        assert convite.json()["status"] == "convidado"
        assert convite.json()["delivered"] is True
        assert "invite" not in convite.json()
        assert sent["to"] == "caixa@clinica.test"
        assert "/convite/" in sent["body"]
        assert "senha" not in sent["body"].lower()
        assert "password" not in sent["body"].lower()
        link = next(line.strip() for line in sent["body"].splitlines() if "/convite/" in line)
        token = link.rsplit("/convite/", 1)[1]

        aceite = client.post("/members/accept", json={"token": token})
        assert aceite.status_code == 200, aceite.text
        assert aceite.json()["role"] == "financeiro"
        assert aceite.json()["email"] == "caixa@clinica.test"
        assert "access_token" in aceite.json()
    finally:
        cadastro_app.dependency_overrides.pop(get_db, None)


def test_onboarding_exige_atraso_anterior_nao_negativo():
    client = TestClient(cadastro_app)
    defaults = client.get("/onboarding/defaults")
    assert defaults.status_code == 200, defaults.text
    base = {
        **defaults.json(),
        "name": "Clínica Norte",
        "slug": "clinica-norte",
        "owner_email": "dona@clinica.test",
    }
    sem_linha = client.post("/onboarding", json=base)
    assert sem_linha.status_code == 422
    negativa = client.post("/onboarding", json={**base, "baseline_avg_days_late": -1})
    assert negativa.status_code == 422


def test_atendente_nao_confirma_baixa_e_financeiro_confirma(monkeypatch):
    tenant_id = uuid4()
    payment = SimpleNamespace(
        id=uuid4(),
        bank_confirmed_at=datetime.now(UTC),
        amount=Decimal("100.00"),
    )
    exc = SimpleNamespace(
        id=uuid4(),
        type=ExceptionType.SUGESTAO_MATCH,
        status=ExceptionStatus.ABERTA,
        payment_id=payment.id,
        invoice_id=uuid4(),
        conversation_id=None,
        details={},
        assignee=None,
        resolution=None,
        created_at=datetime.now(UTC),
        resolved_at=None,
        tenant_id=tenant_id,
    )

    class _Db:
        def scalars(self, _query):
            return _Linhas([exc])

        def get(self, model, key):
            if key == payment.id:
                return payment
            return None

        def add(self, _obj) -> None:
            return None

        def flush(self) -> None:
            return None

    banco = _Db()

    def _db():
        yield banco

    anterior = conciliacao_app.dependency_overrides.get(get_db)
    conciliacao_app.dependency_overrides[get_db] = _db
    monkeypatch.setattr("app.api.routes.exceptions.apply_allocations", lambda *_a, **_k: None)
    monkeypatch.setattr("app.api.routes.exceptions.audit", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.api.routes.exceptions._out",
        lambda _db, items: [
            ExceptionOut(
                id=items[0].id,
                type=str(items[0].type),
                status=str(items[0].status),
                payment=None,
                invoice_id=items[0].invoice_id,
                conversation_id=None,
                details={},
                assignee=items[0].assignee,
                resolution=items[0].resolution,
                created_at=items[0].created_at,
                resolved_at=items[0].resolved_at,
            )
        ],
    )
    client = TestClient(conciliacao_app)
    corpo = {"allocations": [{"invoice_id": str(exc.invoice_id), "amount": "100.00"}]}
    try:
        mesa = _token("atendente", tenant_id, "mesa@clinica.test")
        atendente = client.post(
            f"/exceptions/{exc.id}/confirm",
            headers={"Authorization": f"Bearer {mesa}"},
            json=corpo,
        )
        assert atendente.status_code == 403
        assert atendente.json()["detail"] == "atendente não confirma baixa"
        assert exc.status == ExceptionStatus.ABERTA

        caixa = _token("financeiro", tenant_id, "caixa@clinica.test")
        financeiro = client.post(
            f"/exceptions/{exc.id}/confirm",
            headers={"Authorization": f"Bearer {caixa}"},
            json=corpo,
        )
        assert financeiro.status_code == 200, financeiro.text
        assert financeiro.json()["status"] == "resolvida"
    finally:
        if anterior is None:
            conciliacao_app.dependency_overrides.pop(get_db, None)
        else:
            conciliacao_app.dependency_overrides[get_db] = anterior


def test_convite_nao_leva_login_compartilhado():
    from app.onboarding.members import invite_copy

    _subject, body = invite_copy("Clínica Norte", "atendente", "http://localhost:3000/convite/abc")
    assert "http://localhost:3000/convite/abc" in body
    assert "senha" not in body.lower()
    assert "password" not in body.lower()
