"""SETL-21: extrato do emissor e Open Finance, sem arquivo."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.ingest.issuers import AsaasAdapter
from app.reconciliation.feeds import open_finance_config, pull_tenant
from app.reconciliation.open_finance import OpenFinanceClient

SINCE = date(2026, 11, 1)
TODAY = date(2026, 11, 8)
E2E = "E18236120202610121230ABCDEFGHIJK"


def _asaas_client(pages: dict[str, list[dict]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status = request.url.params.get("status")
        return httpx.Response(200, json={"hasMore": False, "data": pages.get(status, [])})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3")


def test_extrato_do_emissor_e_o_webhook_apontam_o_mesmo_lancamento() -> None:
    payment = {
        "id": "pay_auto",
        "value": 80,
        "status": "RECEIVED",
        "paymentDate": "2026-11-07",
        "endToEndIdentifier": E2E,
    }
    client = _asaas_client({"RECEIVED": [payment]})
    adapter = AsaasAdapter({"api_key": "k"}, client=client)
    webhook = adapter.parse({"event": "PAYMENT_RECEIVED", "payment": payment})
    rows = adapter.statement(SINCE)
    assert webhook is not None
    assert rows[0].source_id == webhook.source_id == "asaas:pay_auto"
    assert rows[0].txid == "pay_auto"
    assert rows[0].e2e_id == E2E
    assert rows[0].raw["source"] == "extrato_emissor"


def test_extrato_do_emissor_ignora_cobranca_sem_data() -> None:
    pages = {
        "CONFIRMED": [{"id": "pay_sem_data", "value": 10, "status": "CONFIRMED"}],
        "RECEIVED": [{
            "id": "pay_zero",
            "value": 0,
            "status": "RECEIVED",
            "paymentDate": "2026-11-07",
        }],
    }
    adapter = AsaasAdapter({"api_key": "k"}, client=_asaas_client(pages))
    assert adapter.statement(SINCE) == []


def test_open_finance_traz_so_credito_efetivado() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["path"] = request.url.path
        if request.url.params.get("page") != "1":
            return httpx.Response(200, json={"data": [], "meta": {"totalPages": 1}})
        return httpx.Response(
            200,
            json={
                "meta": {"totalPages": 1},
                "data": [
                    {
                        "transactionId": E2E,
                        "completedAuthorisedPaymentType": "TRANSACAO_EFETIVADA",
                        "creditDebitType": "CREDITO",
                        "type": "PIX",
                        "transactionAmount": {"amount": "40.00", "currency": "BRL"},
                        "transactionDateTime": "2026-11-07T15:00:00Z",
                        "partieCnpjCpf": "123.456.789-01",
                        "partieCompeCode": "001",
                    },
                    {
                        "transactionId": "debito-1",
                        "completedAuthorisedPaymentType": "TRANSACAO_EFETIVADA",
                        "creditDebitType": "DEBITO",
                        "transactionAmount": {"amount": "10.00", "currency": "BRL"},
                        "transactionDateTime": "2026-11-07T15:00:00Z",
                    },
                    {
                        "transactionId": "futuro-1",
                        "completedAuthorisedPaymentType": "LANCAMENTO_FUTURO",
                        "creditDebitType": "CREDITO",
                        "transactionAmount": {"amount": "10.00", "currency": "BRL"},
                        "transactionDateTime": "2026-11-09T15:00:00Z",
                    },
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://banco.test/v2")
    rows = OpenFinanceClient(
        {"base_url": "https://banco.test/v2", "token": "segredo", "account_id": "acc-1"},
        client=client,
    ).statement(SINCE, TODAY)
    assert seen["auth"] == "Bearer segredo"
    assert seen["path"].endswith("/accounts/acc-1/transactions")
    assert len(rows) == 1
    assert rows[0].e2e_id == E2E
    assert rows[0].source_id == f"of:{E2E}"
    assert rows[0].payer_doc == "12345678901"
    assert rows[0].payer_bank == "001"
    assert "segredo" not in str(rows[0].raw)


def test_open_finance_incompleto_nao_liga_o_feed() -> None:
    tenant = SimpleNamespace(bank_feed={"open_finance": {"base_url": "https://banco.test"}})
    assert open_finance_config(tenant) is None


def test_as_duas_fontes_fora_do_ar_sobem_para_o_retry() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "indisponivel"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3")
    tenant = SimpleNamespace(
        id=uuid4(),
        issuer_provider="asaas",
        issuer_config={"api_key": "k"},
        bank_feed={
            "open_finance": {
                "base_url": "https://banco.test/v2",
                "token": "segredo",
                "account_id": "acc-1",
            }
        },
    )
    with pytest.raises(httpx.HTTPStatusError):
        pull_tenant(
            None,
            tenant,
            since=SINCE,
            today=TODAY,
            issuer_client=client,
            open_finance_client=client,
        )


def test_o_beat_busca_o_extrato() -> None:
    from app.workers.celery_app import celery_app

    job = celery_app.conf.beat_schedule["pull-statements"]
    assert job["task"] == "app.reconciliation.tasks.pull_statements"
