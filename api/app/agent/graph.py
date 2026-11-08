"""Agente de negociação (FLUXOS.md §7) como grafo de estados explícito.

Cada mensagem do devedor é um turno: o grafo roda do início até um END ou até o
`interrupt` de aprovação humana. A memória (opções apresentadas, identidade
confirmada) fica no checkpointer, com `thread_id` = id da conversa.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent import tools
from app.agent.intent import ChoiceResult, interpret_choice
from app.agent.policy import brl
from app.agent.prompts import ANSWER_SYSTEM, GUARDRAILS
from app.core.config import get_settings
from app.core.llm import get_chat_model, llm_callbacks
from app.models.enums import Intent


class AgentState(TypedDict, total=False):
    tenant_id: str
    tenant_name: str
    conversation_id: str
    debtor_id: str
    debtor_document: str
    thread_id: str
    today: str
    text: str
    intent: str
    identity_verified: bool
    identity_verified_on: str
    awaiting_identity: bool
    identity_attempts: int
    pending_text: str | None
    pending_intent: str | None
    invoices: list[dict]
    options: list[dict]
    chosen_option: str | None
    awaiting_choice: bool
    approval_reason: str
    replies: list[str]
    outcome: str


def _answer_question(state: AgentState) -> str:
    listing = "\n".join(
        f"- {i['description']}: {brl(Decimal(i['amount_open']))}, "
        f"vencimento {i['due_date']}, pagamento: "
        f"{i.get('payment_url') or i.get('pix_copy_paste') or 'sob consulta'}"
        for i in state.get("invoices", [])
    )
    system = ANSWER_SYSTEM.format(
        tenant=state.get("tenant_name", ""), invoices=listing, guardrails=GUARDRAILS,
    )
    response = get_chat_model().invoke(
        [SystemMessage(system), HumanMessage(state["text"])],
        config={"callbacks": llm_callbacks(), "run_name": "negotiation_answer"},
    )
    return str(response.content)


@dataclass
class AgentDeps:
    """Dependências injetáveis, para testar o grafo sem banco e sem LLM."""

    get_invoices: Callable[[str, str], list[dict]] = lambda t, d: tools.get_debtor_invoices.invoke(
        {"tenant_id": t, "debtor_id": d}
    )
    get_policy: Callable[[str], dict] = lambda t: tools.get_negotiation_policy.invoke(
        {"tenant_id": t}
    )
    build_options: Callable[..., list[dict]] = lambda total, policy, today: (
        tools.build_options.invoke({"total_open": total, "policy": policy, "today": today})
    )
    create_agreement: Callable[..., dict] = lambda **kw: tools.create_agreement.invoke(kw)
    request_human: Callable[..., str] = lambda **kw: tools.request_human.invoke(kw)
    interpret_choice: Callable[[str, list[dict]], ChoiceResult] = interpret_choice
    answer_question: Callable[[AgentState], str] = _answer_question
    max_identity_attempts: int = field(default_factory=lambda: get_settings().identity_max_attempts)


def numbered_choice(text: str, options: list[dict]) -> ChoiceResult | None:
    """A lista sai numerada a partir de 1. '6' é a sexta opção, sem passar pelo modelo."""
    if not re.fullmatch(r"\d{1,2}", text.strip()):
        return None
    index = int(text.strip()) - 1
    if index < 0 or index >= len(options):
        return ChoiceResult(decision="outro")
    return ChoiceResult(decision="aceita", option_id=options[index]["id"])


def identity_matches(text: str, document: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return bool(digits) and (digits == document or digits[:3] == document[:3] and len(digits) == 3)


def _reply(state: AgentState, *messages: str) -> list[str]:
    return [*state.get("replies", []), *messages]


def _parcel_line(invoice: dict) -> str:
    code = invoice.get("pix_copy_paste") or invoice.get("digitable_line")
    amount = brl(Decimal(invoice["amount_open"]))
    return f"- {invoice['description']}: {amount} em {invoice['due_date']}\n  Código: {code}"


def build_graph(deps: AgentDeps | None = None, checkpointer: Any = None):
    deps = deps or AgentDeps()

    def entry(state: AgentState) -> str:
        # A identidade confirmada vale só no dia; no dia seguinte pergunta de novo.
        if state.get("identity_verified") and state.get("identity_verified_on") == state["today"]:
            return "consultar_titulos"
        if state.get("awaiting_identity"):
            return "verificar_identidade"
        return "pedir_identidade"

    def pedir_identidade(state: AgentState) -> AgentState:
        return {
            "awaiting_identity": True,
            "pending_text": state["text"],
            "pending_intent": state.get("intent"),
            "replies": _reply(
                state,
                "Para sua segurança, antes de falar de valores preciso confirmar seus dados. "
                "Pode me informar os 3 primeiros dígitos do seu CPF/CNPJ?",
            ),
        }

    def verificar_identidade(state: AgentState) -> AgentState:
        if identity_matches(state["text"], state["debtor_document"]):
            return {
                "identity_verified": True,
                "identity_verified_on": state["today"],
                "awaiting_identity": False,
                "identity_attempts": 0,
                "text": state.get("pending_text") or state["text"],
                "intent": state.get("pending_intent") or state.get("intent"),
                "replies": _reply(state, "Obrigado, dados confirmados!"),
            }
        attempts = state.get("identity_attempts", 0) + 1
        if attempts >= deps.max_identity_attempts:
            return {
                "identity_attempts": attempts,
                "awaiting_identity": False,
                "outcome": "identidade_falhou",
                "replies": _reply(
                    state,
                    "Não consegui confirmar seus dados. Alguém da nossa equipe vai falar com você.",
                ),
            }
        return {
            "identity_attempts": attempts,
            "replies": _reply(state, "Os dígitos não conferem. Pode verificar e enviar de novo?"),
        }

    def after_identity(state: AgentState) -> str:
        return "consultar_titulos" if state.get("identity_verified") else END

    def consultar_titulos(state: AgentState) -> AgentState:
        return {"invoices": deps.get_invoices(state["tenant_id"], state["debtor_id"])}

    def classificar_pedido(state: AgentState) -> str:
        if not state.get("invoices"):
            return "sem_pendencias"
        if state.get("awaiting_choice"):
            return "aguardar_aceite"
        if state.get("intent") == Intent.PARCELAR_DESCONTO:
            return "gerar_propostas"
        return "responder"

    def sem_pendencias(state: AgentState) -> AgentState:
        return {
            "awaiting_choice": False,
            "outcome": "sem_pendencias",
            "replies": _reply(
                state, "Não encontrei pendências em aberto no seu nome. Posso ajudar em algo mais?",
            ),
        }

    def gerar_propostas(state: AgentState) -> AgentState:
        total = sum((Decimal(i["amount_open"]) for i in state["invoices"]), Decimal("0"))
        policy = deps.get_policy(state["tenant_id"])
        options = deps.build_options(total, policy, date.fromisoformat(state["today"]))
        return {"options": options}

    def has_options(state: AgentState) -> str:
        return "apresentar_opcoes" if state.get("options") else "pedir_aprovacao"

    def apresentar_opcoes(state: AgentState) -> AgentState:
        lines = [f"{n}) {o['label']}" for n, o in enumerate(state["options"], start=1)]
        return {
            "awaiting_choice": True,
            "replies": _reply(
                state,
                "Posso oferecer estas condições:\n" + "\n".join(lines) + "\n\nQual prefere?",
            ),
        }

    def aguardar_aceite(state: AgentState) -> AgentState:
        options = state.get("options") or []
        choice = numbered_choice(state["text"], options)
        if choice is None:
            choice = deps.interpret_choice(state["text"], options)
            valid_ids = {o["id"] for o in options}
            if choice.decision == "aceita" and choice.option_id not in valid_ids:
                choice = ChoiceResult(decision="outro")
        return {"outcome": f"escolha:{choice.decision}", "chosen_option": choice.option_id}

    def route_choice(state: AgentState) -> str:
        decision = state["outcome"].split(":", 1)[1]
        return {
            "aceita": "criar_acordo",
            "recusa": "encerrar",
            "fora_da_politica": "pedir_aprovacao",
        }.get(decision, "repetir_opcoes")

    def repetir_opcoes(state: AgentState) -> AgentState:
        return {
            "replies": _reply(
                state, "Não entendi qual opção você prefere. Pode responder com o número?",
            ),
        }

    def criar_acordo(state: AgentState) -> AgentState:
        try:
            result = deps.create_agreement(
                tenant_id=state["tenant_id"],
                debtor_id=state["debtor_id"],
                invoice_ids=[i["id"] for i in state["invoices"]],
                option_id=state["chosen_option"],
                today=state["today"],
            )
        except (ValueError, httpx.HTTPError, NotImplementedError) as exc:
            return {
                "awaiting_choice": False,
                "outcome": "emitir_falhou",
                "approval_reason": f"Acordo não registrado: {exc}",
            }
        parcels = "\n".join(_parcel_line(i) for i in result["invoices"])
        return {
            "awaiting_choice": False,
            "options": [],
            "chosen_option": None,
            "outcome": "acordo",
            "replies": _reply(
                state,
                f"Combinado! Acordo registrado: {result['label']}.\n{parcels}",
            ),
        }

    def encerrar(state: AgentState) -> AgentState:
        return {
            "awaiting_choice": False,
            "options": [],
            "outcome": "recusa",
            "replies": _reply(state, "Tudo bem. Se mudar de ideia, é só me chamar por aqui."),
        }

    def after_create(state: AgentState) -> str:
        return "pedir_aprovacao" if state.get("outcome") == "emitir_falhou" else END

    def pedir_aprovacao(state: AgentState) -> AgentState:
        deps.request_human(
            tenant_id=state["tenant_id"],
            conversation_id=state["conversation_id"],
            thread_id=state["thread_id"],
            reason=state.get("approval_reason") or f"Pedido do devedor: {state['text']}",
            payload={"invoices": state.get("invoices", []), "options": state.get("options", [])},
        )
        return {
            "awaiting_choice": False,
            "outcome": "aguardando_aprovacao",
            "replies": _reply(state, "Vou levar seu pedido para nossa equipe e retorno em breve."),
        }

    def aguardar_humano(state: AgentState) -> AgentState:
        decision = interrupt({"conversation_id": state["conversation_id"]})
        message = decision.get("message")
        return {
            "outcome": "aprovado" if decision.get("approved") else "rejeitado",
            "replies": [message] if message else [],
        }

    def responder(state: AgentState) -> AgentState:
        return {"outcome": "resposta", "replies": _reply(state, deps.answer_question(state))}

    g = StateGraph(AgentState)
    for name, fn in [
        ("pedir_identidade", pedir_identidade),
        ("verificar_identidade", verificar_identidade),
        ("consultar_titulos", consultar_titulos),
        ("sem_pendencias", sem_pendencias),
        ("gerar_propostas", gerar_propostas),
        ("apresentar_opcoes", apresentar_opcoes),
        ("aguardar_aceite", aguardar_aceite),
        ("repetir_opcoes", repetir_opcoes),
        ("criar_acordo", criar_acordo),
        ("encerrar", encerrar),
        ("pedir_aprovacao", pedir_aprovacao),
        ("aguardar_humano", aguardar_humano),
        ("responder", responder),
    ]:
        g.add_node(name, fn)

    g.add_conditional_edges(
        START, entry, ["pedir_identidade", "verificar_identidade", "consultar_titulos"],
    )
    g.add_edge("pedir_identidade", END)
    g.add_conditional_edges("verificar_identidade", after_identity, ["consultar_titulos", END])
    g.add_conditional_edges(
        "consultar_titulos", classificar_pedido,
        ["sem_pendencias", "aguardar_aceite", "gerar_propostas", "responder"],
    )
    g.add_conditional_edges(
        "gerar_propostas", has_options, ["apresentar_opcoes", "pedir_aprovacao"],
    )
    g.add_conditional_edges(
        "aguardar_aceite", route_choice,
        ["criar_acordo", "encerrar", "pedir_aprovacao", "repetir_opcoes"],
    )
    g.add_conditional_edges("criar_acordo", after_create, ["pedir_aprovacao", END])
    g.add_edge("pedir_aprovacao", "aguardar_humano")
    for terminal in ["sem_pendencias", "apresentar_opcoes", "repetir_opcoes",
                     "encerrar", "aguardar_humano", "responder"]:
        g.add_edge(terminal, END)

    return g.compile(checkpointer=checkpointer)
