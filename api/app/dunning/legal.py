"""Parecer do SETL-15.

A minuta do contrato está em docs/CONTRATO.md. Os textos versionados estão em
docs/TEXTOS-REGUA.md. Este módulo não é o parecer: em produção a ativação fica
recusada até `LEGAL_OPINION_REF` apontar o registro feito no ticket.
"""

from app.dunning.rules import DEFAULT_DUNNING_RULES, TEXT_VERSION

MISSING_OPINION = "parecer jurídico (SETL-15)"

# Chaves da régua anterior, substituídas na versão canônica.
_RETIRED_TEMPLATES = {
    "desconto_vista": "convite_quitar",
    "parcelamento": "convite_conversa",
    "entrada_saldo": "lembrete_aberto",
    "aviso_restricao": "aviso_equipe",
}


def production_without_opinion(env: str, opinion_ref: str | None) -> bool:
    """O primeiro cliente em produção não liga sem o parecer registrado."""
    return env == "prod" and not (opinion_ref or "").strip()


def _rename(spec: object) -> dict:
    if not isinstance(spec, dict):
        return {}
    return {_RETIRED_TEMPLATES.get(str(key), str(key)): value for key, value in spec.items()}


def adopt_canonical_texts(rules: dict | None) -> dict | None:
    """Troca a régua antiga, ainda sem versão, pelos textos canônicos.

    Uma régua que o tenant editou, sem as chaves aposentadas, permanece.
    """
    if not isinstance(rules, dict) or rules.get("text_version") == TEXT_VERSION:
        return None
    templates = rules.get("templates") or {}
    if not isinstance(templates, dict) or not any(key in templates for key in _RETIRED_TEMPLATES):
        return None
    fresh = {
        "text_version": TEXT_VERSION,
        "steps": [dict(step) for step in DEFAULT_DUNNING_RULES["steps"]],
        "templates": dict(DEFAULT_DUNNING_RULES["templates"]),
    }
    whatsapp = _rename(rules.get("whatsapp_templates"))
    if whatsapp:
        fresh["whatsapp_templates"] = whatsapp
    approved = _rename(rules.get("approved_templates"))
    if approved:
        fresh["approved_templates"] = approved
    if rules.get("rate_per_minute"):
        fresh["rate_per_minute"] = rules["rate_per_minute"]
    return fresh
