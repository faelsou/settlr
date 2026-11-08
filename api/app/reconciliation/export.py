"""Arquivo do período para o contador: título, valor, data e identificador bancário."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.settlement import tenant_zone
from app.models import Invoice, Match, Payment, Tenant

HEADER = ("titulo", "valor", "data", "identificador_bancario")


@dataclass(frozen=True)
class AccountantRow:
    titulo: str
    valor: Decimal
    data: date
    identificador_bancario: str


def settlement_rows(
    session: Session, tenant_id: UUID, start: date, end: date,
) -> list[AccountantRow]:
    tenant = session.get(Tenant, tenant_id)
    zone = tenant_zone(tenant.timezone if tenant is not None else None)
    start_at = datetime.combine(start, time.min, tzinfo=zone)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone)
    found = session.execute(
        select(
            Invoice.external_id,
            Match.amount_applied,
            Payment.paid_at,
            Payment.e2e_id,
            Payment.txid,
        )
        .join(Payment, Payment.id == Match.payment_id)
        .join(Invoice, Invoice.id == Match.invoice_id)
        .where(Match.provisional.is_(False))
        .where(Payment.paid_at >= start_at, Payment.paid_at < end_at)
        .order_by(Payment.paid_at, Invoice.external_id)
    ).all()
    rows: list[AccountantRow] = []
    for external_id, amount, paid_at, e2e_id, txid in found:
        when = paid_at if paid_at.tzinfo else paid_at.replace(tzinfo=zone)
        rows.append(
            AccountantRow(
                titulo=external_id,
                valor=amount,
                data=when.astimezone(zone).date(),
                identificador_bancario=e2e_id or txid or "",
            )
        )
    return rows


def render_accountant_csv(rows: list[AccountantRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow([
            row.titulo,
            f"{row.valor.quantize(Decimal('0.01'))}",
            row.data.isoformat(),
            row.identificador_bancario,
        ])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
