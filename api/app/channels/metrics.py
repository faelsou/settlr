"""Contadores do WhatsApp para o Grafana.

Cada mensagem entra uma vez em `aceita` (webhook ou sincronização) e uma vez em
`roteada` (contexto). Cada saída conta em `enviada` quando a Evolution aceita.
O recibo do aparelho conta em `recibo`, com contexto `entregue`, `lido` ou `falhou`.
Arquivo tem contador próprio:
recebido ou entregue, ok ou falha.

O processo expõe `cobranca_whatsapp_*` em `/internal/metrics`. Com o coletor OTLP
ligado, o mesmo evento sai como `whatsapp_messages_total` e `whatsapp_files_total`.
O painel lê o OTLP e, se ele não existir, o scrape.
"""

from __future__ import annotations

from opentelemetry import metrics as otel_metrics
from prometheus_client import Counter

from app.core.logging import get_logger
from app.models.enums import Intent

log = get_logger(__name__)

MESSAGES = Counter(
    "cobranca_whatsapp_messages",
    "Mensagens de WhatsApp por direção, etapa, contexto e resultado.",
    ["direction", "stage", "context", "kind", "result"],
)
FILES = Counter(
    "cobranca_whatsapp_files",
    "Arquivos de WhatsApp recebidos ou entregues, ok ou com falha.",
    ["direction", "result", "reason"],
)

_INTENTS = {item.value for item in Intent}
_ROUTE = {
    "pede_comprovante": "comprovante",
    "pede_data": "promessa",
    "promessa_recusada": "promessa",
    "promessa": "promessa",
    "opt_out": "opt_out",
    "escalonado": "escalonado",
    "contestacao": "contestacao",
    "aguardando_aprovacao": "aprovacao",
    "sem_texto_ou_humano": "humano",
    "agente": "agente",
    "grupo": "grupo",
    "contato_desconhecido": "contato_desconhecido",
    "webhook": "webhook",
    "sync": "sync",
    "ignorado": "ignorado",
    "instancia_desconhecida": "instancia_desconhecida",
    "regua": "regua",
    "operador": "operador",
    "comprovante": "comprovante",
    "aprovacao": "aprovacao",
    "humano": "humano",
    "roteamento": "roteamento",
}
_STAGES = {"aceita", "roteada", "enviada", "recibo"}
_RECEIPT = {"entregue", "lido", "falhou", "sem_recibo"}
_KINDS = {"texto", "arquivo"}
_FILE_OK = {"duplicado", "ja_recebido", "aguardando_banco", "armazenado"}
_FILE_FAIL = {"baixa_confianca", "download", "processamento", "envio"}

_otel_messages = None
_otel_files = None


def route_context(outcome: str, intent: str | None = None) -> str:
    """Contexto estável para o rótulo. Intenção conhecida ganha do apelido da rota."""
    if outcome in {"grupo", "contato_desconhecido", "humano", "aprovacao"}:
        return outcome
    if intent in _INTENTS:
        return intent
    return _ROUTE.get(outcome, "outro")


def outbound_context(author: str, intent: str | None) -> str:
    if author.startswith("regua"):
        return "regua"
    if author != "agente":
        return "operador"
    if intent in _INTENTS:
        return intent
    return "agente"


def record_message(direction: str, stage: str, context: str, kind: str, result: str) -> None:
    direction = direction if direction in {"entrada", "saida"} else "entrada"
    stage = stage if stage in _STAGES else "roteada"
    context = context if context in _ROUTE.values() or context in _INTENTS or context in _RECEIPT else "outro"
    kind = kind if kind in _KINDS else "texto"
    result = result if result in {"ok", "falha"} else "falha"
    labels = {
        "direction": direction,
        "stage": stage,
        "context": context,
        "kind": kind,
        "result": result,
    }
    MESSAGES.labels(**labels).inc()
    _message_counter().add(1, labels)
    log.info("whatsapp.message", **labels)


def record_file(direction: str, reason: str) -> None:
    direction = direction if direction in {"recebido", "entregue"} else "recebido"
    if reason in _FILE_OK:
        result = "ok"
    else:
        result = "falha"
        if reason not in _FILE_FAIL:
            reason = "outro"
    labels = {"direction": direction, "result": result, "reason": reason}
    FILES.labels(**labels).inc()
    _file_counter().add(1, labels)
    log.info("whatsapp.file", **labels)


def _message_counter():
    global _otel_messages
    if _otel_messages is None:
        _otel_messages = otel_metrics.get_meter("app.channels").create_counter(
            "whatsapp_messages",
            description="Mensagens de WhatsApp por direção, etapa, contexto e resultado.",
            unit="1",
        )
    return _otel_messages


def _file_counter():
    global _otel_files
    if _otel_files is None:
        _otel_files = otel_metrics.get_meter("app.channels").create_counter(
            "whatsapp_files",
            description="Arquivos de WhatsApp recebidos ou entregues, ok ou com falha.",
            unit="1",
        )
    return _otel_files
