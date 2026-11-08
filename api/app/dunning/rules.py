"""Régua de cobrança (FLUXOS.md §5). Funções puras: nada aqui fala com banco ou rede."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_DUNNING_RULES: dict = {
    "steps": [
        {"key": "D-3", "offset": -3, "channels": ["whatsapp"], "template": "lembrete"},
        {"key": "D0", "offset": 0, "channels": ["whatsapp"], "template": "vencimento_hoje"},
        {"key": "D+1", "offset": 1, "channels": ["whatsapp"], "template": "segunda_via"},
        {"key": "D+3", "offset": 3, "channels": ["whatsapp"], "template": "desconto_vista"},
        {"key": "D+5", "offset": 5, "channels": ["whatsapp"], "template": "oferta_negociacao"},
        {"key": "D+7", "offset": 7, "channels": ["whatsapp"], "template": "parcelamento"},
        {"key": "D+10", "offset": 10, "channels": ["whatsapp"], "template": "entrada_saldo"},
        {"key": "D+15", "offset": 15, "channels": ["whatsapp", "email"], "template": "ultima_tentativa"},
        {"key": "D+21", "offset": 21, "channels": ["whatsapp"], "template": "aviso_restricao"},
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
        "desconto_vista": (
            "Olá, {nome}. {descricao} ({valor}) venceu em {vencimento}. "
            "Se quitar à vista hoje pelo PIX, o valor fica com 15% de desconto. PIX: {pix}"
        ),
        "oferta_negociacao": (
            "Olá, {nome}. Sabemos que imprevistos acontecem. Se precisar, podemos combinar "
            "uma forma de pagamento para {descricao}. É só responder esta mensagem."
        ),
        "parcelamento": (
            "Olá, {nome}. Dá para parcelar {descricao} ({valor}), vencido em {vencimento}, "
            "em até 6 vezes. Responda com o número de parcelas que cabe no mês."
        ),
        "entrada_saldo": (
            "Olá, {nome}. Para regularizar {descricao} ({valor}), combinamos uma entrada "
            "agora e o saldo em 3 parcelas. O PIX da entrada é {pix}. "
            "Se a entrada precisar ser outra, é só responder."
        ),
        "ultima_tentativa": (
            "Olá, {nome}. Esta é nossa última mensagem automática sobre {descricao} "
            "({valor}). Depois dela, o atendimento passa para nossa equipe."
        ),
        "aviso_restricao": (
            "Olá, {nome}. {descricao} ({valor}) segue em aberto desde {vencimento}. "
            "Esta é a última oferta antes de o caso ir para análise da equipe, "
            "com possível restrição do nome. Quite pelo PIX {pix} ou responda para negociar."
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
