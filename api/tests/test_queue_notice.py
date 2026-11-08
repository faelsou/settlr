"""SETL-17: aviso ao dono quando a fila humana ganha um item.

O texto leva o tipo e há quanto tempo está parado. O destino é o e-mail ou o
WhatsApp interno do dono. Devedor em opt-out não recebe esse aviso.
"""

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.agent.tools import request_human
from app.channels.queue_notice import notice_copy, notify_human_queue, queue_label
from app.dunning.service import process_invoice
from app.models import AuditLog, Tenant
from app.models.enums import ExceptionType, InvoiceStatus
from app.reconciliation.service import open_exception

OPENED = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
NOW = OPENED + timedelta(minutes=12)


def test_notice_says_the_type_and_how_long_it_has_been_waiting():
    label, _subject, body = notice_copy("contestacao", OPENED, NOW)
    assert label == "contestação"
    assert "Tipo: contestação." in body
    assert "há 12 minutos" in body

    fresh = notice_copy("aprovacao", NOW, NOW)[2]
    assert "aprovação fora da política" in fresh
    assert "há menos de 1 minuto" in fresh
    assert "título em D+30" in notice_copy("fila_humana", OPENED, NOW)[2]
    assert queue_label("sugestao_match") == "exceção"


def _tenant(**overrides) -> Tenant:
    data = {
        "id": uuid4(),
        "name": "Clínica",
        "slug": "clinica",
        "active": True,
        "timezone": "America/Sao_Paulo",
        "negotiation_policy": {},
        "dunning_rules": {},
        "reconciliation_rules": {},
        "allowed_hours": {},
        "whatsapp_instance": "clinica",
        "owner_email": "dono@clinica.test",
        "owner_phone": None,
    }
    data.update(overrides)
    return Tenant(**data)


def _session(tenant: Tenant, debtors: list) -> MagicMock:
    session = MagicMock()
    session.get.return_value = tenant
    session.scalars.return_value.all.return_value = debtors
    return session


def _debtor(**overrides) -> SimpleNamespace:
    data = {"opt_out": False, "email": "joao@devedor.test", "phone": "5511999999999", "phones": []}
    data.update(overrides)
    return SimpleNamespace(**data)


def test_new_item_emails_the_owner_with_type_and_age(monkeypatch):
    sent: dict = {}

    def fake_send(to: str, subject: str, body: str) -> None:
        sent.update(to=to, subject=subject, body=body)

    monkeypatch.setattr("app.channels.queue_notice.send_email", fake_send)
    monkeypatch.setattr(
        "app.channels.outbound.send_to_debtor",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("aviso foi para o devedor")),
    )
    tenant = _tenant()
    debtor = _debtor()
    result = notify_human_queue(
        _session(tenant, [debtor]),
        tenant_id=tenant.id,
        kind="contestacao",
        entity="exception",
        entity_id=uuid4(),
        opened_at=OPENED,
        now=NOW,
    )

    assert result == "email"
    assert sent["to"] == "dono@clinica.test"
    assert sent["to"] != debtor.email
    assert "Tipo: contestação." in sent["body"]
    assert "há 12 minutos" in sent["body"]
    assert "contestação" in sent["subject"]


def test_internal_whatsapp_stays_off_the_debtor_thread(monkeypatch):
    sent: dict = {}

    class Client:
        def send_text(self, instance: str, number: str, text: str) -> str:
            sent.update(instance=instance, number=number, text=text)
            return "WA1"

    monkeypatch.setattr("app.channels.queue_notice.EvolutionClient", Client)
    monkeypatch.setattr(
        "app.channels.queue_notice.send_email",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("e-mail sem destino")),
    )
    monkeypatch.setattr(
        "app.channels.outbound.send_to_debtor",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("aviso foi para o devedor")),
    )
    tenant = _tenant(owner_email=None, owner_phone="11977776666")
    debtor = _debtor()
    result = notify_human_queue(
        _session(tenant, [debtor]),
        tenant_id=tenant.id,
        kind="pagamento_nao_identificado",
        entity="exception",
        entity_id=uuid4(),
        opened_at=OPENED,
        now=NOW,
    )

    assert result == "whatsapp"
    assert sent["instance"] == "clinica"
    assert sent["number"] == "11977776666"
    assert sent["number"] != debtor.phone
    assert "Tipo: exceção." in sent["text"]
    assert "há 12 minutos" in sent["text"]


def test_opted_out_debtor_does_not_receive_the_notice(monkeypatch):
    monkeypatch.setattr(
        "app.channels.queue_notice.send_email",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("e-mail do devedor")),
    )

    class Client:
        def send_text(self, *_a, **_k) -> str:
            raise AssertionError("WhatsApp do devedor")

    monkeypatch.setattr("app.channels.queue_notice.EvolutionClient", Client)
    tenant = _tenant(owner_email="joao@devedor.test", owner_phone="11999999999")
    debtor = _debtor(opt_out=True)
    session = _session(tenant, [debtor])
    result = notify_human_queue(
        session,
        tenant_id=tenant.id,
        kind="fila_humana",
        entity="exception",
        entity_id=uuid4(),
        opened_at=OPENED,
        now=NOW,
    )

    assert result == "recusado"
    audits = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], AuditLog)
    ]
    assert audits[-1].action == "aviso_fila_recusado"
    assert audits[-1].after["motivo"] == "opt_out"


