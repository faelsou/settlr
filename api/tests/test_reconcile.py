"""SETL-8: reconciliação em produção, saída pendente, comprovante no MinIO e alerta de sessão."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx

from app.channels.delivery import ACEITO, ENTREGUE, LIDO, PENDENTE, SEM_RECIBO
from app.channels.outbound import send_to_debtor
from app.channels.reconcile import plan_outbound_fixes, receipt_window, reconciliation_enabled
from app.channels.session import alert_session_down, connection_state, session_is_down
from app.channels.tasks import cache_inbound_media, fresh_inbound
from app.channels.turn import claim_turn
from app.channels.whatsapp import EvolutionWebhook
from app.dunning.rules import Step
from app.dunning.service import _send_step
from app.models import DunningEvent, Message
from app.models.enums import ExceptionType
from app.receipts.tasks import load_receipt_bytes, process_whatsapp_receipt


def test_reconciliation_runs_in_production_when_the_key_exists():
    assert reconciliation_enabled(SimpleNamespace(env="prod", evolution_api_key="key"))
    assert reconciliation_enabled(SimpleNamespace(env="dev", evolution_api_key="key"))
    assert not reconciliation_enabled(SimpleNamespace(env="prod", evolution_api_key=""))


def test_receipt_window_defaults_to_six_hours_and_honors_the_tenant():
    assert receipt_window(None) == timedelta(hours=6)
    assert receipt_window({"receipt_window_hours": 2}) == timedelta(hours=2)
    assert receipt_window({"receipt_window_hours": "nope"}) == timedelta(hours=6)


def test_outbound_receipt_from_evolution_wins_over_the_window():
    now = datetime(2026, 11, 7, 18, 0, tzinfo=UTC)
    old = now - timedelta(hours=8)
    fixes = plan_outbound_fixes(
        [
            ("WA1", ACEITO, old),
            ("WA2", ACEITO, old),
            ("WA3", ACEITO, now),
            ("WA4", SEM_RECIBO, old),
        ],
        [
            {"key": {"id": "WA1"}, "status": "DELIVERY_ACK"},
            {"key": {"id": "WA4"}, "status": "READ"},
        ],
        now=now,
        window=timedelta(hours=6),
    )
    assert fixes == [("WA1", ENTREGUE), ("WA2", SEM_RECIBO), ("WA4", LIDO)]


def test_outbound_is_pending_before_send_and_timeout_keeps_it(monkeypatch):
    order: list[str] = []
    session = MagicMock()
    session.flush.side_effect = lambda: order.append("flush")
    conv = SimpleNamespace(
        tenant_id=uuid4(), id=uuid4(), wa_jid="5511999999999@s.whatsapp.net", intent=None,
    )
    tenant = SimpleNamespace(whatsapp_instance="cobranca")
    client = MagicMock()

    def send_text(*_args, **_kwargs):
        order.append("send")
        added = session.add.call_args.args[0]
        assert added.delivery_status == PENDENTE
        raise httpx.TimeoutException("timeout")

    client.send_text.side_effect = send_text
    msg = send_to_debtor(session, tenant, conv, "oi", client=client)
    assert order[:2] == ["flush", "send"]
    assert msg.delivery_status == PENDENTE
    assert msg.wa_message_id is None


def test_accepted_send_moves_the_pending_row_to_aceito():
    session = MagicMock()
    conv = SimpleNamespace(
        tenant_id=uuid4(), id=uuid4(), wa_jid="5511999999999@s.whatsapp.net", intent=None,
    )
    tenant = SimpleNamespace(whatsapp_instance="cobranca")
    client = MagicMock()
    client.send_text.return_value = "WA9"
    msg = send_to_debtor(session, tenant, conv, "oi", client=client)
    assert msg.delivery_status == ACEITO
    assert msg.wa_message_id == "WA9"


def test_dunning_timeout_keeps_the_pending_message(monkeypatch):
    tenant_id = uuid4()
    invoice = SimpleNamespace(
        id=uuid4(),
        description="mensalidade",
        amount=Decimal("10"),
        amount_open=Decimal("10"),
        due_date=datetime(2026, 11, 7, tzinfo=UTC).date(),
        pix_copy_paste="pix",
        payment_url=None,
        digitable_line=None,
        external_id="1",
    )
    debtor = SimpleNamespace(
        id=uuid4(), name="Maria Souza", phone="5511999999999", phones=[], email=None,
    )
    tenant = SimpleNamespace(
        id=tenant_id,
        whatsapp_instance="cobranca",
        dunning_rules={
            "approved_templates": {
                "vencimento_hoje": {
                    "name": "vencimento_hoje",
                    "language": "pt_BR",
                    "params": ["{nome}"],
                },
            },
        },
    )
    conv = SimpleNamespace(
        tenant_id=tenant_id, id=uuid4(), wa_jid="5511999999999@s.whatsapp.net", intent=None,
    )
    added: list[object] = []
    session = MagicMock()
    session.add.side_effect = added.append
    monkeypatch.setattr("app.dunning.service.get_or_create_conversation", lambda *_a, **_k: conv)
    monkeypatch.setattr("app.dunning.service.take_rate_slot", lambda *_a, **_k: True)
    monkeypatch.setattr("app.dunning.service.audit", lambda *_a, **_k: None)
    client = MagicMock()

    def send_template(*_args, **_kwargs):
        assert added[0].delivery_status == PENDENTE
        raise httpx.TimeoutException("timeout")

    client.send_template.side_effect = send_template
    step = Step("D0", 0, ("whatsapp",), "vencimento_hoje")
    _send_step(session, tenant, invoice, debtor, step, ("whatsapp",), client)
    messages = [item for item in added if isinstance(item, Message)]
    events = [item for item in added if isinstance(item, DunningEvent)]
    assert messages[0].delivery_status == PENDENTE
    assert events[0].delivery_status == PENDENTE
    assert events[0].message_id is None


def test_media_is_stored_before_ocr(monkeypatch):
    order: list[str] = []

    class Client:
        def get_media(self, *_args, **_kwargs):
            order.append("download")
            return b"abc", "image/png"

    monkeypatch.setattr("app.receipts.tasks.EvolutionClient", Client)

    def stage(tenant_id, data, content_type):
        order.append("minio")
        assert data == b"abc"
        assert content_type == "image/png"
        return f"{tenant_id}/hash.png"

    monkeypatch.setattr("app.receipts.tasks.stage_receipt_bytes", stage)
    _data, content_type, key = load_receipt_bytes("tenant", "cobranca", {"id": "M1"}, None, None)
    assert (content_type, key) == ("image/png", "tenant/hash.png")
    assert order == ["download", "minio"]


def test_ocr_reads_the_copy_stored_on_arrival(monkeypatch):
    order: list[str] = []

    class Client:
        def get_media(self, *_args, **_kwargs):
            raise AssertionError("a Evolution não deve ser consultada de novo")

    monkeypatch.setattr("app.receipts.tasks.EvolutionClient", Client)
    monkeypatch.setattr(
        "app.receipts.tasks.storage.get_object",
        lambda key: order.append(f"minio:{key}") or b"abc",
    )

    def process(*_args, **kwargs):
        order.append("ocr")
        assert kwargs["file_key"].endswith("/hash.png")
        return SimpleNamespace(status="aguardando_banco", payment_id=None)

    monkeypatch.setattr("app.receipts.tasks.process_receipt", process)
    monkeypatch.setattr("app.receipts.tasks.claim_once", lambda _token: True)
    @contextmanager
    def fake_session(_tenant_id):
        session = MagicMock()
        session.get.return_value = SimpleNamespace(id=uuid4())
        yield session

    monkeypatch.setattr("app.receipts.tasks.tenant_session", fake_session)
    tenant_id = str(uuid4())
    status = process_whatsapp_receipt(
        tenant_id, "cobranca", {"id": "M1"}, "M1", media_key=f"{tenant_id}/hash.png",
    )
    assert status == "aguardando_banco"
    assert order[0].startswith("minio:") and order[0].endswith("/hash.png")
    assert order[1] == "ocr"


def test_arrival_caches_media_in_minio(monkeypatch):
    class Client:
        def get_media(self, *_args, **_kwargs):
            return b"abc", "application/pdf"

    monkeypatch.setattr("app.channels.tasks.EvolutionClient", Client)
    monkeypatch.setattr(
        "app.channels.tasks.stage_receipt_bytes",
        lambda tenant_id, data, content_type: f"{tenant_id}/hash.pdf",
    )
    msg = SimpleNamespace(has_media=True, instance="cobranca", key={"id": "M1"}, message_id="M1")
    assert cache_inbound_media("tenant", msg) == "tenant/hash.pdf"


def test_session_down_opens_an_exception_outside_the_debtor_queue(monkeypatch):
    opened: dict = {}

    def fake_open(_session, _tenant_id, type_, **kwargs):
        opened["type"] = type_
        opened["conversation_id"] = kwargs.get("conversation_id")
        opened["details"] = kwargs["details"]
        return SimpleNamespace()

    monkeypatch.setattr("app.channels.session.open_exception", fake_open)
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    assert alert_session_down(session, uuid4(), "cobranca", "close", 401)
    assert opened["type"] == ExceptionType.SESSAO_CANAL
    assert opened["conversation_id"] is None
    assert opened["details"]["motivo"] == "sessão do WhatsApp caída"
    assert session.add.call_count == 0

    session.scalars.return_value.all.return_value = [
        SimpleNamespace(details={"instance": "cobranca"}),
    ]
    assert alert_session_down(session, uuid4(), "cobranca", "close", 401) is False


def test_open_connection_is_not_an_alert():
    payload = EvolutionWebhook(
        event="connection.update", instance="cobranca", data={"state": "open"},
    )
    assert connection_state(payload) == "open"
    assert not session_is_down("open")
    closed = EvolutionWebhook(
        event="CONNECTION_UPDATE", instance="cobranca", data={"state": "close"},
    )
    assert session_is_down(connection_state(closed))


def test_known_inbound_does_not_start_another_turn():
    session = MagicMock()
    session.scalar.side_effect = ["already", None]
    known = SimpleNamespace(message_id="WA1")
    fresh = SimpleNamespace(message_id="WA2")
    assert fresh_inbound(session, [known, fresh]) == [fresh]


def test_second_receipt_does_not_run_ocr(monkeypatch):
    monkeypatch.setattr("app.receipts.tasks.claim_once", lambda _token: False)

    def explode(*_args, **_kwargs):
        raise AssertionError("OCR não roda de novo")

    monkeypatch.setattr("app.receipts.tasks.load_receipt_bytes", explode)
    assert process_whatsapp_receipt(str(uuid4()), "cobranca", {"id": "M1"}, "M1") == "duplicado"


def test_claim_turn_is_once_per_message(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        def delete(self, key):
            store.pop(key, None)

    monkeypatch.setattr("app.channels.turn.get_redis", lambda: FakeRedis())
    conversation_id = uuid4()
    assert claim_turn(conversation_id, "WA1")
    assert not claim_turn(conversation_id, "WA1")
    assert claim_turn(conversation_id, "WA2")
