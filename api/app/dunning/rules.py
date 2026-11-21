"""Régua de cobrança (FLUXOS.md §5). Funções puras: nada aqui fala com banco ou rede."""

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

# Versão dos textos canônicos. O dossiê é docs/TEXTOS-REGUA.md. O parecer fica no SETL-15.
TEXT_VERSION = "2026-11-08"

DEFAULT_DUNNING_RULES: dict = {
    "text_version": TEXT_VERSION,
    "steps": [
        {"key": "D-3", "offset": -3, "channels": ["whatsapp"], "template": "lembrete"},
        {"key": "D0", "offset": 0, "channels": ["whatsapp"], "template": "vencimento_hoje"},
        {"key": "D+1", "offset": 1, "channels": ["whatsapp"], "template": "segunda_via"},
        {"key": "D+3", "offset": 3, "channels": ["whatsapp"], "template": "convite_quitar"},
        {"key": "D+5", "offset": 5, "channels": ["whatsapp"], "template": "oferta_negociacao"},
        {"key": "D+7", "offset": 7, "channels": ["whatsapp"], "template": "convite_conversa"},
        {"key": "D+10", "offset": 10, "channels": ["whatsapp"], "template": "lembrete_aberto"},
        {
            "key": "D+15",
            "offset": 15,
            "channels": ["whatsapp", "email"],
            "template": "ultima_tentativa",
        },
        {"key": "D+21", "offset": 21, "channels": ["whatsapp"], "template": "aviso_equipe"},
        {"key": "D+30", "offset": 30, "channels": [], "template": None, "handoff": True},
    ],
    "templates": {
        "lembrete": (
            "Olá, {nome}! Passando para lembrar que o pagamento de {descricao} no valor de "
            "{valor} vence em {vencimento}. PIX copia e cola: {pix}"
        ),
        "vencimento_hoje": (
            "Olá, {nome}. O pagamento de {descricao} ({valor}) vence hoje. PIX: {pix}"
        ),
        "segunda_via": (
            "Olá, {nome}. Ainda não identificamos o pagamento de {descricao} ({valor}), "
            "vencido em {vencimento}. Segue a segunda via: {link}. Se já pagou, é só "
            "responder com o comprovante."
        ),
        "convite_quitar": (
            "Olá, {nome}. {descricao} ({valor}) venceu em {vencimento}. "
            "O PIX para quitar é {pix}. Se precisar de outra forma, responda esta mensagem."
        ),
        "oferta_negociacao": (
            "Olá, {nome}. Sabemos que imprevistos acontecem. Se precisar, podemos combinar "
            "uma forma de pagamento para {descricao}. É só responder esta mensagem."
        ),
        "convite_conversa": (
            "Olá, {nome}. {descricao} ({valor}) segue em aberto desde {vencimento}. "
            "Se quiser conversar sobre o pagamento, responda esta mensagem. "
            "O PIX para quitar é {pix}."
        ),
        "lembrete_aberto": (
            "Olá, {nome}. {descricao} ({valor}) segue em aberto desde {vencimento}. "
            "O PIX para quitar é {pix}. Se a forma precisar ser outra, responda esta mensagem."
        ),
        "ultima_tentativa": (
            "Olá, {nome}. Esta é nossa última mensagem automática sobre {descricao} "
            "({valor}). Depois dela, o atendimento passa para nossa equipe."
        ),
        "aviso_equipe": (
            "Olá, {nome}. {descricao} ({valor}) segue em aberto desde {vencimento}. "
            "Esta mensagem é automática. Depois dela, a equipe assume o atendimento. "
            "Quite pelo PIX {pix} ou responda se quiser conversar."
        ),
    },
}

DEFAULT_ALLOWED_HOURS: dict = {"start": "08:00", "end": "20:00", "weekdays": [0, 1, 2, 3, 4, 5]}


@dataclass(frozen=True)
class Step:
    key: str
    offset: int
    channels: tuple[str, ...]
    template: str | None
    handoff: bool = False


@dataclass(frozen=True)
class AllowedHours:
    start: time
    end: time
    weekdays: frozenset[int] = field(default_factory=lambda: frozenset(range(6)))

    @classmethod
    def from_json(cls, data: dict | None) -> "AllowedHours":
        data = data or DEFAULT_ALLOWED_HOURS
        return cls(
            start=time.fromisoformat(data.get("start", "08:00")),
            end=time.fromisoformat(data.get("end", "20:00")),
            weekdays=frozenset(data.get("weekdays", range(6))),
        )


