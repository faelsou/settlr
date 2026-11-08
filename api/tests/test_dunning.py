"""Régua de cobrança — 100% determinística (FLUXOS.md §5)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.dunning.legal import MISSING_OPINION, adopt_canonical_texts, production_without_opinion
from app.dunning.official import (
    commit_activation,
    parse_connection_state,
    parse_template_catalog,
    preserve_approved,
    read_evolution,
)
from app.dunning.payment import has_payment_code
from app.dunning.rules import (
    TEXT_VERSION,
    AllowedHours,
    DEFAULT_DUNNING_RULES,
    Step,
    decide,
    parse_steps,
    promise_pauses,
    within_allowed_hours,
)
from app.dunning.service import Dispatch, _send_step, process_invoice
from app.models import DunningEvent
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

    def grab(_session, _tenant, _invoice, _debtor, step, _channels, _client=None) -> Dispatch:
        sent.append(step.key)
        return Dispatch(sent=True)

    monkeypatch.setattr("app.dunning.service._send_step", grab)

    outcome = process_invoice(_Sessao(invoice, debtor), tenant, invoice.id, date(2026, 10, 22))

    assert outcome.action == "send"
    assert outcome.reason == "D+5"
    assert sent == ["D+5"]
    assert invoice.status == InvoiceStatus.EM_COBRANCA


def _regua_de_um_passo() -> dict:
    return {
        "steps": [
            {"key": "D-3", "offset": -3, "channels": ["whatsapp"], "template": "lembrete"},
            {"key": "D+30", "offset": 30, "channels": [], "template": None, "handoff": True},
        ],
        "whatsapp_templates": {
            "lembrete": {"name": "lembrete_pix", "language": "pt_BR", "params": ["{nome}"]},
        },
    }


def _catalogo_aprovado() -> list[dict]:
    return [{"name": "lembrete_pix", "language": "pt_BR", "status": "approved"}]


def test_canonical_texts_match_the_versioned_dossier():
    dossier = Path(__file__).resolve().parents[2] / "docs" / "TEXTOS-REGUA.md"
    text = dossier.read_text(encoding="utf-8")
    assert TEXT_VERSION in text
    assert DEFAULT_DUNNING_RULES["text_version"] == TEXT_VERSION
    blob = " ".join(DEFAULT_DUNNING_RULES["templates"].values()).lower()
    for banned in ("restrição", "negativ", "protesto", "15%", "6 vezes", "3 parcelas"):
        assert banned not in blob
    for key, body in DEFAULT_DUNNING_RULES["templates"].items():
        assert f"## {key}" in text
        assert body in text


def test_old_unversioned_rules_adopt_the_canonical_texts():
    old = {
        "steps": [{"key": "D+3", "offset": 3, "channels": ["whatsapp"], "template": "desconto_vista"}],
        "templates": {"desconto_vista": "15% de desconto", "aviso_restricao": "restrição do nome"},
        "whatsapp_templates": {"aviso_restricao": {"name": "aviso_meta", "language": "pt_BR", "params": []}},
        "rate_per_minute": 12,
    }
    adopted = adopt_canonical_texts(old)
    assert adopted is not None
    assert adopted["text_version"] == TEXT_VERSION
    assert "desconto_vista" not in adopted["templates"]
    assert "15%" not in " ".join(adopted["templates"].values())
    assert adopted["whatsapp_templates"]["aviso_equipe"]["name"] == "aviso_meta"
    assert adopted["rate_per_minute"] == 12
    assert adopt_canonical_texts(adopted) is None
    assert adopt_canonical_texts({"templates": {"lembrete": "texto da clínica"}, "text_version": ""}) is None


def test_production_activation_waits_for_the_legal_opinion(monkeypatch):
    from app.api.routes.admin import missing_requirements

    tenant = SimpleNamespace(
        negotiation_policy={"max_installments": 6},
        dunning_rules={"steps": []},
        allowed_hours={"start": "08:00"},
        whatsapp_instance="loja",
        legal_basis="execução de contrato",
    )

    class Ambiente:
        def __init__(self, env: str, ref: str) -> None:
            self.env = env
            self.legal_opinion_ref = ref

    monkeypatch.setattr("app.api.routes.admin.get_settings", lambda: Ambiente("dev", ""))
    assert MISSING_OPINION not in missing_requirements(tenant)
    assert production_without_opinion("dev", "") is False

    monkeypatch.setattr("app.api.routes.admin.get_settings", lambda: Ambiente("prod", ""))
    assert missing_requirements(tenant) == [MISSING_OPINION]

    monkeypatch.setattr(
        "app.api.routes.admin.get_settings", lambda: Ambiente("prod", "SETL-15#parecer")
    )
    assert missing_requirements(tenant) == []


class _Transacao:
    def __enter__(self):
        return None

    def __exit__(self, *_args):
        return False


class _SessaoAdmin:
    def __init__(self, tenant) -> None:
        self.tenant = tenant

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def begin(self) -> _Transacao:
        return _Transacao()

    def get(self, _model, key):
        return self.tenant if key == self.tenant.id else None


def _token(role: str, tenant_id) -> str:
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    return jwt.encode(
        {
            "sub": "user-1",
            "email": "agencia@settlr.test",
            "aud": settings.jwt_audience,
            "app_metadata": {"role": role, "tenant_id": str(tenant_id) if tenant_id else None},
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def _conta_pronta():
    from uuid import uuid4

    from app.models import Tenant

    return Tenant(
        id=uuid4(),
        name="Clínica",
        slug="clinica-parecer",
        active=False,
        timezone="America/Sao_Paulo",
        negotiation_policy={"max_installments": 6},
        dunning_rules=_regua_de_um_passo(),
        reconciliation_rules={},
        allowed_hours={"start": "08:00", "end": "20:00", "weekdays": [0, 1, 2, 3, 4, 5]},
        whatsapp_instance="loja",
        whatsapp_number="5511999990000",
        whatsapp_senders=[],
        issuer_config={},
        legal_basis="execução de contrato",
    )


def test_activate_http_refuses_production_until_the_opinion_is_recorded(monkeypatch):
    from fastapi.testclient import TestClient

    from app.services.cadastro import app

    tenant = _conta_pronta()
    monkeypatch.setattr("app.api.routes.admin.SessionLocal", lambda: _SessaoAdmin(tenant))
    monkeypatch.setattr("app.api.routes.admin.read_evolution", lambda *_args, **_kwargs: ("close", []))
    monkeypatch.setattr("app.api.routes.admin.audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.api.routes.admin.set_tenant", lambda *_args, **_kwargs: None)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token('agencia', None)}"}

    class Ambiente:
        def __init__(self, env: str, ref: str) -> None:
            self.env = env
            self.legal_opinion_ref = ref

    monkeypatch.setattr("app.api.routes.admin.get_settings", lambda: Ambiente("prod", ""))
    blocked = client.post(f"/admin/tenants/{tenant.id}/activate", headers=headers)
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == {"missing": [MISSING_OPINION]}
    assert tenant.active is False

    monkeypatch.setattr(
        "app.api.routes.admin.get_settings", lambda: Ambiente("prod", "SETL-15#parecer")
    )
    opened = client.post(f"/admin/tenants/{tenant.id}/activate", headers=headers)
    assert opened.status_code == 422
    assert opened.json()["detail"]["missing"] == ["número pareado", "template oficial aprovado"]
    assert tenant.active is False

    monkeypatch.setattr("app.api.routes.admin.get_settings", lambda: Ambiente("dev", ""))
    dev = client.post(f"/admin/tenants/{tenant.id}/activate", headers=headers)
    assert dev.status_code == 422
    assert MISSING_OPINION not in dev.json()["detail"]["missing"]


def test_settings_http_returns_the_text_version():
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.dunning.rules import DEFAULT_DUNNING_RULES
    from app.services.cadastro import app

    tenant = _conta_pronta()
    tenant.dunning_rules = DEFAULT_DUNNING_RULES
    session = _SessaoAdmin(tenant)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get(
            "/settings",
            headers={"Authorization": f"Bearer {_token('operador', tenant.id)}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rules = response.json()["dunning_rules"]
    assert rules["text_version"] == TEXT_VERSION
    assert "15%" not in " ".join(rules["templates"].values())
    assert "aviso_restricao" not in rules["templates"]


def test_activation_stays_off_without_a_paired_number():
    tenant = SimpleNamespace(active=False, dunning_rules=_regua_de_um_passo())
    missing = commit_activation(tenant, "close", _catalogo_aprovado())
    assert missing == ["número pareado"]
    assert tenant.active is False
    assert "approved_templates" not in tenant.dunning_rules


def test_activation_stays_off_without_an_approved_template():
    tenant = SimpleNamespace(active=False, dunning_rules=_regua_de_um_passo())
    catalog = [{"name": "lembrete_pix", "language": "pt_BR", "status": "pending"}]
    missing = commit_activation(tenant, "open", catalog)
    assert missing == ["template oficial aprovado"]
    assert tenant.active is False


def test_activation_turns_on_when_the_number_is_paired_and_the_template_is_approved():
    tenant = SimpleNamespace(active=False, dunning_rules=_regua_de_um_passo())
    assert commit_activation(tenant, "open", _catalogo_aprovado()) == []
    assert tenant.active is True
    assert tenant.dunning_rules["approved_templates"]["lembrete"]["name"] == "lembrete_pix"


def test_settings_cannot_invent_an_approved_template():
    previous = {
        "approved_templates": {
            "lembrete": {"name": "lembrete_pix", "language": "pt_BR", "params": ["{nome}"]},
        },
    }
    forged = {
        "approved_templates": {
            "lembrete": {"name": "falso", "language": "pt_BR", "params": []},
        },
        "whatsapp_templates": {},
    }
    assert "approved_templates" not in preserve_approved({}, forged)

    renamed = {
        "whatsapp_templates": {
            "lembrete": {"name": "outro", "language": "pt_BR", "params": ["{nome}"]},
        },
    }
    assert "approved_templates" not in preserve_approved(previous, renamed)

    same = {
        "whatsapp_templates": {
            "lembrete": {"name": "lembrete_pix", "language": "pt_BR", "params": ["{valor}"]},
        },
    }
    kept = preserve_approved(previous, same)
    assert kept["approved_templates"]["lembrete"]["params"] == ["{valor}"]


def test_evolution_payloads_mean_paired_and_approved():
    state = parse_connection_state({"instance": {"instanceName": "loja", "state": "open"}})
    catalog = parse_template_catalog([
        {"name": "lembrete_pix", "language": "pt-BR", "status": "APPROVED"},
    ])
    assert state == "open"
    assert catalog[0]["status"] == "approved"
    tenant = SimpleNamespace(active=False, dunning_rules=_regua_de_um_passo())
    assert commit_activation(tenant, state, catalog) == []


def test_evolution_down_counts_as_not_ready():
    class Fora:
        def connection_state(self, _instance: str) -> str:
            raise RuntimeError("sem rede")

        def list_templates(self, _instance: str) -> list[dict]:
            raise RuntimeError("sem rede")

    assert read_evolution(Fora(), "loja") == (None, [])


def _devedor_com_telefone() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), name="Maria Souza", phone="5511999999999", phones=[], email=None,
    )


def _titulo_com_pix() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        debtor_id=uuid4(),
        status=InvoiceStatus.ABERTO,
        due_date=date(2026, 10, 17),
        description="mensalidade",
        amount=Decimal("10"),
        amount_open=Decimal("10"),
        external_id="1",
        pix_copy_paste="00020126PIX",
        payment_url=None,
        digitable_line=None,
    )


def test_proactive_send_never_uses_free_text(monkeypatch):
    invoice = _titulo_com_pix()
    debtor = _devedor_com_telefone()
    tenant = SimpleNamespace(
        id=uuid4(),
        whatsapp_instance="cobranca",
        dunning_rules={"templates": {"oferta_negociacao": "texto livre do modelo"}},
    )
    added: list[object] = []
    session = MagicMock()
    session.add.side_effect = added.append
    monkeypatch.setattr("app.dunning.service.record_message", lambda *_a, **_k: None)
    client = MagicMock()
    client.send_text.side_effect = AssertionError("texto livre no disparo")
    step = Step("D+5", 5, ("whatsapp",), "oferta_negociacao")

    dispatch = _send_step(session, tenant, invoice, debtor, step, ("whatsapp",), client)

    client.send_template.assert_not_called()
    assert dispatch.blocked_template is True
    assert dispatch.sent is False
    assert not any(isinstance(item, DunningEvent) for item in added)


def test_proactive_send_uses_the_approved_template(monkeypatch):
    invoice = _titulo_com_pix()
    debtor = _devedor_com_telefone()
    tenant = SimpleNamespace(
        id=uuid4(),
        whatsapp_instance="cobranca",
        dunning_rules={
            "templates": {"oferta_negociacao": "texto livre do modelo"},
            "approved_templates": {
                "oferta_negociacao": {
                    "name": "oferta_oficial",
                    "language": "pt_BR",
                    "params": ["{nome}"],
                },
            },
        },
    )
    session = MagicMock()
    monkeypatch.setattr("app.dunning.service.record_message", lambda *_a, **_k: None)
    monkeypatch.setattr("app.dunning.service.take_rate_slot", lambda *_a, **_k: True)
    monkeypatch.setattr("app.dunning.service.audit", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.dunning.service.get_or_create_conversation",
        lambda *_a, **_k: SimpleNamespace(id=uuid4(), tenant_id=tenant.id),
    )
    client = MagicMock()
    client.send_template.return_value = "WA1"
    step = Step("D+5", 5, ("whatsapp",), "oferta_negociacao")

    dispatch = _send_step(session, tenant, invoice, debtor, step, ("whatsapp",), client)

    client.send_text.assert_not_called()
    client.send_template.assert_called_once()
    assert client.send_template.call_args.args[2] == "oferta_oficial"
    assert dispatch.sent is True


def test_process_invoice_skips_when_the_official_template_is_missing(monkeypatch):
    invoice = _titulo_com_pix()
    debtor = _devedor_com_telefone()
    debtor.opt_out = False
    tenant = SimpleNamespace(id=uuid4(), dunning_rules={}, whatsapp_instance="cobranca")
    monkeypatch.setattr("app.dunning.service.record_message", lambda *_a, **_k: None)

    outcome = process_invoice(_Sessao(invoice, debtor), tenant, invoice.id, date(2026, 10, 22))

    assert outcome.action == "skip"
    assert outcome.reason == "sem_template_oficial"
    assert invoice.status == InvoiceStatus.ABERTO


def test_allowed_hours_respects_timezone_and_weekday():
    hours = AllowedHours.from_json({"start": "08:00", "end": "20:00", "weekdays": [0, 1, 2, 3, 4]})
    tz = "America/Sao_Paulo"
    monday_morning = datetime(2026, 10, 19, 11, 0, tzinfo=ZoneInfo(tz))
    monday_night = datetime(2026, 10, 19, 21, 0, tzinfo=ZoneInfo(tz))
    sunday = datetime(2026, 10, 18, 11, 0, tzinfo=ZoneInfo(tz))
    assert within_allowed_hours(monday_morning, hours, tz)
    assert not within_allowed_hours(monday_night, hours, tz)
    assert not within_allowed_hours(sunday, hours, tz)
