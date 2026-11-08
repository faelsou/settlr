"""Qual serviço responde cada caminho público. O gateway só encaminha."""

# Prefixo mais específico primeiro: /webhooks/evolution não pode cair em outro webhook.
PREFIXES: tuple[tuple[str, str], ...] = (
    ("/webhooks/evolution", "cobranca"),
    ("/webhooks/banco", "conciliacao"),
    ("/webhooks/emissor", "cadastro"),
    ("/conversations", "cobranca"),
    ("/approvals", "cobranca"),
    ("/payments", "conciliacao"),
    ("/exceptions", "conciliacao"),
    ("/invoices", "cadastro"),
    ("/debtors", "cadastro"),
    ("/settings", "cadastro"),
    ("/onboarding", "cadastro"),
    ("/members", "cadastro"),
    ("/metrics", "cadastro"),
    ("/admin", "cadastro"),
)


def owner_of(path: str) -> str | None:
    if not path.startswith("/"):
        path = "/" + path
    path = path.split("?", 1)[0]
    for prefix, owner in PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return owner
    return None
