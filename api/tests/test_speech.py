"""Nota de voz: transcrição no mesmo roteamento do texto, resposta falada só no horário."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx

from app.channels.outbound import send_to_debtor, voice_reply_allowed
from app.channels.speech import synthesize, transcribe, usable_transcript
from app.channels.tasks import _record_audio, continue_after_inbound, message_kind, turn_text
from app.channels.whatsapp import InboundMessage
from app.models.enums import ConversationState, Intent


def _msg(**kwargs) -> InboundMessage:
    base = dict(
        instance="cobranca",
        message_id="A1",
        remote_jid="5511988887777@s.whatsapp.net",
        from_me=False,
        push_name=None,
        text=None,
        media_type=None,
        mimetype="audio/ogg",
        key={"id": "A1"},
        timestamp=1,
        audio=False,
    )
    base.update(kwargs)
    return InboundMessage(**base)


def _conv(jid: str = "5511988887777@s.whatsapp.net"):
    return SimpleNamespace(
        tenant_id=uuid4(), id=uuid4(), wa_jid=jid, intent=None, state=ConversationState.AGENTE,
    )


def _tenant():
    return SimpleNamespace(
        id=uuid4(),
        whatsapp_instance="cobranca",
        timezone="America/Sao_Paulo",
        allowed_hours={"start": "08:00", "end": "20:00", "weekdays": [0, 1, 2, 3, 4, 5]},
    )


def test_usable_transcript_drops_noise():
    assert usable_transcript("  pago amanhã  ") == "pago amanhã"
    assert usable_transcript("[silêncio]") is None
    assert usable_transcript(" . ") is None
    assert usable_transcript(None) is None


def test_transcribe_without_openai_does_not_invent(monkeypatch):
    monkeypatch.setattr("app.channels.speech._openai_key", lambda: None)
    assert transcribe(b"ogg", "audio/ogg") is None


def test_transcribe_keeps_the_phrase(monkeypatch):
    monkeypatch.setattr("app.channels.speech._openai_key", lambda: "sk-test")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "quero parcelar"}

    monkeypatch.setattr("app.channels.speech.httpx.post", lambda *a, **k: Response())
    assert transcribe(b"ogg", "audio/ogg") == "quero parcelar"


def test_synthesize_returns_bytes(monkeypatch):
    monkeypatch.setattr("app.channels.speech._openai_key", lambda: "sk-test")

    class Response:
        content = b"opus"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("app.channels.speech.httpx.post", lambda *a, **k: Response())
    assert synthesize("combinado") == b"opus"


def test_turn_text_uses_transcript_and_skips_receipt():
    audio = _msg(message_id="A1", audio=True)
    receipt = _msg(message_id="R1", audio=False, media_type="imageMessage", text="comprovante")
    written = _msg(message_id="T1", text="e o pix?")
    text, voice = turn_text([audio, receipt, written], {"A1": "pago sexta"})
    assert text == "pago sexta\ne o pix?"
    assert voice is True
    assert message_kind(audio) == "audio"
    assert message_kind(receipt) == "arquivo"
    empty, heard = turn_text([audio], {"A1": None})
    assert empty == ""
    assert heard is False


def test_failed_audio_opens_exception_without_inventing_words(monkeypatch):
    saved = {}

    def fake_log(session, conv, direction, author, body, **kwargs):
        saved["body"] = body
        saved.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("app.channels.tasks.log_message", fake_log)

    def fake_open(*_args, **kwargs):
        saved["details"] = kwargs["details"]

    monkeypatch.setattr("app.channels.tasks.open_exception", fake_open)
    def fake_send(*args, **_kwargs):
        saved["reply"] = args[3]

    monkeypatch.setattr("app.channels.tasks.send_to_debtor", fake_send)
    conv = _conv()
    _record_audio(
        MagicMock(), _tenant(), conv, _msg(audio=True),
        (None, "t/voz/x.ogg", "audio/ogg"), uuid4(), reply=True,
    )
    assert saved["body"] is None
    assert saved["media_key"] == "t/voz/x.ogg"
    assert saved["details"]["motivo"] == "áudio sem transcrição utilizável"
    assert saved["reply"].startswith("Não consegui ouvir")
    assert conv.state == ConversationState.HUMANO


def test_transcript_keeps_the_quoted_invoice(monkeypatch):
    saved = {}

    def fake_log(session, conv, direction, author, body, **kwargs):
        saved["body"] = body
        saved.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("app.channels.tasks.log_message", fake_log)
    monkeypatch.setattr(
        "app.channels.tasks.open_exception",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("transcrição boa não abre exceção")),
    )
    invoice_id = uuid4()
    _record_audio(
        MagicMock(), _tenant(), _conv(), _msg(audio=True, text=None),
        ("pago amanhã", "t/voz/x.ogg", "audio/ogg"), invoice_id, reply=False,
    )
    assert saved["body"] == "pago amanhã"
    assert saved["invoice_id"] == invoice_id


def test_voice_transcript_follows_opt_out(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.channels.tasks.classify_intent",
        lambda text, today: SimpleNamespace(intent=Intent.PARAR, promised_date=None),
    )
    monkeypatch.setattr("app.channels.tasks.audit", lambda *a, **k: None)
    monkeypatch.setattr("app.channels.tasks.send_to_debtor", lambda *a, **k: sent.append((a[3], k)))
    conv = _conv()
    debtor = SimpleNamespace(id=uuid4(), opt_out=False, opt_out_at=None)
    outcome, turn = continue_after_inbound(
        MagicMock(), _tenant(), debtor, conv, "para de me cobrar", reply_voice=True,
    )
    assert outcome == "opt_out"
    assert turn is None
    assert debtor.opt_out is True
    assert sent[0][1]["voice"] is True


def test_voice_reply_only_inside_hours_and_never_in_a_group(monkeypatch):
    inside = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    outside = datetime(2026, 11, 11, 1, 0, tzinfo=UTC)
    tenant = _tenant()
    direct = _conv()
    group = _conv("120363@g.us")
    assert voice_reply_allowed(tenant, direct, inside)
    assert not voice_reply_allowed(tenant, direct, outside)
    assert not voice_reply_allowed(tenant, group, inside)

    session = MagicMock()
    client = MagicMock()
    client.send_audio.return_value = "WA-AUDIO"
    client.send_text.return_value = "WA-TEXT"
    monkeypatch.setattr("app.channels.outbound.synthesize", lambda text: b"opus")

    spoken = send_to_debtor(
        session, tenant, direct, "pode parcelar em 3", client=client, voice=True, now=inside,
    )
    assert spoken.body == "pode parcelar em 3"
    assert spoken.wa_message_id == "WA-AUDIO"
    client.send_text.assert_not_called()

    written = send_to_debtor(
        session, tenant, direct, "pode parcelar em 3", client=client, voice=True, now=outside,
    )
    assert written.body == "pode parcelar em 3"
    assert written.wa_message_id == "WA-TEXT"

    try:
        send_to_debtor(session, tenant, group, "cobrança", client=client, voice=True, now=inside)
    except ValueError as exc:
        assert "grupo" in str(exc)
    else:
        raise AssertionError("grupo não pode receber nota de voz")
    assert client.send_audio.call_count == 1


def test_voice_falls_back_to_text_when_synthesis_fails(monkeypatch):
    session = MagicMock()
    client = MagicMock()
    client.send_text.return_value = "WA-TEXT"
    monkeypatch.setattr("app.channels.outbound.synthesize", lambda text: None)
    msg = send_to_debtor(
        session, _tenant(), _conv(), "segue escrito", client=client, voice=True,
        now=datetime(2026, 11, 11, 15, 0, tzinfo=UTC),
    )
    assert msg.wa_message_id == "WA-TEXT"
    assert msg.body == "segue escrito"
    client.send_audio.assert_not_called()


def test_transport_timeout_on_voice_keeps_the_text(monkeypatch):
    session = MagicMock()
    client = MagicMock()
    client.send_audio.side_effect = httpx.TimeoutException("timeout")
    monkeypatch.setattr("app.channels.outbound.synthesize", lambda text: b"opus")
    msg = send_to_debtor(
        session, _tenant(), _conv(), "fica registrado", client=client, voice=True,
        now=datetime(2026, 11, 11, 15, 0, tzinfo=UTC),
    )
    assert msg.body == "fica registrado"
    assert msg.wa_message_id is None
