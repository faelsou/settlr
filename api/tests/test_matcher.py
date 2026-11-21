"""Conciliação em camadas — código determinístico, sem LLM (FLUXOS.md §10)."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.enums import MatchMethod
from app.reconciliation.matcher import (
    Decision,
    InvoiceCandidate,
    PaymentData,
    ReconciliationRules,
    document_matches,
    match_payment,
    name_similarity,
)


def _invoice(**kwargs) -> InvoiceCandidate:
    defaults = dict(
        id=uuid4(),
        debtor_id=uuid4(),
        amount_open=Decimal("350.00"),
        due_date=date(2026, 10, 12),
        debtor_doc="12345678909",
        debtor_name="Maria Souza",
        txid="txdemo0001",
    )
    defaults.update(kwargs)
    return InvoiceCandidate(**defaults)


def test_layer1_exact_txid_auto_settle():
    invoice = _invoice()
    payment = PaymentData(
        amount=Decimal("350.00"),
        paid_on=date(2026, 10, 12),
        e2e_id="E18236120202610121230ABCDEFGHIJK",
        txid=invoice.txid,
    )
    result = match_payment(payment, [invoice])
    assert result.decision == Decision.AUTO
    assert result.layer == 1
    assert result.method == MatchMethod.CHAVE_EXATA
    assert result.allocations[0].invoice_id == invoice.id


def test_layer2_value_document_and_window():
    invoice = _invoice(txid=None)
    payment = PaymentData(
        amount=Decimal("350.00"),
        paid_on=date(2026, 10, 14),
        payer_doc="12345678909",
        payer_name="Outro Nome",
    )
    result = match_payment(payment, [invoice])
    assert result.decision == Decision.AUTO
    assert result.layer == 2
    assert result.method == MatchMethod.VALOR_DOCUMENTO


def test_layer3_name_similarity_becomes_suggestion():
    invoice = _invoice(txid=None)
    payment = PaymentData(
        amount=Decimal("350.00"),
        paid_on=date(2026, 10, 14),
        payer_name="Maria de Souza",
    )
    result = match_payment(payment, [invoice])
    assert result.decision == Decision.SUGGESTION
    assert result.layer == 3
    assert result.suggestions


def test_layer3_sum_of_invoices_same_debtor():
    debtor_id = uuid4()
    a = _invoice(
        debtor_id=debtor_id, amount_open=Decimal("200.00"), txid=None, due_date=date(2026, 10, 1)
    )
    b = _invoice(
        debtor_id=debtor_id,
        debtor_doc=a.debtor_doc,
        debtor_name=a.debtor_name,
        amount_open=Decimal("150.00"),
        txid=None,
        due_date=date(2026, 10, 10),
    )
    payment = PaymentData(
        amount=Decimal("350.00"),
        paid_on=date(2026, 10, 12),
        payer_name="Maria Souza",
        debtor_id=debtor_id,
    )
    result = match_payment(payment, [a, b])
    assert result.decision == Decision.SUGGESTION
    methods = {s["method"] for s in result.suggestions}
    assert MatchMethod.SOMA_TITULOS.value in methods


def test_layer4_unidentified():
    invoice = _invoice(txid=None)
    payment = PaymentData(
        amount=Decimal("10.00"),
        paid_on=date(2026, 1, 1),
        payer_name="Desconhecido",
    )
    result = match_payment(payment, [invoice])
    assert result.decision == Decision.UNIDENTIFIED
    assert result.layer == 4


def test_partial_when_underpay_allowed():
    invoice = _invoice()
    payment = PaymentData(
        amount=Decimal("200.00"),
        paid_on=date(2026, 10, 12),
        txid=invoice.txid,
    )
    result = match_payment(payment, [invoice], ReconciliationRules(allow_partial=True))
    assert result.decision == Decision.PARTIAL
    assert result.allocations[0].amount == Decimal("200.00")


def test_amount_mismatch_when_partial_forbidden():
    invoice = _invoice()
    payment = PaymentData(
        amount=Decimal("200.00"),
        paid_on=date(2026, 10, 12),
        txid=invoice.txid,
    )
    result = match_payment(payment, [invoice], ReconciliationRules(allow_partial=False))
    assert result.decision == Decision.AMOUNT_MISMATCH


def test_masked_document_matches():
    assert document_matches("***.456.789-**", "12345678909")
    assert not document_matches("***.000.000-**", "12345678909")


def test_name_similarity_ignores_stopwords():
    assert name_similarity("Maria de Souza", "Maria Souza") >= 0.82
