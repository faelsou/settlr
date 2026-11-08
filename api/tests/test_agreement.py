"""SETL-12: acordo aceito nasce com PIX ou boleto, e pedido fora da política não vira condição."""

import json
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import AgentDeps, build_graph
from app.agent.intent import ChoiceResult
from app.agent.tools import create_agreement
from app.ingest.issuers import AsaasAdapter, IssuedCharge
from app.models import Agreement, Invoice
from app.models.enums import InvoiceStatus

TODAY = date(2026, 11, 7)
PIX = "00020126PIX"
BOLETO = "34191790010104351004791020150008184660000026000"


def test_asaas_issues_pix_for_an_existing_customer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/customers") and request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "cus_1"}]})
        if request.url.path.endswith("/payments") and request.method == "POST":
            seen["payment"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "pay_1", "invoiceUrl": "https://asaas/pay_1"})
        if request.url.path.endswith("/pixQrCode"):
            return httpx.Response(200, json={"payload": PIX})
        return httpx.Response(404, json={"error": request.url.path})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3",
    )
    charge = AsaasAdapter({"api_key": "k", "billing_type": "cartao"}, client=client).issue(
        name="Maria", document="12345678901", phone="11999999999", email=None,
        amount=Decimal("200.00"), due_date=date(2026, 11, 10), description="Acordo parcela 1/2",
    )
    assert seen["payment"]["billingType"] == "PIX"
    assert seen["payment"]["customer"] == "cus_1"
    assert seen["payment"]["value"] == 200.0
    assert charge.external_id == "pay_1"
    assert charge.pix_copy_paste == PIX
    assert charge.digitable_line is None
    assert charge.payment_url == "https://asaas/pay_1"


def test_asaas_issues_boleto_and_strips_the_line():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/customers") and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        if request.url.path.endswith("/customers") and request.method == "POST":
            body = json.loads(request.content)
            assert body["cpfCnpj"] == "12345678901"
            assert "email" not in body
            return httpx.Response(200, json={"id": "cus_2"})
        if request.url.path.endswith("/payments") and request.method == "POST":
            assert json.loads(request.content)["billingType"] == "BOLETO"
            return httpx.Response(200, json={"id": "pay_2", "bankSlipUrl": "https://asaas/b"})
        if request.url.path.endswith("/identificationField"):
            return httpx.Response(200, json={
                "identificationField": "34191.79001 01043.510047 91020.150008 1 84660000026000",
            })
        raise AssertionError(request.method + " " + request.url.path)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3",
    )
    charge = AsaasAdapter({"billing_type": "BOLETO"}, client=client).issue(
        name="Maria", document="12345678901", phone=None, email=None,
        amount=Decimal("800.00"), due_date=date(2026, 12, 10), description="Acordo parcela 2/2",
    )
    assert charge.pix_copy_paste is None
    assert charge.digitable_line == BOLETO
    assert charge.payment_url == "https://asaas/b"


def test_asaas_cancels_the_charge_when_there_is_no_payable_code():
    deleted = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/customers") and request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "cus_1"}]})
        if request.url.path.endswith("/payments") and request.method == "POST":
            return httpx.Response(200, json={"id": "pay_x"})
        if request.url.path.endswith("/pixQrCode"):
            return httpx.Response(404, json={"error": "sem pix"})
        if request.url.path.endswith("/identificationField"):
            return httpx.Response(200, json={"identificationField": ""})
        if request.method == "DELETE":
            deleted.append(request.url.path)
            return httpx.Response(200, json={})
        raise AssertionError(request.url.path)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3",
    )
    with pytest.raises(ValueError, match="PIX nem boleto"):
        AsaasAdapter({}, client=client).issue(
            name="Maria", document="12345678901", phone=None, email=None,
            amount=Decimal("10.00"), due_date=TODAY, description="parcela",
        )
    assert deleted == ["/v3/payments/pay_x"]


def test_asaas_cancels_when_both_instrument_calls_fail():
    deleted = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/customers") and request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "cus_1"}]})
        if request.url.path.endswith("/payments") and request.method == "POST":
            return httpx.Response(200, json={"id": "pay_y"})
        if request.method == "DELETE":
            deleted.append(request.url.path)
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": "fora"})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3",
    )
    with pytest.raises(httpx.HTTPStatusError):
        AsaasAdapter({}, client=client).issue(
            name="Maria", document="12345678901", phone=None, email=None,
            amount=Decimal("10.00"), due_date=TODAY, description="parcela",
        )
    assert deleted == ["/v3/payments/pay_y"]


