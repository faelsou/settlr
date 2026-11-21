"""Validação determinística do comprovante (FLUXOS.md §9)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.receipts.schemas import ReceiptExtraction
from app.receipts.validation import validate_extraction

NOW = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)


def _extraction(**kwargs) -> ReceiptExtraction:
    data = dict(
        is_payment_receipt=True,
        confidence=0.92,
        amount=Decimal("350.00"),
        paid_at=datetime(2026, 10, 16, 12, 30, tzinfo=UTC),
        e2e_id="E18236120202610161230ABCDEFGHIJK",
        payer_name="Maria Souza",
        payer_doc="12345678909",
        bank="Nubank",
    )
    data.update(kwargs)
    return ReceiptExtraction(**data)


def test_valid_receipt_has_no_problems():
    assert validate_extraction(_extraction(), NOW, 0.8) == []


def test_low_confidence_and_bad_amount():
    problems = validate_extraction(
        _extraction(confidence=0.4, amount=Decimal("0")), NOW, 0.8
    )
    assert any("confiança baixa" in p for p in problems)
    assert any("valor" in p for p in problems)


def test_invalid_e2e_format():
    problems = validate_extraction(_extraction(e2e_id="PIX-123"), NOW, 0.8)
    assert any("E2E" in p for p in problems)


def test_not_a_receipt():
    assert validate_extraction(
        _extraction(is_payment_receipt=False), NOW, 0.8
    ) == ["documento não parece um comprovante de pagamento"]
