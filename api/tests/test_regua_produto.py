"""A tabela da régua padrão em docs/PRODUTO.md é a de DEFAULT_DUNNING_RULES."""

import re
from pathlib import Path

from app.dunning.rules import DEFAULT_DUNNING_RULES

PRODUTO = Path(__file__).resolve().parents[2] / "docs" / "PRODUTO.md"
_HEADING = "### Régua padrão (configurável)"
_STEP_KEY = re.compile(r"^D(?:0|[+-]\d+)$")
_CHANNEL = {
    "whatsapp template": "whatsapp",
    "whatsapp": "whatsapp",
    "e-mail": "email",
    "email": "email",
}


def _offset(key: str) -> int:
    if key == "D0":
        return 0
    sign, days = key[1], key[2:]
    value = int(days)
    return value if sign == "+" else -value


def _channels(cell: str) -> tuple[str, ...]:
    text = cell.strip().lower()
    if text == "painel":
        return ()
    parts = [part.strip() for part in text.split("+")]
    unknown = [part for part in parts if part not in _CHANNEL]
    assert not unknown, f"canal sem mapeamento na tabela: {cell!r}"
    return tuple(_CHANNEL[part] for part in parts)


def _produto_steps() -> list[tuple[str, int, tuple[str, ...]]]:
    lines = PRODUTO.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == _HEADING)
    rows: list[tuple[str, int, tuple[str, ...]]] = []
    in_table = False
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if not line.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        head = cells[0]
        if head in {"Momento", "---"} or set(head) <= {"-", ":"}:
            in_table = True
            continue
        if not _STEP_KEY.fullmatch(head):
            break
        in_table = True
        assert len(cells) >= 3, line
        rows.append((head, _offset(head), _channels(cells[2])))
    assert rows, "tabela da régua padrão não encontrada em PRODUTO.md"
    return rows


def test_default_dunning_rules_match_produto_table():
    documented = _produto_steps()
    coded = [
        (step["key"], int(step["offset"]), tuple(step["channels"]))
        for step in DEFAULT_DUNNING_RULES["steps"]
    ]
    assert documented == coded
