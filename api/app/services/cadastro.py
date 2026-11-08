"""Cadastro: títulos, configuração, métricas, agência e o webhook do emissor."""

from app.api.routes import admin, debtors, invoices, members, metrics, onboarding, settings
from app.api.routes.webhooks import issuer_router
from app.services.runtime import create_service

app = create_service(
    "cadastro",
    [
        issuer_router,
        invoices.router,
        debtors.router,
        settings.router,
        onboarding.router,
        members.router,
        metrics.router,
        admin.router,
    ],
)
