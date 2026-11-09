"""Entrada de dinheiro sem arquivo: extrato do emissor e Open Finance."""

from dataclasses import dataclass
from datetime import date

import httpx

from app.core.logging import get_logger
from app.ingest.issuers import get_adapter
from app.models import Tenant
from app.models.enums import PaymentOrigin
from app.reconciliation.open_finance import OpenFinanceClient
from app.reconciliation.service import BankPaymentIn, register_bank_payment

log = get_logger(__name__)


@dataclass(frozen=True)
class FeedResult:
    created: list[str]
    duplicates: int
    sources: list[str]


def open_finance_config(tenant: Tenant) -> dict | None:
    feed = tenant.bank_feed or {}
    config = feed.get("open_finance") or {}
    if config.get("base_url") and config.get("token") and config.get("account_id"):
        return config
    return None


def pull_tenant(
    session,
    tenant: Tenant,
    *,
    since: date,
    today: date,
    issuer_client: httpx.Client | None = None,
    open_finance_client: httpx.Client | None = None,
) -> FeedResult:
    """Busca as duas fontes. Se as duas falharem, a exceção sobe para o retry do worker."""
    rows: list[BankPaymentIn] = []
    sources: list[str] = []
    errors: list[httpx.HTTPError] = []
    configured = 0

    if tenant.issuer_provider:
        configured += 1
        try:
            rows.extend(_issuer_rows(tenant, since, issuer_client))
            sources.append("emissor")
        except httpx.HTTPError as exc:
            errors.append(exc)
            log.warning(
                "statement.emissor_falhou",
                tenant_id=str(tenant.id),
                provider=tenant.issuer_provider,
            )

    of_config = open_finance_config(tenant)
    if of_config:
        configured += 1
        try:
            client = OpenFinanceClient(of_config, client=open_finance_client)
            rows.extend(client.statement(since, today))
            sources.append("open_finance")
        except httpx.HTTPError as exc:
            errors.append(exc)
            log.warning("statement.open_finance_falhou", tenant_id=str(tenant.id))

    if configured and len(errors) == configured:
        raise errors[-1]

    created: list[str] = []
    duplicates = 0
    for item in rows:
        payment = register_bank_payment(session, tenant.id, item, PaymentOrigin.EXTRATO)
        if payment is None:
            duplicates += 1
        else:
            created.append(str(payment.id))
    return FeedResult(created=created, duplicates=duplicates, sources=sources)


def _issuer_rows(tenant: Tenant, since: date, client: httpx.Client | None) -> list[BankPaymentIn]:
    try:
        adapter = get_adapter(tenant.issuer_provider, tenant.issuer_config or {}, client=client)
    except NotImplementedError:
        log.info("statement.emissor_sem_extrato", provider=tenant.issuer_provider)
        return []
    statement = getattr(adapter, "statement", None)
    if statement is None:
        return []
    return statement(since)
