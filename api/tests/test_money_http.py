"""SETL-14: baixa, acordo e isolamento entre tenants, pelo HTTP e com RLS.

A role da aplicação não é dona das tabelas e não ignora o RLS. Confirmar, rejeitar
e importar passam pelo TestClient. O acordo nasce na tool do agente (não há rota
de painel); o HTTP prova que só o tenant dono lê as parcelas.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.core.config import get_settings
from app.core.db import set_tenant
from app.models import Agreement, AuditLog, Debtor, Invoice, Match, Payment, ReviewException, Tenant
from app.models.enums import ExceptionType, InvoiceStatus, PaymentOrigin, PaymentStatus
from app.services.cadastro import app as cadastro_app
from app.services.conciliacao import app as conciliacao_app

DB_NAME = "cobranca_http_test"
APP_ROLE = "cobranca_app"
APP_PASSWORD = "cobranca_app"
ENV_KEYS = (
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_ADMIN_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_APP_PASSWORD",
)
HOJE = date(2026, 11, 7)
PAGO_EM = datetime(2026, 11, 7, 15, tzinfo=UTC)
baixas_emissor: list[tuple] = []


@dataclass(frozen=True)
class Caso:
    tenant_id: UUID
    email: str
    debtor_id: UUID
    invoice_id: UUID
    payment_id: UUID | None = None
    exception_id: UUID | None = None


@dataclass
class Banco:
    admin: sessionmaker[Session]
    app: sessionmaker[Session]
    conc: TestClient
    cad: TestClient

    def limpar(self) -> None:
        with self.admin() as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("TRUNCATE TABLE tenants CASCADE"))

    @contextmanager
    def como_app(self, tenant_id: UUID) -> Iterator[Session]:
        with self.app() as session, session.begin():
            set_tenant(session, tenant_id)
            yield session


def _url(user: str, password: str, host: str, port: int, database: str) -> str:
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
    )


def _engine(url: str, *, autocommit: bool = False):
    kwargs: dict = {"pool_pre_ping": True, "connect_args": {"connect_timeout": 3}}
    if autocommit:
        kwargs["isolation_level"] = "AUTOCOMMIT"
    return create_engine(url, **kwargs)


def _manutencao():
    host = os.environ.get("TEST_PG_HOST", "127.0.0.1")
    user = os.environ.get("TEST_PG_USER", "cobranca")
    password = os.environ.get("TEST_PG_PASSWORD", "cobranca")
    port_env = os.environ.get("TEST_PG_PORT")
    ports = [int(port_env)] if port_env else [55432, 5432]
    falhas: list[str] = []
    for port in ports:
        for database in ("cobranca", "postgres"):
            engine = _engine(_url(user, password, host, port, database), autocommit=True)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return host, port, user, password, engine
            except Exception as exc:
                falhas.append(f"{host}:{port}/{database} ({exc.__class__.__name__})")
                engine.dispose()
    mensagem = "Postgres de teste indisponível: " + "; ".join(falhas)
    if os.environ.get("CI") or os.environ.get("TEST_PG_PORT"):
        pytest.fail(mensagem)
    pytest.skip(mensagem)


def _aplicar_schema(host: str, port: int, user: str, password: str) -> None:
    saved = {key: os.environ.get(key) for key in ENV_KEYS}
    os.environ["DATABASE_HOST"] = host
    os.environ["DATABASE_PORT"] = str(port)
    os.environ["DATABASE_NAME"] = DB_NAME
    os.environ["DATABASE_ADMIN_USER"] = user
    os.environ["POSTGRES_PASSWORD"] = password
    os.environ["DATABASE_USER"] = APP_ROLE
    os.environ["POSTGRES_APP_PASSWORD"] = APP_PASSWORD
    get_settings.cache_clear()
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "app" / "models" / "migrations"))
    try:
        command.upgrade(cfg, "head")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def _derruba(maint, *engines) -> None:
    for engine in engines:
        engine.dispose()
    with maint.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": DB_NAME},
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))


@pytest.fixture(scope="session")
def banco() -> Iterator[Banco]:
    host, port, user, password, maint = _manutencao()
    admin_engine = _engine(_url(user, password, host, port, DB_NAME))
    app_engine = _engine(_url(APP_ROLE, APP_PASSWORD, host, port, DB_NAME))
    try:
        with maint.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": APP_ROLE}
            ).first()
            verbo = "ALTER ROLE" if existe else "CREATE ROLE"
            papel_sql = (
                f"{verbo} {APP_ROLE} "
                f"{'WITH ' if existe else ''}LOGIN PASSWORD '{APP_PASSWORD}' "
                "NOSUPERUSER NOBYPASSRLS"
            )
            conn.execute(text(papel_sql))
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": DB_NAME},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
            conn.execute(text(f"CREATE DATABASE {DB_NAME} OWNER {user}"))
            conn.execute(text(f"GRANT CONNECT ON DATABASE {DB_NAME} TO {APP_ROLE}"))
        _aplicar_schema(host, port, user, password)
        with admin_engine.begin() as conn:
            conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
            papel = conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :role"),
                {"role": APP_ROLE},
            ).one()
            assert papel.rolsuper is False
            assert papel.rolbypassrls is False
            dono = conn.execute(
                text("SELECT tableowner FROM pg_tables WHERE tablename = 'payments'")
            ).scalar()
            assert dono != APP_ROLE
            rls = conn.execute(
                text(
                    """
                    SELECT c.relrowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relname IN (
                        'payments', 'invoices', 'exceptions', 'audit_log', 'agreements'
                      )
                    """
                )
            ).scalars().all()
            assert rls and all(rls)
        with app_engine.connect() as conn:
            assert conn.execute(text("SELECT current_user")).scalar() == APP_ROLE

        fabrica = sessionmaker(bind=app_engine, expire_on_commit=False, autoflush=False)

        def get_db_app(user: CurrentUser = Depends(require_tenant_user)) -> Iterator[Session]:
            with fabrica() as session, session.begin():
                set_tenant(session, user.tenant_id)
                yield session

        for aplicacao in (conciliacao_app, cadastro_app):
            aplicacao.dependency_overrides[get_db] = get_db_app

        yield Banco(
            admin=sessionmaker(bind=admin_engine, expire_on_commit=False, autoflush=False),
            app=fabrica,
            conc=TestClient(conciliacao_app, raise_server_exceptions=False),
            cad=TestClient(cadastro_app, raise_server_exceptions=False),
        )
    finally:
        for aplicacao in (conciliacao_app, cadastro_app):
            aplicacao.dependency_overrides.pop(get_db, None)
        _derruba(maint, admin_engine, app_engine)


@pytest.fixture(autouse=True)
def _banco_limpo(banco: Banco, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.core import db as dbmod

    original = dbmod.SessionLocal
    dbmod.SessionLocal = banco.app
    baixas_emissor.clear()
    monkeypatch.setattr("app.reconciliation.service.redis_lock", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr("app.api.routes.payments.reconcile.delay", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.ingest.tasks.settle_issuer_charges.delay",
        lambda *args, **_kwargs: baixas_emissor.append(args),
    )
    banco.limpar()
    try:
        yield
    finally:
        dbmod.SessionLocal = original


def _token(tenant_id: UUID, email: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    encoded = jwt.encode(
        {
            "sub": email,
            "email": email,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "app_metadata": {"tenant_id": str(tenant_id), "role": "operador"},
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return encoded if isinstance(encoded, str) else encoded.decode()


def _auth(caso: Caso) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(caso.tenant_id, caso.email)}"}


def _semear_pagamento(
    banco: Banco,
    *,
    slug: str,
    email: str,
    nome: str,
    documento: str,
    external_id: str,
    bank: bool,
    origin: PaymentOrigin,
    status: PaymentStatus,
    exc_type: ExceptionType,
    e2e_id: str | None = None,
    issuer: str | None = None,
    raw: dict | None = None,
) -> Caso:
    with banco.admin() as session, session.begin():
        tenant = Tenant(
            name=nome,
            slug=slug,
            active=True,
            timezone="America/Sao_Paulo",
            issuer_provider=issuer,
            issuer_config={"api_key": "k"} if issuer else {},
        )
        session.add(tenant)
        session.flush()
        debtor = Debtor(tenant_id=tenant.id, name=nome, document=documento, phone="11999999999")
        session.add(debtor)
        session.flush()
        invoice = Invoice(
            tenant_id=tenant.id,
            debtor_id=debtor.id,
            external_id=external_id,
            description="mensalidade",
            amount=Decimal("100.00"),
            amount_paid=Decimal("0"),
            due_date=date(2026, 11, 1),
            status=InvoiceStatus.EM_COBRANCA,
        )
        session.add(invoice)
        session.flush()
        payment = Payment(
            tenant_id=tenant.id,
            origin=origin,
            status=status,
            amount=Decimal("100.00"),
            paid_at=PAGO_EM,
            payer_name=nome,
            payer_doc=documento,
            debtor_id=debtor.id,
            e2e_id=e2e_id,
            raw=raw or {},
            bank_confirmed_at=datetime.now(UTC) if bank else None,
        )
        session.add(payment)
        session.flush()
        exc = ReviewException(
            tenant_id=tenant.id,
            type=exc_type,
            status="aberta",
            payment_id=payment.id,
            invoice_id=invoice.id,
            details={"reason": "teste"},
        )
        session.add(exc)
        session.flush()
        return Caso(tenant.id, email, debtor.id, invoice.id, payment.id, exc.id)


def _titulo(banco: Banco, invoice_id: UUID) -> tuple[str, Decimal]:
    with banco.admin() as session:
        invoice = session.get(Invoice, invoice_id)
        assert invoice is not None
        return invoice.status, invoice.amount_paid


def test_confirmar_excecao_baixa_e_registra_o_responsavel(banco: Banco) -> None:
    caso = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="NF-1",
        bank=True,
        origin=PaymentOrigin.EXTRATO,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
    )
    resposta = banco.conc.post(
        f"/exceptions/{caso.exception_id}/confirm",
        headers=_auth(caso),
        json={
            "allocations": [{"invoice_id": str(caso.invoice_id), "amount": "100.00"}],
            "note": "conferido",
        },
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "resolvida"
    assert _titulo(banco, caso.invoice_id) == (InvoiceStatus.PAGO, Decimal("100.00"))

    with banco.como_app(caso.tenant_id) as session:
        baixa = session.scalars(select(AuditLog).where(AuditLog.action == "baixa")).one()
        fechamento = session.scalars(
            select(AuditLog).where(AuditLog.action == "excecao_resolvida")
        ).one()
        match = session.scalars(select(Match).where(Match.invoice_id == caso.invoice_id)).one()
    assert baixa.actor == "humano:operador@clinica.test"
    assert fechamento.actor == "humano:operador@clinica.test"
    assert fechamento.after["note"] == "conferido"
    assert match.provisional is False
    assert match.confirmed_by == "humano:operador@clinica.test"


def test_comprovante_sem_banco_nao_quita_o_titulo(banco: Banco) -> None:
    caso = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="NF-1",
        bank=False,
        origin=PaymentOrigin.COMPROVANTE,
        status=PaymentStatus.AGUARDANDO_BANCO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
    )
    resposta = banco.conc.post(
        f"/exceptions/{caso.exception_id}/confirm",
        headers=_auth(caso),
        json={"allocations": [{"invoice_id": str(caso.invoice_id), "amount": "100.00"}]},
    )
    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "pagamento ainda sem confirmação do banco"
    assert _titulo(banco, caso.invoice_id) == (InvoiceStatus.EM_COBRANCA, Decimal("0"))
    with banco.admin() as session:
        match = session.scalars(select(Match).where(Match.invoice_id == caso.invoice_id)).first()
        assert match is None
        pagamento = session.get(Payment, caso.payment_id)
        assert pagamento is not None
        assert pagamento.status == PaymentStatus.AGUARDANDO_BANCO
        assert pagamento.bank_confirmed_at is None


def test_rejeitar_sugestao_devolve_pagamento_nao_identificado(banco: Banco) -> None:
    caso = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="NF-1",
        bank=True,
        origin=PaymentOrigin.EXTRATO,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
    )
    resposta = banco.conc.post(
        f"/exceptions/{caso.exception_id}/reject",
        headers=_auth(caso),
        json={"note": "não é esse título"},
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "rejeitada"
    assert _titulo(banco, caso.invoice_id) == (InvoiceStatus.EM_COBRANCA, Decimal("0"))

    abertas = banco.conc.get("/exceptions", headers=_auth(caso))
    assert abertas.status_code == 200
    corpo = abertas.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["type"] == "pagamento_nao_identificado"
    assert corpo["items"][0]["payment"]["id"] == str(caso.payment_id)
    with banco.como_app(caso.tenant_id) as session:
        auditoria = session.scalars(
            select(AuditLog).where(AuditLog.action == "excecao_rejeitada")
        ).one()
    assert auditoria.actor == "humano:operador@clinica.test"


def test_importar_extrato_registra_pagamento_do_banco(banco: Banco) -> None:
    caso = _semear_tenant(banco, slug="clinica", email="operador@clinica.test", nome="Clínica")
    outro = _semear_tenant(banco, slug="escola", email="operador@escola.test", nome="Escola")
    csv = (
        "data,valor,e2e_id,documento,nome\n"
        "07/11/2026 10:00,150.50,E2EIMPORT1,12345678901,Maria\n"
    )
    resposta = banco.conc.post(
        "/payments/import",
        headers=_auth(caso),
        files={"file": ("extrato.csv", csv, "text/csv")},
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["created"] == 1
    assert resposta.json()["duplicates"] == 0

    de_novo = banco.conc.post(
        "/payments/import",
        headers=_auth(caso),
        files={"file": ("extrato.csv", csv, "text/csv")},
    )
    assert de_novo.status_code == 200, de_novo.text
    assert de_novo.json()["created"] == 0
    assert de_novo.json()["duplicates"] == 1

    lista = banco.conc.get("/payments", headers=_auth(caso))
    assert lista.status_code == 200
    itens = lista.json()["items"]
    assert len(itens) == 1
    assert itens[0]["origin"] == "extrato"
    assert itens[0]["status"] == "confirmado"
    assert itens[0]["bank_confirmed"] is True
    assert Decimal(str(itens[0]["amount"])) == Decimal("150.50")
    alheio = banco.conc.get("/payments", headers=_auth(outro))
    assert alheio.json()["total"] == 0
    with banco.admin() as session:
        pagamento = session.scalars(select(Payment).where(Payment.e2e_id == "E2EIMPORT1")).one()
        assert pagamento.tenant_id == caso.tenant_id
        assert pagamento.bank_confirmed_at is not None
        assert session.get(Tenant, outro.tenant_id) is not None


def test_tenant_nao_le_nem_altera_dinheiro_do_outro(banco: Banco) -> None:
    clinica = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="NF-A",
        bank=True,
        origin=PaymentOrigin.EXTRATO,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
    )
    escola = _semear_pagamento(
        banco,
        slug="escola",
        email="operador@escola.test",
        nome="Escola",
        documento="10987654321",
        external_id="NF-B",
        bank=True,
        origin=PaymentOrigin.WEBHOOK,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.PAGAMENTO_NAO_IDENTIFICADO,
    )

    pagamentos = banco.conc.get("/payments", headers=_auth(clinica)).json()
    assert {item["id"] for item in pagamentos["items"]} == {str(clinica.payment_id)}
    titulos = banco.cad.get("/invoices", headers=_auth(clinica)).json()
    assert {item["id"] for item in titulos["items"]} == {str(clinica.invoice_id)}
    alheio = banco.cad.get(f"/invoices/{escola.invoice_id}", headers=_auth(clinica))
    assert alheio.status_code == 404
    assert banco.conc.get("/exceptions", headers=_auth(clinica)).json()["total"] == 1

    leitura = banco.conc.post(
        f"/exceptions/{escola.exception_id}/confirm",
        headers=_auth(clinica),
        json={"allocations": [{"invoice_id": str(escola.invoice_id), "amount": "100.00"}]},
    )
    assert leitura.status_code == 404
    assert _titulo(banco, escola.invoice_id) == (InvoiceStatus.EM_COBRANCA, Decimal("0"))

    cruzado = banco.conc.post(
        f"/exceptions/{clinica.exception_id}/confirm",
        headers=_auth(clinica),
        json={"allocations": [{"invoice_id": str(escola.invoice_id), "amount": "100.00"}]},
    )
    assert cruzado.status_code >= 400
    assert _titulo(banco, escola.invoice_id) == (InvoiceStatus.EM_COBRANCA, Decimal("0"))
    assert _titulo(banco, clinica.invoice_id) == (InvoiceStatus.EM_COBRANCA, Decimal("0"))
    with banco.admin() as session:
        exc = session.get(ReviewException, clinica.exception_id)
        assert exc is not None
        assert exc.status == "aberta"


def test_criar_acordo_so_o_tenant_ve_as_parcelas(
    banco: Banco, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agent.tools import create_agreement
    from app.ingest.issuers import IssuedCharge

    clinica = _semear_acordo(banco, slug="clinica", email="operador@clinica.test", nome="Clínica")
    escola = _semear_tenant(banco, slug="escola", email="operador@escola.test", nome="Escola")

    class _Emissor:
        def issue(self, **_kwargs) -> IssuedCharge:
            return IssuedCharge(
                external_id="pay_acordo",
                txid="pay_acordo",
                pix_copy_paste="00020126PIX",
                digitable_line=None,
                payment_url="https://asaas/pay_acordo",
            )

        def cancel(self, _payment_id: str) -> None:
            return None

    monkeypatch.setattr("app.agent.tools.get_adapter", lambda *_a, **_k: _Emissor())
    criado = create_agreement.invoke({
        "tenant_id": clinica.tenant_id,
        "debtor_id": clinica.debtor_id,
        "invoice_ids": [clinica.invoice_id],
        "option_id": "a_vista",
        "today": HOJE,
    })
    assert "00020126PIX" in criado["invoices"][0]["pix_copy_paste"]

    lista = banco.cad.get("/invoices", headers=_auth(clinica))
    assert lista.status_code == 200, lista.text
    itens = lista.json()["items"]
    assert {item["status"] for item in itens} == {"renegociado", "em_cobranca"}
    origem_http = next(item for item in itens if item["status"] == "renegociado")
    parcela = next(item for item in itens if item["status"] == "em_cobranca")
    assert origem_http["id"] == str(clinica.invoice_id)
    assert parcela["agreement_id"]
    assert parcela["parent_id"] == str(clinica.invoice_id)
    assert Decimal(str(parcela["amount"])) == Decimal("900.00")
    detalhe = banco.cad.get(f"/invoices/{clinica.invoice_id}", headers=_auth(clinica))
    assert detalhe.status_code == 200, detalhe.text
    assert [item["id"] for item in detalhe.json()["installments"]] == [parcela["id"]]

    assert banco.cad.get("/invoices", headers=_auth(escola)).json()["total"] == 0
    origem_alheia = banco.cad.get(f"/invoices/{clinica.invoice_id}", headers=_auth(escola))
    parcela_alheia = banco.cad.get(f"/invoices/{parcela['id']}", headers=_auth(escola))
    assert origem_alheia.status_code == 404
    assert parcela_alheia.status_code == 404

    with banco.admin() as session:
        origem = session.get(Invoice, clinica.invoice_id)
        assert origem is not None
        assert origem.status == InvoiceStatus.RENEGOCIADO
        acordo = session.scalars(
            select(Agreement).where(Agreement.tenant_id == clinica.tenant_id)
        ).one()
        nova = session.scalars(
            select(Invoice).where(Invoice.external_id == "pay_acordo")
        ).one()
        assert nova.agreement_id == acordo.id
        assert nova.pix_copy_paste == "00020126PIX"
        assert nova.tenant_id == clinica.tenant_id
        assert session.get(Debtor, clinica.debtor_id) is not None
        assert session.get(Tenant, escola.tenant_id) is not None
    with banco.como_app(clinica.tenant_id) as session:
        auditoria = session.scalars(select(AuditLog).where(AuditLog.action == "cria_acordo")).one()
    assert auditoria.actor == "agente"


def _semear_tenant(banco: Banco, *, slug: str, email: str, nome: str) -> Caso:
    with banco.admin() as session, session.begin():
        tenant = Tenant(name=nome, slug=slug, active=True, timezone="America/Sao_Paulo")
        session.add(tenant)
        session.flush()
        return Caso(tenant.id, email, uuid4(), uuid4())


def _semear_acordo(banco: Banco, *, slug: str, email: str, nome: str) -> Caso:
    with banco.admin() as session, session.begin():
        tenant = Tenant(
            name=nome,
            slug=slug,
            active=True,
            timezone="America/Sao_Paulo",
            issuer_provider="asaas",
            issuer_config={},
        )
        session.add(tenant)
        session.flush()
        debtor = Debtor(
            tenant_id=tenant.id, name="Maria", document="12345678901", phone="11999999999",
        )
        session.add(debtor)
        session.flush()
        invoice = Invoice(
            tenant_id=tenant.id,
            debtor_id=debtor.id,
            external_id="NF-ORIGEM",
            description="mensalidade",
            amount=Decimal("1000.00"),
            amount_paid=Decimal("0"),
            due_date=date(2026, 10, 1),
            status=InvoiceStatus.EM_COBRANCA,
        )
        session.add(invoice)
        session.flush()
        return Caso(tenant.id, email, debtor.id, invoice.id)


def test_lista_separa_titulo_sem_pix_ou_boleto(banco: Banco) -> None:
    from app.dunning.service import eligible_invoice_ids

    hoje = date(2026, 11, 7)
    with banco.admin() as session, session.begin():
        tenant = Tenant(name="Clínica", slug="clinica-regua", active=False, timezone="America/Sao_Paulo")
        session.add(tenant)
        session.flush()
        debtor = Debtor(
            tenant_id=tenant.id, name="Padaria", document="12345678000190", phone="11988887777",
        )
        session.add(debtor)
        session.flush()

        def titulo(external_id: str, **codes: str | None) -> Invoice:
            row = Invoice(
                tenant_id=tenant.id,
                debtor_id=debtor.id,
                external_id=external_id,
                description="mensalidade",
                amount=Decimal("150.00"),
                amount_paid=Decimal("0"),
                due_date=hoje,
                status=InvoiceStatus.ABERTO,
                pix_copy_paste=codes.get("pix"),
                digitable_line=codes.get("boleto"),
                payment_url=codes.get("link"),
            )
            session.add(row)
            return row

        sem = titulo("SEM", link="https://pagar.exemplo/sem-codigo")
        branco = titulo("BRANCO", pix="   ")
        pago = titulo("PAGO")
        pago.status = InvoiceStatus.PAGO
        com_pix = titulo("PIX", pix="00020126PIX")
        com_boleto = titulo("BOLETO", boleto="34191790010104351004791020150008291070026000")
        session.flush()
        caso = Caso(tenant.id, "operador@clinica.test", debtor.id, sem.id)
        elegiveis = set(eligible_invoice_ids(session, tenant, hoje))

    assert elegiveis == {com_pix.id, com_boleto.id}

    resposta = banco.cad.get("/invoices?sem_pagamento=true", headers=_auth(caso))
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["total"] == 2
    assert {item["external_id"] for item in corpo["items"]} == {"SEM", "BRANCO"}
    assert all(item["has_payment_code"] is False for item in corpo["items"])

    carteira = banco.cad.get("/invoices", headers=_auth(caso))
    assert carteira.status_code == 200
    assert {item["external_id"] for item in carteira.json()["items"]} == {
        "SEM", "BRANCO", "PAGO", "PIX", "BOLETO",
    }

    from app.dunning.service import process_invoice
    from app.models import DunningEvent

    with banco.admin() as session, session.begin():
        row = session.get(Invoice, sem.id)
        tenant = session.get(Tenant, caso.tenant_id)
        assert row is not None and tenant is not None
        row.pix_copy_paste = "00020126AGORA"
        row.due_date = hoje - timedelta(days=5)
        session.flush()
        outcome = process_invoice(session, tenant, row.id, hoje)
        eventos = session.scalars(select(DunningEvent).where(DunningEvent.invoice_id == row.id)).all()
    assert outcome.action == "send"
    assert outcome.reason == "D+5"
    assert eventos == []


def _confirmar(banco: Banco, caso: Caso) -> None:
    resposta = banco.conc.post(
        f"/exceptions/{caso.exception_id}/confirm",
        headers=_auth(caso),
        json={"allocations": [{"invoice_id": str(caso.invoice_id), "amount": "100.00"}]},
    )
    assert resposta.status_code == 200, resposta.text


def test_exportacao_do_periodo_traz_titulo_valor_data_e_identificador(banco: Banco) -> None:
    caso = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="NF-1",
        bank=True,
        origin=PaymentOrigin.EXTRATO,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
        e2e_id="E2E-PIX-001",
    )
    _confirmar(banco, caso)
    with banco.admin() as session, session.begin():
        session.add(
            Match(
                tenant_id=caso.tenant_id,
                payment_id=caso.payment_id,
                invoice_id=caso.invoice_id,
                amount_applied=Decimal("1.00"),
                method="manual",
                score=1,
                provisional=True,
                confirmed_by="sistema",
            )
        )

    arquivo = banco.conc.get(
        "/payments/export",
        headers=_auth(caso),
        params={"start": "2026-11-01", "end": "2026-11-30"},
    )
    assert arquivo.status_code == 200, arquivo.text
    assert "text/csv" in arquivo.headers["content-type"]
    assert arquivo.headers["content-disposition"] == 'attachment; filename="baixas-2026-11-01-2026-11-30.csv"'
    assert arquivo.content.decode("utf-8-sig").splitlines() == [
        "titulo;valor;data;identificador_bancario",
        "NF-1;100.00;2026-11-07;E2E-PIX-001",
    ]

    fora = banco.conc.get(
        "/payments/export",
        headers=_auth(caso),
        params={"start": "2026-10-01", "end": "2026-10-31"},
    )
    assert fora.status_code == 200
    assert fora.content.decode("utf-8-sig").splitlines() == ["titulo;valor;data;identificador_bancario"]

    invertido = banco.conc.get(
        "/payments/export",
        headers=_auth(caso),
        params={"start": "2026-11-30", "end": "2026-11-01"},
    )
    assert invertido.status_code == 422
    assert invertido.json()["detail"] == "o fim do período é anterior ao início"


def test_titulo_conciliado_marca_cobranca_no_emissor(banco: Banco, monkeypatch: pytest.MonkeyPatch) -> None:
    caso = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="pay_piloto",
        bank=True,
        origin=PaymentOrigin.EXTRATO,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
        e2e_id="E2E-PIX-001",
        issuer="asaas",
    )
    _confirmar(banco, caso)
    assert baixas_emissor == [(str(caso.tenant_id), [str(caso.invoice_id)])]

    chamadas: list[tuple] = []

    class _Emissor:
        def mark_paid(self, payment_id: str, paid_on: date, value: Decimal) -> str:
            chamadas.append((payment_id, paid_on, value))
            return "paid"

    monkeypatch.setattr("app.ingest.tasks.get_adapter", lambda *_args, **_kwargs: _Emissor())
    from app.ingest.tasks import settle_issuer_charges

    assert settle_issuer_charges(str(caso.tenant_id), [str(caso.invoice_id)]) == "paga"
    assert chamadas == [("pay_piloto", date(2026, 11, 7), Decimal("100.00"))]

    with banco.como_app(caso.tenant_id) as session:
        trilha = session.scalars(select(AuditLog).where(AuditLog.action == "baixa_emissor")).one()
    assert trilha.actor == "sistema"
    assert trilha.after["charge_id"] == "pay_piloto"
    assert trilha.after["resultado"] == "paga"
    assert trilha.after["valor"] == "100.00"
    assert trilha.after["data"] == "2026-11-07"


def test_webhook_do_emissor_nao_marca_a_cobranca_de_novo(
    banco: Banco, monkeypatch: pytest.MonkeyPatch,
) -> None:
    caso = _semear_pagamento(
        banco,
        slug="clinica",
        email="operador@clinica.test",
        nome="Clínica",
        documento="12345678901",
        external_id="pay_piloto",
        bank=True,
        origin=PaymentOrigin.WEBHOOK,
        status=PaymentStatus.EM_EXCECAO,
        exc_type=ExceptionType.SUGESTAO_MATCH,
        issuer="asaas",
        raw={"provider": "asaas", "event": "PAYMENT_RECEIVED"},
    )
    _confirmar(banco, caso)
    chamadas: list[tuple] = []

    class _Emissor:
        def mark_paid(self, *_args, **_kwargs) -> str:
            chamadas.append(_args)
            return "paid"

    monkeypatch.setattr("app.ingest.tasks.get_adapter", lambda *_args, **_kwargs: _Emissor())
    from app.ingest.tasks import settle_issuer_charges

    assert settle_issuer_charges(str(caso.tenant_id), [str(caso.invoice_id)]) == "ja_no_emissor"
    assert chamadas == []
    with banco.como_app(caso.tenant_id) as session:
        trilha = session.scalars(select(AuditLog).where(AuditLog.action == "baixa_emissor")).one()
    assert trilha.after["resultado"] == "ja_no_emissor"