def parse_steps(rules: dict | None) -> list[Step]:
    raw = (rules or DEFAULT_DUNNING_RULES).get("steps") or DEFAULT_DUNNING_RULES["steps"]
    steps = [
        Step(
            key=s["key"],
            offset=int(s["offset"]),
            channels=tuple(s.get("channels", [])),
            template=s.get("template"),
            handoff=bool(s.get("handoff", False)),
        )
        for s in raw
    ]
    return sorted(steps, key=lambda s: s.offset)


# Piloto da régua curta (PRODUTO.md §5, SETL-65). Liga em `dunning_rules.piloto_regua`.
VARIANT_FULL = "dez_etapas"
VARIANT_SHORT = "quatro_etapas"
SHORT_STEP_KEYS = frozenset({"D0", "D+1", "D+5", "D+15"})
# Sal próprio do piloto: o grupo de controle (SETL-50) sorteia com outro sal, então os
# dois cortes são independentes e o controle sai antes de qualquer variante.
_VARIANT_SALT = "regua-piloto:"


def variant_bucket(invoice_id: UUID | str) -> int:
    """0 a 99, fixo para o mesmo título."""
    digest = hashlib.sha256(f"{_VARIANT_SALT}{invoice_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 100


def short_share(rules: dict | None) -> int | None:
    """Percentual de títulos na régua de quatro etapas, ou None sem piloto."""
    pilot = (rules or {}).get("piloto_regua")
    if not isinstance(pilot, dict):
        return None
    try:
        share = int(pilot.get("quatro_etapas_pct", 50))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, share))


def regua_variant(rules: dict | None, invoice_id: UUID | str) -> str | None:
    share = short_share(rules)
    if share is None:
        return None
    return VARIANT_SHORT if variant_bucket(invoice_id) < share else VARIANT_FULL


def steps_for_invoice(rules: dict | None, invoice_id: UUID | str) -> list[Step]:
    """Etapas do título. Na variante curta só disparam D0, D+1, D+5 e D+15; a passagem
    para a fila humana continua no fim da régua."""
    steps = parse_steps(rules)
    if regua_variant(rules, invoice_id) != VARIANT_SHORT:
        return steps
    return [s for s in steps if s.key in SHORT_STEP_KEYS or s.handoff]


def within_allowed_hours(now: datetime, hours: AllowedHours, tz: str) -> bool:
    local = now.astimezone(ZoneInfo(tz))
    return local.weekday() in hours.weekdays and hours.start <= local.time() < hours.end


def current_step(today: date, due_date: date, steps: list[Step]) -> Step | None:
    """Etapa vigente: a de maior offset já alcançado. Se o ciclo atrasar, envia só a
    etapa mais recente, nunca uma rajada das anteriores."""
    days = (today - due_date).days
    reached = [s for s in steps if s.offset <= days]
    return reached[-1] if reached else None


def promise_pauses(today: date, promised_date: date | None) -> bool:
    """Promessa ativa pausa a régua até `data_prometida + 1`."""
    return promised_date is not None and today <= promised_date + timedelta(days=1)


@dataclass(frozen=True)
class DunningDecision:
    action: str  # "send" | "skip" | "handoff"
    step: Step | None = None
    channels: tuple[str, ...] = ()
    reason: str = ""


def decide(
    *,
    today: date,
    due_date: date,
    steps: list[Step],
    opt_out: bool,
    active_promise: date | None,
    sent: set[tuple[str, str]],
    has_payment_code: bool = True,
) -> DunningDecision:
    """Decide o que fazer com um título neste ciclo. A checagem de horário e de rate
    limit fica no chamador, porque depende do relógio e do Redis."""
    if opt_out:
        return DunningDecision("skip", reason="opt_out")
    if promise_pauses(today, active_promise):
        return DunningDecision("skip", reason="promessa_ativa")
    if not has_payment_code:
        return DunningDecision("skip", reason="sem_meio_pagamento")

    step = current_step(today, due_date, steps)
    if step is None:
        return DunningDecision("skip", reason="antes_da_regua")
    if step.handoff:
        return DunningDecision("handoff", step, reason="fim_da_regua")

    pending = tuple(ch for ch in step.channels if (step.key, ch) not in sent)
    if not pending:
        return DunningDecision("skip", step, reason="etapa_ja_enviada")
    return DunningDecision("send", step, pending)
