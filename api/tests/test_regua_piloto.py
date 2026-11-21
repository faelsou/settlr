"""SETL-65: piloto compara a régua de dez etapas com a de quatro na mesma carteira."""

import hashlib
from datetime import date, timedelta
from uuid import UUID, uuid4

from app.dunning.rules import (
    DEFAULT_DUNNING_RULES,
    VARIANT_FULL,
    VARIANT_SHORT,
    decide,
    parse_steps,
    regua_variant,
    short_share,
    steps_for_invoice,
    variant_bucket,
)

PILOTO = {**DEFAULT_DUNNING_RULES, "piloto_regua": {"quatro_etapas_pct": 50}}
IDS = [UUID(int=i * 7919 + 1) for i in range(4000)]


def _disparos(rules: dict, invoice_id: UUID) -> list[str]:
    """Simula a régua dia a dia, do D-3 ao D+30, e devolve as etapas enviadas."""
    due = date(2026, 11, 1)
    sent: set[tuple[str, str]] = set()
    keys: list[str] = []
    for day in range(-3, 31):
        decision = decide(
            today=due + timedelta(days=day),
            due_date=due,
            steps=steps_for_invoice(rules, invoice_id),
            opt_out=False,
            active_promise=None,
            sent=sent,
        )
        if decision.action == "send":
            sent |= {(decision.step.key, ch) for ch in decision.channels}
            keys.append(decision.step.key)
        if decision.action == "handoff":
            keys.append("fila_humana")
            break
    return keys


def test_sem_piloto_todo_titulo_roda_a_regua_inteira() -> None:
    assert short_share(DEFAULT_DUNNING_RULES) is None
    assert short_share({**DEFAULT_DUNNING_RULES, "piloto_regua": None}) is None
    invoice_id = uuid4()
    assert regua_variant(DEFAULT_DUNNING_RULES, invoice_id) is None
    assert steps_for_invoice(DEFAULT_DUNNING_RULES, invoice_id) == parse_steps(None)


def test_variante_curta_so_dispara_d0_d1_d5_d15() -> None:
    curto = next(i for i in IDS if regua_variant(PILOTO, i) == VARIANT_SHORT)
    longo = next(i for i in IDS if regua_variant(PILOTO, i) == VARIANT_FULL)

    assert _disparos(PILOTO, curto) == ["D0", "D+1", "D+5", "D+15", "fila_humana"]
    assert _disparos(PILOTO, longo) == [
        "D-3", "D0", "D+1", "D+3", "D+5", "D+7", "D+10", "D+15", "D+21", "fila_humana",
    ]


def test_titulo_nao_troca_de_variante_entre_execucoes() -> None:
    for invoice_id in IDS[:200]:
        primeira = regua_variant(PILOTO, invoice_id)
        assert regua_variant(PILOTO, invoice_id) == primeira
        assert regua_variant(PILOTO, str(invoice_id)) == primeira


def test_proporcao_segue_o_percentual_configurado() -> None:
    for pct in (0, 25, 50, 100):
        rules = {**DEFAULT_DUNNING_RULES, "piloto_regua": {"quatro_etapas_pct": pct}}
        curtos = sum(regua_variant(rules, i) == VARIANT_SHORT for i in IDS)
        assert abs(curtos / len(IDS) - pct / 100) < 0.03, (pct, curtos)


def test_aumentar_o_percentual_so_move_titulos_da_longa_para_a_curta() -> None:
    menor = {**DEFAULT_DUNNING_RULES, "piloto_regua": {"quatro_etapas_pct": 30}}
    maior = {**DEFAULT_DUNNING_RULES, "piloto_regua": {"quatro_etapas_pct": 60}}
    for invoice_id in IDS[:500]:
        if regua_variant(menor, invoice_id) == VARIANT_SHORT:
            assert regua_variant(maior, invoice_id) == VARIANT_SHORT


def test_corte_da_variante_e_independente_de_um_grupo_de_controle() -> None:
    """O grupo de controle (SETL-50) sorteia com outro sal. Os 10% do controle não podem
    cair todos numa variante, senão o controle distorce a comparação."""

    def controle(invoice_id: UUID) -> bool:
        digest = hashlib.sha256(f"grupo-controle:{invoice_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % 100 < 10

    restantes = [i for i in IDS if not controle(i)]
    curtos = sum(variant_bucket(i) < 50 for i in restantes)
    assert abs(curtos / len(restantes) - 0.5) < 0.03
