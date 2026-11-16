"""Cobrança que ficou aberta no emissor depois de um cancelamento que falhou (SETL-46).

O acordo desfaz a transação local, mas a parcela continua pagável no Asaas ou no
Inter. Cada uma vira uma exceção na fila, gravada numa transação própria (a do
acordo é desfeita), e uma tarefa tenta cancelar de novo com retry. Quando o
emissor cancela, a tarefa fecha a exceção.
"""

from uuid import UUID

from app.core.db import tenant_session
from app.core.logging import get_logger
from app.models.enums import ExceptionType
from app.reconciliation.service import open_exception

log = get_logger(__name__)


def report_orphan_charges(
    tenant_id: UUID,
    provider: str | None,
    external_ids: list[str],
    *,
    reason: str,
    debtor_id: UUID | None = None,
    source_invoice_ids: list[UUID] | None = None,
) -> list[UUID]:
    """Abre uma exceção por cobrança órfã e agenda o cancelamento. Nunca levanta."""
    opened: list[tuple[str, UUID]] = []
    try:
        # Sem invoice_id: a transação do acordo ainda trava os títulos de origem.
        with tenant_session(tenant_id) as session:
            for external_id in external_ids:
                exc = open_exception(
                    session, tenant_id, ExceptionType.COBRANCA_EMISSOR,
                    details={
                        "reason": f"{reason}: cobrança ficou aberta no emissor",
                        "external_id": external_id,
                        "provider": provider,
                        "debtor_id": str(debtor_id) if debtor_id else None,
                        "source_invoice_ids": [str(i) for i in source_invoice_ids or []],
                        "action": "cancelar",
                    },
                )
                opened.append((external_id, exc.id))
    except Exception:
        log.exception("issuer.orphan_report_failed", tenant_id=str(tenant_id),
                      external_ids=external_ids)
        return []

    from app.ingest.tasks import cancel_issuer_charge

    for external_id, exception_id in opened:
        try:
            cancel_issuer_charge.delay(str(tenant_id), external_id, str(exception_id))
        except Exception:
            log.exception("issuer.orphan_enqueue_failed", external_id=external_id)
    return [exception_id for _, exception_id in opened]