class _Issuer:
    def __init__(self, fail_on: int | None = None):
        self.fail_on = fail_on
        self.cancelled: list[str] = []
        self.n = 0

    def issue(self, **_kwargs) -> IssuedCharge:
        self.n += 1
        if self.fail_on == self.n:
            raise ValueError("emissor não devolveu PIX nem boleto")
        return IssuedCharge(
            external_id=f"pay_{self.n}",
            txid=f"pay_{self.n}",
            pix_copy_paste=f"{PIX}{self.n}",
            digitable_line=None,
            payment_url=f"https://asaas/pay_{self.n}",
        )

    def cancel(self, payment_id: str) -> None:
        self.cancelled.append(payment_id)


def _world(monkeypatch, issuer: _Issuer | None):
    tenant_id, debtor_id = uuid4(), uuid4()
    source = Invoice(
        id=uuid4(),
        tenant_id=tenant_id,
        debtor_id=debtor_id,
        external_id="NF1",
        description="mensalidade",
        amount=Decimal("1000.00"),
        amount_paid=Decimal("0"),
        due_date=date(2026, 10, 1),
        status=InvoiceStatus.EM_COBRANCA,
    )
    tenant = SimpleNamespace(
        issuer_provider="asaas" if issuer is not None else None,
        issuer_config={},
        negotiation_policy=None,
    )
    debtor = SimpleNamespace(
        name="Maria", document="12345678901", phone="11999999999", email=None,
    )
    added: list[object] = []
    session = MagicMock()
    session.scalars.return_value.all.return_value = [source]
    session.scalars.return_value.first.return_value = None
    session.get.side_effect = lambda model, _id: (
        tenant if model.__name__ == "Tenant" else debtor
    )
    session.add.side_effect = added.append

    def flush():
        for obj in added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    session.flush.side_effect = flush

    @contextmanager
    def fake_session(_tenant_id):
        yield session

    monkeypatch.setattr("app.agent.tools.tenant_session", fake_session)
    monkeypatch.setattr("app.agent.tools.get_adapter", lambda *_a, **_k: issuer)
    return tenant_id, debtor_id, source, added


def _accept(tenant_id, debtor_id, source, option_id="parcelado_2x"):
    return create_agreement.invoke({
        "tenant_id": tenant_id,
        "debtor_id": debtor_id,
        "invoice_ids": [source.id],
        "option_id": option_id,
        "today": TODAY,
    })


def test_accepted_agreement_stores_pix_and_links_the_origin(monkeypatch):
    issuer = _Issuer()
    tenant_id, debtor_id, source, added = _world(monkeypatch, issuer)
    result = _accept(tenant_id, debtor_id, source)

    parcels = [obj for obj in added if isinstance(obj, Invoice)]
    agreement = next(obj for obj in added if isinstance(obj, Agreement))
    assert source.status == InvoiceStatus.RENEGOCIADO
    assert len(parcels) == 2
    assert [p.pix_copy_paste for p in parcels] == [f"{PIX}1", f"{PIX}2"]
    assert all(p.parent_id == source.id and p.agreement_id == agreement.id for p in parcels)
    assert [p.external_id for p in parcels] == ["pay_1", "pay_2"]
    assert issuer.cancelled == []
    assert "00020126PIX1" in result["invoices"][0]["pix_copy_paste"]


def test_missing_issuer_does_not_renegotiate(monkeypatch):
    tenant_id, debtor_id, source, added = _world(monkeypatch, None)
    with pytest.raises(ValueError, match="sem emissor"):
        _accept(tenant_id, debtor_id, source)
    assert source.status == InvoiceStatus.EM_COBRANCA
    assert added == []


def test_option_outside_policy_does_not_issue_a_charge(monkeypatch):
    issuer = _Issuer()
    tenant_id, debtor_id, source, added = _world(monkeypatch, issuer)
    with pytest.raises(ValueError, match="fora da política"):
        _accept(tenant_id, debtor_id, source, option_id="parcelado_8x")
    assert issuer.n == 0
    assert source.status == InvoiceStatus.EM_COBRANCA
    assert added == []


def test_failed_second_charge_cancels_the_first_and_keeps_the_origin(monkeypatch):
    issuer = _Issuer(fail_on=2)
    tenant_id, debtor_id, source, added = _world(monkeypatch, issuer)
    with pytest.raises(ValueError, match="PIX nem boleto"):
        _accept(tenant_id, debtor_id, source)
    assert issuer.cancelled == ["pay_1"]
    assert source.status == InvoiceStatus.EM_COBRANCA
    assert not any(isinstance(obj, Invoice) for obj in added)


