"""SETL-18: baixa no emissor do piloto e arquivo do contador."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.ingest.issuers import AsaasAdapter
from app.ingest.settlement import charge_id_for, paid_by_issuer
from app.reconciliation.export import AccountantRow, render_accountant_csv


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.asaas.com/v3")


def test_asaas_marca_a_cobranca_como_recebida_sem_avisar_o_devedor():
    visto = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/payments/pay_piloto/receiveInCash")
        visto["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "pay_piloto", "status": "RECEIVED"})

    resultado = AsaasAdapter({"api_key": "k"}, client=_client(handler)).mark_paid(
        "pay_piloto", date(2026, 11, 7), Decimal("100.00"),
    )
    assert resultado == "paid"
    assert visto["body"] == {
        "paymentDate": "2026-11-07",
        "value": 100.0,
        "notifyCustomer": False,
    }


def test_asaas_trata_cobranca_ja_recebida_como_feita():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"description": "Cobrança já recebida."}]})

    resultado = AsaasAdapter({}, client=_client(handler)).mark_paid(
        "pay_piloto", date(2026, 11, 7), Decimal("100.00"),
    )
    assert resultado == "already_paid"


def test_asaas_propaga_erro_que_nao_e_cobranca_quitada():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"description": "valor inválido"}]})

    with pytest.raises(httpx.HTTPStatusError):
        AsaasAdapter({}, client=_client(handler)).mark_paid(
            "pay_piloto", date(2026, 11, 7), Decimal("100.00"),
        )


def test_cada_emissor_so_reconhece_a_propria_cobranca():
    codigo = "183e982a-34e5-4bc0-9643-def5432abcde"
    assert charge_id_for("asaas", "pay_piloto", None) == "pay_piloto"
    assert charge_id_for("asaas", "NF-1", "pay_txid") == "pay_txid"
    assert charge_id_for("asaas", "NF-1", "txid") is None
    assert charge_id_for("asaas", codigo, None) is None
    assert charge_id_for(None, "pay_piloto", None) is None
    assert charge_id_for("inter", "pay_piloto", None) is None
    assert charge_id_for("inter", codigo, "txid") == codigo
    assert charge_id_for("efi", codigo, None) is None


def test_pagamento_nascido_no_emissor_ja_esta_quitado_la():
    assert paid_by_issuer({"provider": "asaas"}, "asaas") is True
    assert paid_by_issuer({"bank": {"provider": "asaas"}}, "asaas") is True
    assert paid_by_issuer({"provider": "banco"}, "asaas") is False
    assert paid_by_issuer(None, "asaas") is False


def test_csv_do_contador_tem_as_quatro_colunas():
    corpo = render_accountant_csv([
        AccountantRow("NF-1", Decimal("100.5"), date(2026, 11, 7), "E2E-PIX-001"),
    ]).decode("utf-8-sig")
    assert corpo.splitlines() == [
        "titulo;valor;data;identificador_bancario",
        "NF-1;100.50;2026-11-07;E2E-PIX-001",
    ]
