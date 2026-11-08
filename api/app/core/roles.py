"""Papéis da empresa. O dono configura. O financeiro confirma a baixa. O atendente não."""

CONFIGURE_ROLES = frozenset({"dono", "operador"})
SETTLE_ROLES = frozenset({"financeiro", "dono", "operador"})
COMPANY_ROLES = frozenset({"dono", "financeiro", "atendente"})


def can_configure(role: str) -> bool:
    return role in CONFIGURE_ROLES


def can_settle(role: str) -> bool:
    return role in SETTLE_ROLES