def test_webhook_row_is_reused_as_the_installment(monkeypatch):
    issuer = _Issuer()
    tenant_id, debtor_id, source, added = _world(monkeypatch, issuer)
    existing = Invoice(
        id=uuid4(),
        tenant_id=tenant_id,
        debtor_id=debtor_id,
        external_id="pay_1",
        description=None,
        amount=Decimal("200.00"),
        amount_paid=Decimal("0"),
        due_date=date(2026, 11, 10),
        status=InvoiceStatus.ABERTO,
    )

    @contextmanager
    def fake_session(_tenant_id):
        session = MagicMock()
        session.scalars.return_value.all.return_value = [source]
        session.scalars.return_value.first.side_effect = [existing, None]
        tenant = SimpleNamespace(issuer_provider="asaas", issuer_config={}, negotiation_policy=None)
        debtor = SimpleNamespace(name="Maria", document="12345678901", phone=None, email=None)
        session.get.side_effect = lambda model, _id: (
            tenant if model.__name__ == "Tenant" else debtor
        )
        session.add.side_effect = added.append

        def flush():
            for obj in added:
                if getattr(obj, "id", None) is None:
                    obj.id = uuid4()

        session.flush.side_effect = flush
        yield session

    monkeypatch.setattr("app.agent.tools.tenant_session", fake_session)
    added.clear()
    _accept(tenant_id, debtor_id, source)
    assert existing.status == InvoiceStatus.EM_COBRANCA
    assert existing.parent_id == source.id
    assert existing.pix_copy_paste == f"{PIX}1"
    assert existing.agreement_id is not None
    assert [obj.external_id for obj in added if isinstance(obj, Invoice)] == ["pay_2"]


def _graph(create, human, interpret):
    invoices = [{
        "id": str(uuid4()),
        "description": "mensalidade",
        "amount_open": "1000.00",
        "due_date": "2026-10-01",
    }]
    return build_graph(
        AgentDeps(
            get_invoices=lambda _t, _d: invoices,
            get_policy=lambda _t: {},
            build_options=lambda *_a, **_k: [],
            create_agreement=create,
            request_human=human,
            interpret_choice=interpret,
        ),
        checkpointer=MemorySaver(),
    )


def _state(text: str) -> dict:
    return {
        "tenant_id": str(uuid4()),
        "tenant_name": "Clínica",
        "conversation_id": str(uuid4()),
        "debtor_id": str(uuid4()),
        "debtor_document": "12345678901",
        "thread_id": "thr",
        "today": TODAY.isoformat(),
        "text": text,
        "intent": "parcelar_desconto",
        "identity_verified": True,
        "identity_verified_on": TODAY.isoformat(),
        "awaiting_choice": True,
        "options": [{"id": "parcelado_2x", "label": "Entrada + 1x"}],
        "replies": [],
    }


def test_debtor_receives_the_payment_code():
    calls = {"create": 0, "human": 0}

    def create(**_kwargs):
        calls["create"] += 1
        return {
            "label": "Entrada + 1x",
            "invoices": [{
                "description": "Acordo parcela 1/2",
                "amount_open": "200.00",
                "due_date": "2026-11-10",
                "pix_copy_paste": PIX,
                "digitable_line": None,
            }],
        }

    def human(**_kwargs):
        calls["human"] += 1
        return "approval"

    graph = _graph(create, human, lambda *_a, **_k: ChoiceResult(decision="outro"))
    result = graph.invoke(_state("1"), {"configurable": {"thread_id": "ok"}})
    reply = "\n".join(result["replies"])
    assert calls == {"create": 1, "human": 0}
    assert result["outcome"] == "acordo"
    assert PIX in reply
    assert "Código:" in reply


def test_request_outside_policy_goes_to_approval_without_a_new_condition():
    calls = {"create": 0, "reasons": []}

    def create(**_kwargs):
        calls["create"] += 1
        raise AssertionError("fora da política não gera acordo")

    def human(**kwargs):
        calls["reasons"].append(kwargs["reason"])
        assert kwargs["payload"]["options"] == [{"id": "parcelado_2x", "label": "Entrada + 1x"}]
        return "approval"

    graph = _graph(
        create,
        human,
        lambda *_a, **_k: ChoiceResult(decision="fora_da_politica"),
    )
    result = graph.invoke(_state("quero 8 vezes"), {"configurable": {"thread_id": "fora"}})
    assert calls["create"] == 0
    assert calls["reasons"] == ["Pedido do devedor: quero 8 vezes"]
    assert result["outcome"] == "aguardando_aprovacao"
    assert "8x" not in "\n".join(result["replies"])


def test_issuer_failure_asks_for_approval_and_sends_no_code():
    def create(**_kwargs):
        raise ValueError("tenant sem emissor")

    reasons = []

    def human(**kwargs):
        reasons.append(kwargs["reason"])
        return "approval"

    graph = _graph(
        create,
        human,
        lambda *_a, **_k: ChoiceResult(decision="aceita", option_id="parcelado_2x"),
    )
    result = graph.invoke(_state("1"), {"configurable": {"thread_id": "falha"}})
    reply = "\n".join(result["replies"])
    assert reasons == ["Acordo não registrado: tenant sem emissor"]
    assert result["outcome"] == "aguardando_aprovacao"
    assert PIX not in reply
    assert "Código:" not in reply
