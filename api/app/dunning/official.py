"""Template oficial e número pareado. A régua só liga com os dois.

O texto livre do modelo fica na resposta. O disparo proativo usa o template
que a Meta marcou como aprovado na hora de ativar a conta.
"""

from typing import Any

from app.core.logging import get_logger
from app.dunning.rules import parse_steps

log = get_logger(__name__)

PAIRED_STATE = "open"
APPROVED_STATUS = "approved"
MISSING_PAIRING = "número pareado"
MISSING_TEMPLATE = "template oficial aprovado"


def parse_connection_state(body: Any) -> str | None:
    """Estado da Evolution. `open` é o número pareado."""
    if not isinstance(body, dict):
        return None
    instance = body.get("instance")
    raw = None
    if isinstance(instance, dict):
        raw = instance.get("state") or instance.get("status")
    raw = raw or body.get("state") or body.get("status")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    return text or None


def parse_template_catalog(body: Any) -> list[dict]:
    """Catálogo da Meta via Evolution. Aceita a lista ou o envelope `{data: [...]}`."""
    if isinstance(body, list):
        rows = body
    elif isinstance(body, dict):
        rows = body.get("data") or body.get("templates") or []
        if isinstance(rows, dict):
            rows = rows.get("data") or []
    else:
        rows = []
    catalog: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        catalog.append({
            "name": name,
            "language": str(row.get("language") or "").strip(),
            "status": str(row.get("status") or "").strip().lower(),
        })
    return catalog


def _language(value: object) -> str:
    text = str(value or "pt_BR").strip() or "pt_BR"
    return text


def _norm_language(value: object) -> str:
    return _language(value).lower().replace("-", "_")


def configured_official(rules: dict | None, template_key: str | None) -> dict | None:
    """Nome cadastrado para a etapa. Ainda não é aprovação da Meta."""
    if not template_key:
        return None
    raw = ((rules or {}).get("whatsapp_templates") or {}).get(template_key)
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    raw_params = raw.get("params")
    params = raw_params if isinstance(raw_params, list) else []
    return {
        "name": name,
        "language": _language(raw.get("language")),
        "params": [str(item) for item in params],
    }


def _whatsapp_template_keys(rules: dict | None) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for step in parse_steps(rules):
        if step.handoff or "whatsapp" not in step.channels or not step.template:
            continue
        keys.append((step.key, step.template))
    return keys


def _catalog_has(catalog: list[dict], name: str, language: str) -> bool:
    wanted_name = name.strip().lower()
    wanted_lang = _norm_language(language)
    for item in catalog:
        if str(item.get("status") or "") != APPROVED_STATUS:
            continue
        if str(item.get("name") or "").strip().lower() != wanted_name:
            continue
        if _norm_language(item.get("language")) == wanted_lang:
            return True
    return False


def activation_blockers(rules: dict | None, state: str | None, catalog: list[dict]) -> list[str]:
    """O que impede ligar a régua. Vazio quando o número está pareado e cada
    etapa de WhatsApp tem template aprovado na Meta."""
    missing: list[str] = []
    if (state or "").strip().lower() != PAIRED_STATE:
        missing.append(MISSING_PAIRING)
    pending = [
        step_key
        for step_key, template_key in _whatsapp_template_keys(rules)
        if (spec := configured_official(rules, template_key)) is None
        or not _catalog_has(catalog, spec["name"], spec["language"])
    ]
    if pending:
        missing.append(MISSING_TEMPLATE)
    return missing


def approved_snapshot(rules: dict | None, catalog: list[dict]) -> dict:
    """Cópia do que a Meta aprovou. O disparo só consulta esta cópia."""
    snapshot: dict = {}
    for _step_key, template_key in _whatsapp_template_keys(rules):
        if template_key in snapshot:
            continue
        spec = configured_official(rules, template_key)
        if spec is None or not _catalog_has(catalog, spec["name"], spec["language"]):
            continue
        snapshot[template_key] = spec
    return snapshot


def commit_activation(tenant, state: str | None, catalog: list[dict]) -> list[str]:
    """Liga a conta e grava os templates aprovados. Se faltar algo, não muda a conta."""
    missing = activation_blockers(tenant.dunning_rules, state, catalog)
    if missing:
        return missing
    rules = dict(tenant.dunning_rules or {})
    rules["approved_templates"] = approved_snapshot(tenant.dunning_rules, catalog)
    tenant.dunning_rules = rules
    tenant.active = True
    return []


def approved_for(rules: dict | None, template_key: str | None) -> dict | None:
    """Template que a ativação gravou. Nome solto em `whatsapp_templates` não dispara."""
    if not template_key or not isinstance(rules, dict):
        return None
    spec = (rules.get("approved_templates") or {}).get(template_key)
    if not isinstance(spec, dict):
        return None
    name = str(spec.get("name") or "").strip()
    if not name:
        return None
    raw_params = spec.get("params")
    params = raw_params if isinstance(raw_params, list) else []
    return {
        "name": name,
        "language": _language(spec.get("language")),
        "params": [str(item) for item in params],
    }


def preserve_approved(previous: dict | None, new_rules: dict) -> dict:
    """Configuração nova não inventa aprovação. Mantém a cópia se o nome e o idioma
    continuam os mesmos; troca de nome exige ativar de novo."""
    approved = (previous or {}).get("approved_templates") or {}
    rules = dict(new_rules)
    rules.pop("approved_templates", None)
    if not isinstance(approved, dict):
        return rules
    configured = rules.get("whatsapp_templates") or {}
    kept: dict = {}
    for key, spec in approved.items():
        if not isinstance(spec, dict):
            continue
        current = configured.get(key)
        if not isinstance(current, dict):
            continue
        prev_name = str(spec.get("name") or "").strip()
        next_name = str(current.get("name") or "").strip()
        prev_lang = _language(spec.get("language"))
        next_lang = _language(current.get("language"))
        if not prev_name or prev_name != next_name or prev_lang != next_lang:
            continue
        raw_params = current.get("params")
        params = raw_params if isinstance(raw_params, list) else spec.get("params") or []
        kept[key] = {
            "name": prev_name,
            "language": prev_lang,
            "params": [str(p) for p in params],
        }
    if kept:
        rules["approved_templates"] = kept
    return rules


def read_evolution(client, instance: str) -> tuple[str | None, list[dict]]:
    """Estado e catálogo. Falha de rede conta como número sem parear e sem template."""
    state = None
    catalog: list[dict] = []
    try:
        state = client.connection_state(instance)
    except Exception:
        log.warning("dunning.pairing_unread", instance=instance)
    try:
        catalog = client.list_templates(instance) or []
    except Exception:
        log.warning("dunning.templates_unread", instance=instance)
        catalog = []
    return state, catalog