def test_opt_out_does_not_block_a_different_owner(monkeypatch):
    sent: dict = {}
    monkeypatch.setattr(
        "app.channels.queue_notice.send_email",
        lambda to, subject, body: sent.update(to=to, body=body),
    )
    tenant = _tenant()
    debtor = _debtor(opt_out=True)
    result = notify_human_queue(
        _session(tenant, [debtor]),
        tenant_id=tenant.id,
        kind="aprovacao",
        entity="approval",
        entity_id=uuid4(),
        opened_at=OPENED,
        now=NOW,
    )

    assert result == "email"
    assert sent["to"] == "dono@clinica.test"
    assert "aprovação fora da política" in sent["body"]
    assert "há 12 minutos" in sent["body"]


def test_opted_out_email_falls_through_to_the_owner_whatsapp(monkeypatch):
    sent: dict = {}

    class Client:
        def send_text(self, instance: str, number: str, text: str) -> str:
            sent.update(number=number, text=text)
            return "WA1"

    monkeypatch.setattr("app.channels.queue_notice.EvolutionClient", Client)
    monkeypatch.setattr(
        "app.channels.queue_notice.send_email",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("e-mail do devedor")),
    )
    tenant = _tenant(owner_email="joao@devedor.test", owner_phone="11977776666")
    debtor = _debtor(opt_out=True, phone="5511888887777")
    result = notify_human_queue(
        _session(tenant, [debtor]),
        tenant_id=tenant.id,
        kind="contestacao",
        entity="exception",
        entity_id=uuid4(),
        opened_at=OPENED,
        now=NOW,
    )

    assert result == "whatsapp"
    assert sent["number"] == "11977776666"
    assert debtor.phone not in sent["text"]


def test_email_failure_falls_back_to_internal_whatsapp(monkeypatch):
    sent: dict = {}

    class Client:
        def send_text(self, _instance: str, number: str, text: str) -> str:
            sent.update(number=number, text=text)
            return "WA1"

    monkeypatch.setattr("app.channels.queue_notice.EvolutionClient", Client)
    monkeypatch.setattr(
        "app.channels.queue_notice.send_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("SMTP não configurado")),
    )
    tenant = _tenant(owner_phone="11977776666")
    debtor = _debtor(opt_out=True)
    result = notify_human_queue(
        _session(tenant, [debtor]),
        tenant_id=tenant.id,
        kind="excecao",
        entity="exception",
        entity_id=uuid4(),
        opened_at=OPENED,
        now=NOW,
    )

    assert result == "whatsapp"
    assert sent["number"] == "11977776666"
    assert sent["number"] != debtor.phone
    assert "há 12 minutos" in sent["text"]


def test_opening_an_exception_triggers_the_notice(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        "app.reconciliation.service.notify_human_queue",
        lambda _session, **kwargs: seen.update(kwargs) or "email",
    )
    exc = open_exception(
        MagicMock(), uuid4(), ExceptionType.FILA_HUMANA,
        invoice_id=uuid4(), details={"reason": "fim da régua (D+30)"},
    )
    assert seen["kind"] == "fila_humana"
    assert seen["entity"] == "exception"
    assert seen["entity_id"] == exc.id


def test_policy_approval_triggers_the_notice(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        "app.agent.tools.notify_human_queue",
        lambda _session, **kwargs: seen.update(kwargs) or "email",
    )

    @contextmanager
    def fake_session(_tenant_id):
        session = MagicMock()
        session.get.return_value = SimpleNamespace(state="agente")
        yield session

    monkeypatch.setattr("app.agent.tools.tenant_session", fake_session)
    tenant_id = uuid4()
    approval_id = request_human.invoke({
        "tenant_id": tenant_id,
        "conversation_id": uuid4(),
        "thread_id": "fora-da-politica",
        "reason": "Pedido de 8 parcelas acima do máximo da política (6).",
        "payload": {"pedido": "8x"},
    })

    assert seen["kind"] == "aprovacao"
    assert seen["tenant_id"] == tenant_id
    assert str(seen["entity_id"]) == approval_id


class _Sessao:
    def __init__(self, invoice: SimpleNamespace, debtor: SimpleNamespace) -> None:
        self.invoice = invoice
        self.debtor = debtor

    def scalars(self, *_args: object, **_kwargs: object) -> "_Sessao":
        return self

    def one(self) -> SimpleNamespace:
        return self.invoice

    def get(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        return self.debtor

    def execute(self, *_args: object, **_kwargs: object) -> "_Sessao":
        return self

    def tuples(self) -> list:
        return []

    def scalar(self, *_args: object, **_kwargs: object) -> None:
        return None

    def add(self, *_args: object, **_kwargs: object) -> None:
        return None

    def flush(self) -> None:
        return None


def test_d30_from_open_invoice_enters_the_human_queue(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        "app.reconciliation.service.notify_human_queue",
        lambda _session, **kwargs: seen.update(kwargs) or "email",
    )
    invoice = SimpleNamespace(
        id=uuid4(),
        debtor_id=uuid4(),
        status=InvoiceStatus.ABERTO,
        due_date=date(2026, 9, 20),
        pix_copy_paste="00020126PIX",
        digitable_line=None,
    )
    tenant = SimpleNamespace(id=uuid4(), dunning_rules=None)
    outcome = process_invoice(
        _Sessao(invoice, SimpleNamespace(opt_out=False)),
        tenant,
        invoice.id,
        date(2026, 10, 20),
    )

    assert outcome.action == "handoff"
    assert invoice.status == InvoiceStatus.FILA_HUMANA
    assert seen["kind"] == "fila_humana"
