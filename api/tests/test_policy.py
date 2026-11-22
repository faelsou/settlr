"""Opções de acordo — o LLM só escolhe o que este módulo devolve (FLUXOS.md §7)."""

from datetime import date
from decimal import Decimal

from app.agent.policy import (
    NegotiationPolicy,
    build_payment_options,
    validate_promise_date,
)

POLICY = NegotiationPolicy.from_json(None)
TODAY = date(2026, 10, 17)


def test_cash_option_applies_max_discount():
    options = build_payment_options(Decimal("1000.00"), POLICY, TODAY)
    cash = next(o for o in options if o.kind == "a_vista")
    assert cash.discount == Decimal("100.00")
    assert cash.total == Decimal("900.00")


def test_installments_respect_max_and_minimum_amount():
    options = build_payment_options(Decimal("1000.00"), POLICY, TODAY)
    parcelados = [o for o in options if o.kind == "parcelado"]
    assert parcelados
    assert max(len(o.installments) for o in parcelados) <= POLICY.max_installments
    for option in parcelados:
        rest = option.installments[1:]
        assert rest
        assert min(i.amount for i in rest) >= POLICY.min_installment_amount


def test_no_options_for_zero_balance():
    assert build_payment_options(Decimal("0"), POLICY, TODAY) == []


def test_small_balance_stops_before_tiny_installments():
    options = build_payment_options(Decimal("40.00"), POLICY, TODAY)
    assert all(o.kind == "a_vista" for o in options)


def test_promise_date_limits():
    assert validate_promise_date(TODAY, TODAY, POLICY) == "a data precisa ser futura"
    assert validate_promise_date(date(2027, 1, 1), TODAY, POLICY)
    assert validate_promise_date(date(2026, 10, 20), TODAY, POLICY) is None
