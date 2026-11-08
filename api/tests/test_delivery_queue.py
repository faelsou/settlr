"""SETL-16: a fila do painel lê o banco e deixa filtrar a falha."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.channels.delivery import (
    ACEITO,
    ARQUIVO_AUSENTE,
    ARQUIVO_RECEBIDO,
    ENTREGUE,
    FALHOU,
    RECEIPT_BODY,
    file_state,
)
from app.channels.queue import deliveries_statement


def test_message_payload_carries_delivery_and_file():
    from app.api.schemas import message_out

    sent = message_out(
        SimpleNamespace(
            id=uuid4(),
            direction="out",
            author="regua",
            body="Lembrete",
            invoice_id=None,
            created_at=datetime(2026, 11, 8, tzinfo=UTC),
            delivery_status=ACEITO,
            media_key=None,
        )
    )
    missing = message_out(
        SimpleNamespace(
            id=uuid4(),
            direction="in",
            author="devedor",
            body=RECEIPT_BODY,
            invoice_id=None,
            created_at=datetime(2026, 11, 8, tzinfo=UTC),
            delivery_status=None,
            media_key=None,
        )
    )
    assert sent.delivery_status == ACEITO
    assert sent.file_status is None
    assert missing.file_status == ARQUIVO_AUSENTE


def test_file_state_is_received_missing_or_absent():
    assert file_state("olá", None) is None
    assert file_state(RECEIPT_BODY, "tenant/hash.png") == ARQUIVO_RECEBIDO
    assert file_state(RECEIPT_BODY, None) == ARQUIVO_AUSENTE
    assert file_state("  [comprovante]  ", None) == ARQUIVO_AUSENTE


def _sql_of(statement) -> str:
    from sqlalchemy.dialects import postgresql

    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _sql(failed_only: bool) -> str:
    return _sql_of(deliveries_statement(failed_only=failed_only))


def test_failure_filter_is_a_bank_predicate():
    opened = _sql(False)
    failed = _sql(True)
    assert "falhou" not in opened
    assert "falhou" in failed
    assert "evolution" not in failed.lower()
    assert "comprovante" in opened


def test_queue_http_returns_sent_delivered_failed_and_the_file(monkeypatch):
    from fastapi.testclient import TestClient

    import app.channels.whatsapp as whatsapp
    from app.api.deps import get_db
    from app.services.cobranca import app

    monkeypatch.setattr("app.channels.reconcile.reconciliation_enabled", lambda: False)

    def _boom(*_args, **_kwargs):
        raise AssertionError("painel consultou a Evolution")

    monkeypatch.setattr(whatsapp.EvolutionClient, "__init__", _boom)

    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    conversation_id = uuid4()
    invoice_id = uuid4()
    rows = [
        (
            SimpleNamespace(
                id=uuid4(),
                conversation_id=conversation_id,
                invoice_id=invoice_id,
                direction="out",
                body="Lembrete",
                delivery_status=ACEITO,
                media_key=None,
                created_at=now,
            ),
            "Ana",
        ),
        (
            SimpleNamespace(
                id=uuid4(),
                conversation_id=conversation_id,
                invoice_id=None,
                direction="out",
                body="Segunda via",
                delivery_status=ENTREGUE,
                media_key="tenant/boleto.pdf",
                created_at=now,
            ),
            "Ana",
        ),
        (
            SimpleNamespace(
                id=uuid4(),
                conversation_id=conversation_id,
                invoice_id=None,
                direction="out",
                body="Régua",
                delivery_status=FALHOU,
                media_key=None,
                created_at=now,
            ),
            "Ana",
        ),
        (
            SimpleNamespace(
                id=uuid4(),
                conversation_id=conversation_id,
                invoice_id=None,
                direction="in",
                body=RECEIPT_BODY,
                delivery_status=None,
                media_key=None,
                created_at=now,
            ),
            "Ana",
        ),
    ]

    class _Session:
        def __init__(self) -> None:
            self.statements: list = []

        def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(all=lambda: rows)

        def scalar(self, statement):
            self.statements.append(statement)
            return len(rows)

    session = _Session()

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/conversations/deliveries", headers=_auth())
        failed = client.get("/conversations/deliveries?falhou=true", headers=_auth())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    by_status = {item["delivery_status"]: item for item in body["items"]}
    assert by_status[ACEITO]["file_status"] is None
    assert by_status[ENTREGUE]["file_status"] == ARQUIVO_RECEBIDO
    assert by_status[FALHOU]["debtor_name"] == "Ana"
    assert by_status[FALHOU]["invoice_id"] is None
    missing = next(item for item in body["items"] if item["file_status"] == ARQUIVO_AUSENTE)
    assert missing["body"] == RECEIPT_BODY
    assert str(invoice_id) == by_status[ACEITO]["invoice_id"]

    assert failed.status_code == 200
    compiled = [_sql_of(statement) for statement in session.statements]
    assert any("falhou" in sql for sql in compiled)
    assert all("evolution" not in sql for sql in compiled)


def _auth() -> dict[str, str]:
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "user-1",
            "email": "operador@settlr.test",
            "aud": settings.jwt_audience,
            "app_metadata": {"role": "operador", "tenant_id": str(uuid4())},
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
