"""SETL-22: segundo emissor é o Inter, no formato real do callback de cobrança."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.ingest.issuers import AsaasAdapter, InterAdapter, get_adapter
from app.ingest.schemas import InvoiceIn
from app.reconciliation.service import BankPaymentIn

CODIGO = "183e982a-34e5-4bc0-9643-def5432abcde"
TXID = "txidinterprova01"
PIX = "00020126PIXINTER"
LINHA = "07790001161234567890123456789012345678901234567"
E2E = "E00416968202611071422ABCDEFGHIJK"
CONFIG = {
    "access_token": "tok",
    "conta_corrente": "1234567",
    "endereco": "Rua A",
    "cidade": "Sao Paulo",
    "uf": "sp",
    "cep": "01001-000",
}


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://cdpj.partners.bancointer.com.br",
    )


def _callback_aberto() -> list[dict]:
    return [{
        "codigoSolicitacao": CODIGO,
        "seuNumero": "mensalidade",
        "situacao": "A_RECEBER",
        "dataHoraSituacao": "2026-11-01T10:00:00.00Z",
        "valorNominal": 150.0,
        "nossoNumero": "000123",
        "linhaDigitavel": LINHA,
        "txid": TXID,
        "pixCopiaECola": PIX,
    }]


def _callback_recebido() -> list[dict]:
    return [{
        "codigoSolicitacao": CODIGO,
        "seuNumero": "mensalidade",
        "situacao": "RECEBIDO",
        "dataHoraSituacao": "2026-11-07T14:22:00.00Z",
        "valorNominal": 150.0,
        "valorTotalRecebido": "150.00",
        "origemRecebimento": "PIX",
        "txid": TXID,
        "endToEndId": E2E,
    }]


def _detalhe() -> dict:
    return {
        "cobranca": {
            "codigoSolicitacao": CODIGO,
            "dataVencimento": "2026-11-15",
            "valorNominal": 150.0,
            "situacao": "A_RECEBER",
            "pagador": {
                "nome": "Maria Silva",
                "cpfCnpj": "123.456.789-01",
                "email": "maria@clinica.test",
                "ddd": "11",
                "telefone": "988887777",
            },
        },
        "boleto": {"linhaDigitavel": LINHA},
        "pix": {"txid": TXID, "pixCopiaECola": PIX},
    }


def test_emissor_desconhecido_nao_cai_no_asaas():
    with pytest.raises(NotImplementedError, match="emissor sem adaptador: efi"):
        get_adapter("efi", {"api_key": "k"})
    with pytest.raises(NotImplementedError, match="emissor sem adaptador: None"):
        get_adapter(None, {})
    adapter = get_adapter("inter", CONFIG)
    assert isinstance(adapter, InterAdapter)
    assert not isinstance(adapter, AsaasAdapter)


def test_callback_do_inter_e_uma_lista_e_nao_e_lido_como_asaas():
    vistos: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request.url.path)
        assert request.headers["authorization"] == "Bearer tok"
        assert request.headers["x-conta-corrente"] == "1234567"
        return httpx.Response(200, json=_detalhe())

    eventos = InterAdapter(CONFIG, client=_client(handler)).events(_callback_aberto())
    assert vistos == [f"/cobranca/v3/cobrancas/{CODIGO}"]
    assert len(eventos) == 1
    titulo = eventos[0]
    assert isinstance(titulo, InvoiceIn)
    assert titulo.external_id == CODIGO
    assert titulo.debtor_name == "Maria Silva"
    assert titulo.debtor_document == "12345678901"
    assert titulo.debtor_phone == "5511988887777"
    assert titulo.amount == Decimal("150.0")
    assert titulo.due_date == date(2026, 11, 15)
    assert titulo.txid == TXID
    assert titulo.pix_copy_paste == PIX
    assert titulo.digitable_line == LINHA

    pagamento = InterAdapter(CONFIG).events(_callback_recebido())[0]
    assert isinstance(pagamento, BankPaymentIn)
    assert pagamento.amount == Decimal("150.00")
    assert pagamento.txid == TXID
    assert pagamento.e2e_id == E2E
    assert pagamento.source_id == f"inter:{CODIGO}"
    assert pagamento.raw["provider"] == "inter"
    assert pagamento.paid_at.isoformat() == "2026-11-07T14:22:00+00:00"

    assert InterAdapter(CONFIG).events(
        {"event": "PAYMENT_RECEIVED", "payment": {"id": "pay_1"}},
    ) == []


def test_asaas_recusa_a_lista_do_inter():
    with pytest.raises(ValueError, match="webhook do Asaas não é um objeto"):
        AsaasAdapter({}).events(_callback_recebido())


def test_extrato_do_inter_filtra_pagamento():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["filtrarDataPor"] == "PAGAMENTO"
        assert request.url.params["dataInicial"] == "2026-11-01"
        status = request.url.params["situacao"]
        if status == "MARCADO_RECEBIDO":
            return httpx.Response(200, json={"ultimaPagina": True, "cobrancas": []})
        return httpx.Response(200, json={
            "ultimaPagina": True,
            "cobrancas": [{
                "codigoSolicitacao": CODIGO,
                "situacao": "RECEBIDO",
                "dataSituacao": "2026-11-07",
                "valorTotalRecebido": "150.00",
                "pix": {"txid": TXID},
            }],
        })

    rows = InterAdapter(CONFIG, client=_client(handler)).statement(date(2026, 11, 1))
    assert len(rows) == 1
    assert rows[0].source_id == f"inter:{CODIGO}"
    assert rows[0].raw["source"] == "extrato_emissor"
    assert rows[0].paid_at.date() == date(2026, 11, 7)


def test_inter_emite_pix_e_cancela_se_nao_houver_codigo():
    corpos: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/cobranca/v3/cobrancas":
            body = json.loads(request.content)
            corpos.append(body)
            return httpx.Response(200, json={"codigoSolicitacao": CODIGO})
        if request.method == "GET":
            return httpx.Response(200, json=_detalhe())
        raise AssertionError(request.method + " " + request.url.path)

    charge = InterAdapter(CONFIG, client=_client(handler)).issue(
        name="Maria",
        document="12345678901",
        phone="5511988887777",
        email="maria@clinica.test",
        amount=Decimal("150.00"),
        due_date=date(2026, 11, 15),
        description="Acordo parcela 1/2",
    )
    assert charge.external_id == CODIGO
    assert charge.pix_copy_paste == PIX
    assert charge.digitable_line == LINHA
    pagador = corpos[0]["pagador"]
    assert pagador["tipoPessoa"] == "FISICA"
    assert pagador["cep"] == "01001000"
    assert pagador["uf"] == "SP"
    assert pagador["ddd"] == "11"
    assert pagador["telefone"] == "988887777"
    assert corpos[0]["formasRecebimento"] == ["BOLETO", "PIX"]
    assert len(corpos[0]["seuNumero"]) == 15

    cancelados: list[str] = []

    def sem_codigo(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/cancelar"):
            cancelados.append(request.url.path)
            return httpx.Response(202, json={})
        if request.method == "POST":
            return httpx.Response(200, json={"codigoSolicitacao": CODIGO})
        return httpx.Response(200, json={"cobranca": {"situacao": "A_RECEBER"}})

    with pytest.raises(ValueError, match="PIX nem boleto"):
        InterAdapter(CONFIG, client=_client(sem_codigo)).issue(
            name="Maria",
            document="12345678901",
            phone=None,
            email=None,
            amount=Decimal("10.00"),
            due_date=date(2026, 11, 15),
            description="parcela",
        )
    assert cancelados == [f"/cobranca/v3/cobrancas/{CODIGO}/cancelar"]


def test_inter_marca_paga_e_trata_cobranca_ja_recebida():
    visto = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["path"] = request.url.path
        visto["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "PROCESSANDO"})

    resultado = InterAdapter(CONFIG, client=_client(handler)).mark_paid(
        CODIGO, date(2026, 11, 7), Decimal("150.00"),
    )
    assert resultado == "paid"
    assert visto["path"] == f"/cobranca/v3/cobrancas/{CODIGO}/pagar"
    assert visto["body"] == {"pagarCom": "PIX"}

    def ja_recebida(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"title": "Cobrança já recebida."})

    de_novo = InterAdapter(CONFIG, client=_client(ja_recebida)).mark_paid(
        CODIGO, date(2026, 11, 7), Decimal("150.00"),
    )
    assert de_novo == "already_paid"


def test_inter_busca_token_antes_de_chamar_a_cobranca():
    vistos: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request.headers["authorization"])
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "novo"})
        return httpx.Response(202, json={})

    config = {"client_id": "id", "client_secret": "sec", "billing_type": "BOLETO"}
    resultado = InterAdapter(config, client=_client(handler)).mark_paid(
        CODIGO, date(2026, 11, 7), Decimal("10.00"),
    )
    assert resultado == "paid"
    assert vistos[0].startswith("Basic ")
    assert vistos[1] == "Bearer novo"
