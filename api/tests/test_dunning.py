"""Régua de cobrança — 100% determinística (FLUXOS.md §5)."""

from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.dunning.payment import has_payment_code
from app.dunning.rules import (
    AllowedHours,
    decide,
    parse_steps,
    promise_pauses,
    within_allowed_hours,
)
from app.dunning.service import process_invoice
from app.models.enums import InvoiceStatus


STEPS = parse_steps(None)


def test_opt_out_skips():
    result = decide(
        today=date(2026, 10, 20),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=True,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "skip"
    assert result.reason == "opt_out"


def test_active_promise_pauses_until_next_day():
    assert promise_pauses(date(2026, 10, 18), date(2026, 10, 17))
    assert not promise_pauses(date(2026, 10, 19), date(2026, 10, 17))

    result = decide(
        today=date(2026, 10, 18),
        due_date=date(2026, 10, 10),
        steps=STEPS,
        opt_out=False,
        active_promise=date(2026, 10, 17),
        sent=set(),
    )
    assert result.action == "skip"
    assert result.reason == "promessa_ativa"


def test_sends_current_step_once():
    result = decide(
        today=date(2026, 10, 17),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "send"
    assert result.step and result.step.key == "D0"
    assert result.channels == ("whatsapp",)

    again = decide(
        today=date(2026, 10, 17),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent={("D0", "whatsapp")},
    )
    assert again.action == "skip"
    assert again.reason == "etapa_ja_enviada"


def test_late_cycle_sends_only_latest_step():
    result = decide(
        today=date(2026, 10, 22),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "send"
    assert result.step and result.step.key == "D+5"


def test_d30_hands_off_to_human():
    result = decide(
        today=date(2026, 11, 20),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "handoff"
    assert result.step and result.step.key == "D+30"


def test_blank_pix_or_boleto_is_not_a_payment_code():
    assert not has_payment_code(None, None)
    assert not has_payment_code("  ", "")
    assert not has_payment_code(None, "   ")
    assert has_payment_code("00020126PIX", None)
    assert has_payment_code(None, "34191.79001")


def test_title_without_pix_or_boleto_skips_even_at_the_end_of_the_ladder():
    result = decide(
        today=date(2026, 11, 20),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
        has_payment_code=False,
    )
    assert result.action == "skip"
    assert result.reason == "sem_meio_pagamento"
    assert result.step is None


def test_late_code_enters_only_the_current_step():
    result = decide(
        today=date(2026, 10, 22),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
        has_payment_code=True,
    )
    assert result.action == "send"
    assert result.step and result.step.key == "D+5"


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

    def tuples(self) -> list[tuple[object, ...]]:
        return []

    def scalar(self, *_args: object, **_kwargs: object) -> None:
        return None


def _titulo(*, pix: str | None = None, boleto: str | None = None, link: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        debtor_id=uuid4(),
        status=InvoiceStatus.ABERTO,
        due_date=date(2026, 10, 17),
        pix_copy_paste=pix,
        digitable_line=boleto,
        payment_url=link,
    )


def test_process_invoice_does_not_send_without_pix_or_boleto(monkeypatch):
    invoice = _titulo(link="https://pagar.exemplo/so-link")
    debtor = SimpleNamespace(opt_out=False)
    tenant = SimpleNamespace(id=uuid4(), dunning_rules=None)
    sent: list[str] = []
    monkeypatch.setattr(
        "app.dunning.service._send_step",
        lambda *_args, **_kwargs: sent.append("enviou"),
    )

    outcome = process_invoice(_Sessao(invoice, debtor), tenant, invoice.id, date(2026, 10, 22))

    assert outcome.action == "skip"
    assert outcome.reason == "sem_meio_pagamento"
    assert sent == []
    assert invoice.status == InvoiceStatus.ABERTO


def test_process_invoice_sends_only_the_current_step_when_the_code_arrives(monkeypatch):
    invoice = _titulo(pix="00020126PIX")
    debtor = SimpleNamespace(opt_out=False)
    tenant = SimpleNamespace(id=uuid4(), dunning_rules=None)
    sent: list[str] = []

    def grab(_session, _tenant, _invoice, _debtor, step, _channels, _client=None) -> None:
        sent.append(step.key)

    monkeypatch.setattr("app.dunning.service._send_step", grab)

    outcome = process_invoice(_Sessao(invoice, debtor), tenant, invoice.id, date(2026, 10, 22))

    assert outcome.action == "send"
    assert outcome.reason == "D+5"
    assert sent == ["D+5"]
    assert invoice.status == InvoiceStatus.EM_COBRANCA


def test_allowed_hours_respects_timezone_and_weekday():
    hours = AllowedHours.from_json({"start": "08:00", "end": "20:00", "weekdays": [0, 1, 2, 3, 4]})
    tz = "America/Sao_Paulo"
    monday_morning = datetime(2026, 10, 19, 11, 0, tzinfo=ZoneInfo(tz))
    monday_night = datetime(2026, 10, 19, 21, 0, tzinfo=ZoneInfo(tz))
    sunday = datetime(2026, 10, 18, 11, 0, tzinfo=ZoneInfo(tz))
    assert within_allowed_hours(monday_morning, hours, tz)
    assert not within_allowed_hours(monday_night, hours, tz)
    assert not within_allowed_hours(sunday, hours, tz)
