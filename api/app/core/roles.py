"""Papéis da empresa. O dono configura. O financeiro confirma a baixa. O atendente não."""

# Até o RBAC v2 (SETL-71), só o dono mexe em política, régua e templates (SETL-69).
CONFIGURE_ROLES = frozenset({"dono"})
SETTLE_ROLES = frozenset({"financeiro", "dono", "operador"})
COMPANY_ROLES = frozenset({"dono", "financeiro", "atendente"})
# Papéis que um token pode carregar. Fora disso, ou sem papel, a API responde 403 (SETL-68).
KNOWN_ROLES = COMPANY_ROLES | SETTLE_ROLES | {"agencia"}


def can_configure(role: str) -> bool:
    return role in CONFIGURE_ROLES


def can_settle(role: str) -> bool:
    return role in SETTLE_ROLES
