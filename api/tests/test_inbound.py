"""Entrada do WhatsApp: JID interno (@lid) e roteamento depois que a mensagem já foi gravada."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.channels.delivery import RECEIPT_BODY
from app.channels.inbound_sync import _poll_jids, agent_follow, unanswered_inbound
from app.channels.tasks import continue_after_inbound, conversation_for_phone
from app.channels.whatsapp import _contact_jid, inbound_from_record
from app.models.enums import ConversationState, Intent, MessageDirection


def test_poll_jids_keeps_lid_and_phone():
    jids = _poll_jids({
        "remoteJid": "271751305011249@lid",
        "lastMessage": {
            "key": {
                "remoteJid": "271751305011249@lid",
                "remoteJidAlt": "5511988887777@s.whatsapp.net",
                "fromMe": False,
            }
        },
    })
    assert "271751305011249@lid" in jids
    assert "5511988887777@s.whatsapp.net" in jids


def test_contact_jid_prefers_phone_over_lid():
    assert _contact_jid({
        "remoteJid": "123456@lid",
        "remoteJidAlt": "5511988887777@s.whatsapp.net",
    }) == "5511988887777@s.whatsapp.net"


def test_voice_note_is_not_a_receipt():
    msg = inbound_from_record("Cobranca", {
        "key": {"id": "PTT1", "fromMe": False, "remoteJid": "5511988887777@s.whatsapp.net"},
        "message": {
            "audioMessage": {
                "mimetype": "audio/ogg; codecs=opus",
                "ptt": True,
                "contextInfo": {"stanzaId": "OUT1"},
            }
        },
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.is_audio
    assert not msg.is_receipt
    assert not msg.has_media
    assert msg.mimetype == "audio/ogg; codecs=opus"
    assert msg.quoted_id == "OUT1"
    restored = msg.from_json(msg.to_json())
    assert restored.is_audio
    assert restored.quoted_id == "OUT1"


def test_audio_file_follows_the_voice_path():
    msg = inbound_from_record("Cobranca", {
        "key": {"id": "AUD1", "fromMe": False, "remoteJid": "5511988887777@s.whatsapp.net"},
        "message": {"pttMessage": {"mimetype": "audio/mpeg", "caption": "segue o áudio"}},
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.is_audio
    assert not msg.is_receipt
    assert msg.text == "segue o áudio"


def test_inbound_from_document_receipt():
    msg = inbound_from_record("Cobranca", {
        "key": {
            "id": "DOC1",
            "fromMe": False,
            "remoteJid": "123@lid",
            "remoteJidAlt": "5511988887777@s.whatsapp.net",
        },
        "messageType": "documentMessage",
        "message": {"documentMessage": {"mimetype": "image/png", "fileName": "pix.png"}},
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.has_media
    assert msg.mimetype == "image/png"
    assert msg.phone == "5511988887777"
    assert not msg.text


def test_inbound_keeps_quoted_stanza_from_reply():
    msg = inbound_from_record("Cobranca", {
        "key": {
            "id": "IN1",
            "fromMe": False,
            "remoteJid": "271751305011249@lid",
            "remoteJidAlt": "5511952313944@s.whatsapp.net",
        },
        "message": {"conversation": "Faltam quantas parcelas?"},
        "contextInfo": {
            "stanzaId": "3EB0D9391AC54874350998",
            "quotedMessage": {"conversation": "Olá, Carla!"},
        },
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.quoted_id == "3EB0D9391AC54874350998"
    assert msg.text == "Faltam quantas parcelas?"
    assert msg.phone == "5511952313944"


def test_inbound_quoted_stanza_inside_extended_text():
    msg = inbound_from_record("Cobranca", {
        "key": {"id": "IN2", "fromMe": False, "remoteJid": "5511988887777@s.whatsapp.net"},
        "message": {
            "extendedTextMessage": {
                "text": "e as parcelas?",
                "contextInfo": {"stanzaId": "OUT9"},
            }
        },
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.quoted_id == "OUT9"
    assert msg.text == "e as parcelas?"


def test_inbound_from_find_messages_record():
    msg = inbound_from_record("Cobranca", {
        "key": {"id": "ABC", "fromMe": False, "remoteJid": "5511988887777@s.whatsapp.net"},
        "message": {"conversation": "Sim, consigo"},
        "messageTimestamp": 1_700_000_000,
        "pushName": "Maria",
    })
    assert msg is not None
    assert msg.text == "Sim, consigo"
    assert msg.phone == "5511988887777"
    assert not msg.from_me


def test_conversation_for_phone_prefers_identity_wait():
    now = datetime.now(timezone.utc)
    maria = SimpleNamespace(id=uuid4())
    carla = SimpleNamespace(id=uuid4())
    conv_maria = SimpleNamespace(
        debtor_id=maria.id, state=ConversationState.HUMANO, updated_at=now
    )
    conv_carla = SimpleNamespace(
        debtor_id=carla.id, state=ConversationState.AGUARDANDO_IDENTIDADE, updated_at=now
    )
    session = MagicMock()
    session.scalars.side_effect = [
        iter([maria, carla]),
        iter([conv_maria, conv_carla]),
    ]
    picked = conversation_for_phone(session, uuid4(), "5511952313944")
    assert picked is conv_carla


def test_continue_after_inbound_stays_quiet_when_human_owns_chat():
    conv = SimpleNamespace(state=ConversationState.HUMANO, id=uuid4(), intent=None)
    outcome, turn = continue_after_inbound(MagicMock(), MagicMock(), MagicMock(), conv, "oi")
    assert outcome == "sem_texto_ou_humano"
    assert turn is None


def test_numeric_reply_is_not_an_opt_out(monkeypatch):
    conv = SimpleNamespace(state=ConversationState.AGENTE, id=uuid4(), intent=Intent.PARCELAR_DESCONTO)
    debtor = SimpleNamespace(opt_out=False, opt_out_at=None)

    def explode(text, today):
        raise AssertionError(f"número de opção não deve ser classificado: {text}")

    monkeypatch.setattr("app.channels.tasks.classify_intent", explode)
    tenant = SimpleNamespace(timezone="America/Sao_Paulo")
    outcome, turn = continue_after_inbound(MagicMock(), tenant, debtor, conv, "6")
    assert outcome == "agente"
    assert turn == (str(conv.id), "6", Intent.PARCELAR_DESCONTO)
    assert debtor.opt_out is False


def test_numbered_choice_picks_the_listed_option():
    from app.agent.graph import numbered_choice

    options = [{"id": f"op-{n}"} for n in range(1, 7)]
    picked = numbered_choice("6", options)
    assert picked is not None
    assert picked.decision == "aceita"
    assert picked.option_id == "op-6"
    assert numbered_choice("quero a 6", options) is None
    assert numbered_choice("9", options).decision == "outro"


def test_unanswered_inbound_joins_texts_since_last_reply():
    rows = [
        (MessageDirection.IN, "Ola", "WA2"),
        (MessageDirection.IN, "123", "WA1"),
        (MessageDirection.OUT, "confirma os dígitos", "OUT1"),
        (MessageDirection.IN, "mensagem antiga", "WA0"),
    ]
    assert unanswered_inbound(rows) == ("123\nOla", "WA2")


def test_unanswered_inbound_skips_receipt_placeholder():
    rows = [
        (MessageDirection.IN, RECEIPT_BODY, "FILE"),
        (MessageDirection.OUT, "resposta", "OUT1"),
    ]
    assert unanswered_inbound(rows) is None


def test_receipt_in_the_same_cycle_does_not_silence_the_agent():
    pending = ("123\nOla", "WA2")
    assert agent_follow(ConversationState.AGUARDANDO_IDENTIDADE, [], pending) == pending
    assert agent_follow(ConversationState.HUMANO, [("Ola", "WA2")], pending) is None
    assert agent_follow(ConversationState.AGENTE, [], None) is None


def test_continue_after_inbound_hands_off_to_agent(monkeypatch):
    conv = SimpleNamespace(state=ConversationState.AGENTE, id=uuid4(), intent=None)

    monkeypatch.setattr(
        "app.channels.tasks.classify_intent",
        lambda text, today: SimpleNamespace(intent=Intent.PARCELAR_DESCONTO, promised_date=None),
    )
    monkeypatch.setattr("app.channels.tasks._route_deterministic", lambda *a, **k: None)

    tenant = SimpleNamespace(timezone="America/Sao_Paulo")
    outcome, turn = continue_after_inbound(MagicMock(), tenant, MagicMock(), conv, "qual o valor?")
    assert outcome == "agente"
    assert turn == (str(conv.id), "qual o valor?", Intent.PARCELAR_DESCONTO)
    assert conv.intent == Intent.PARCELAR_DESCONTO
    assert isinstance(date.today(), date)
