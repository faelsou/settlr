"""SETL-7: HTTP 200 não é entrega. O recibo grava o status e a falha libera reenvio."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from prometheus_client import REGISTRY

from app.channels.delivery import (
    ACEITO,
    ENTREGUE,
    FALHOU,
    LIDO,
    DeliveryUpdate,
    advance_status,
    apply_delivery_updates,
    counts_as_dispatched,
    parse_delivery_updates,
)
from app.channels.whatsapp import EvolutionWebhook
from app.dunning.rules import decide, parse_steps

STEPS = parse_steps(None)


def _decide(sent: set[tuple[str, str]], *, opt_out: bool = False):
    return decide(
        today=date(2026, 10, 17),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=opt_out,
        active_promise=None,
        sent=sent,
    )


def test_http_200_statuses_still_block_the_step():
    for status in (ACEITO, ENTREGUE, LIDO, "enviado"):
        assert counts_as_dispatched(status)
    assert not counts_as_dispatched(FALHOU)


def test_failed_receipt_releases_the_step_but_opt_out_still_skips():
    blocking = {
        (step, channel)
        for step, channel, status in [("D0", "whatsapp", FALHOU)]
        if counts_as_dispatched(status)
    }
    again = _decide(blocking)
    assert again.action == "send"
    assert again.step and again.step.key == "D0"

    opted_out = _decide(blocking, opt_out=True)
    assert opted_out.action == "skip"
    assert opted_out.reason == "opt_out"


def test_accepted_step_is_not_resent():
    result = _decide({("D0", "whatsapp")})
    assert result.action == "skip"
    assert result.reason == "etapa_ja_enviada"


def test_receipt_does_not_regress_terminal_status():
    assert advance_status(ACEITO, ENTREGUE) == ENTREGUE
    assert advance_status(ENTREGUE, LIDO) == LIDO
    assert advance_status(ACEITO, FALHOU) == FALHOU
    assert advance_status(ENTREGUE, ENTREGUE) is None
    assert advance_status(LIDO, ENTREGUE) is None
    assert advance_status(ENTREGUE, FALHOU) is None
    assert advance_status(FALHOU, ENTREGUE) is None
    assert advance_status("enviado", ENTREGUE) == ENTREGUE
    assert advance_status(ACEITO, "sem_recibo") == "sem_recibo"
    assert advance_status("sem_recibo", ENTREGUE) == ENTREGUE
    assert advance_status(ENTREGUE, "sem_recibo") is None


def test_parse_messages_update_object_and_list():
    single = parse_delivery_updates(EvolutionWebhook(
        event="messages.update",
        instance="cobranca",
        data={"key": {"id": "WA1"}, "update": {"status": "DELIVERY_ACK"}},
    ))
    assert single == [DeliveryUpdate("WA1", ENTREGUE)]

    batch = parse_delivery_updates(EvolutionWebhook(
        event="MESSAGES_UPDATE",
        instance="cobranca",
        data=[
            {"messageId": "WA2", "status": 4},
            {"messageId": "WA3", "status": "ERROR"},
            {"status": "READ"},
        ],
    ))
    assert batch == [DeliveryUpdate("WA2", LIDO), DeliveryUpdate("WA3", FALHOU)]


def test_apply_mirrors_message_and_dunning_event_once():
    message = SimpleNamespace(delivery_status=ACEITO)
    event = SimpleNamespace(delivery_status=ACEITO)
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=MagicMock(return_value=[message])),
        MagicMock(all=MagicMock(return_value=[event])),
        MagicMock(all=MagicMock(return_value=[message])),
        MagicMock(all=MagicMock(return_value=[event])),
    ]
    labels = {
        "direction": "saida",
        "stage": "recibo",
        "context": ENTREGUE,
        "kind": "texto",
        "result": "ok",
    }
    before = REGISTRY.get_sample_value("cobranca_whatsapp_messages_total", labels) or 0
    first = apply_delivery_updates(session, [DeliveryUpdate("WA1", ENTREGUE)])
    second = apply_delivery_updates(session, [DeliveryUpdate("WA1", ENTREGUE)])
    assert first == 2
    assert second == 0
    assert message.delivery_status == ENTREGUE
    assert event.delivery_status == ENTREGUE
    assert REGISTRY.get_sample_value("cobranca_whatsapp_messages_total", labels) == before + 1
