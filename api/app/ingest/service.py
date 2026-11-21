"""Ingestão de títulos (FLUXOS.md §4). Idempotente pela chave do emissor."""

import csv
import io
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.phones import merge_phones
from app.ingest.schemas import ImportResult, InvoiceIn
from app.models import Debtor, Invoice
from app.models.enums import InvoiceStatus

CSV_FIELDS = {
    "referencia": "external_id",
    "nome": "debtor_name",
    "documento": "debtor_document",
    "email": "debtor_email",
    "valor": "amount",
    "vencimento": "due_date",
    "descricao": "description",
    "txid": "txid",
    "linha_digitavel": "digitable_line",
    "pix_copia_cola": "pix_copy_paste",
    "link": "payment_url",
}

PHONE_COLUMNS = ("telefone", "telefone2", "telefone3", "telefone4", "telefone5")


def upsert_debtor(session: Session, tenant_id: UUID, data: InvoiceIn) -> Debtor:
    debtor = session.scalars(
        select(Debtor).where(Debtor.tenant_id == tenant_id, Debtor.document == data.debtor_document)
    ).first()
    if debtor is None:
        debtor = Debtor(
            tenant_id=tenant_id,
            name=data.debtor_name,
            document=data.debtor_document,
            phone=data.debtor_phones[0] if data.debtor_phones else None,
            phones=data.debtor_phones,
            email=data.debtor_email,
        )
        session.add(debtor)
        session.flush()
    else:
        if data.debtor_phones:
            phones = merge_phones(debtor.phone, debtor.phones, data.debtor_phones)
            debtor.phones = phones
            debtor.phone = phones[0]
        debtor.email = data.debtor_email or debtor.email
    return debtor


def upsert_invoice(
    session: Session, tenant_id: UUID, data: InvoiceIn, actor: str
) -> tuple[Invoice, bool]:
    debtor = upsert_debtor(session, tenant_id, data)
    invoice = session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id, Invoice.external_id == data.external_id
        )
    ).first()
    created = invoice is None
    fields = {
        "description": data.description,
        "amount": data.amount,
        "due_date": data.due_date,
        "txid": data.txid,
        "digitable_line": data.digitable_line,
        "pix_copy_paste": data.pix_copy_paste,
        "payment_url": data.payment_url,
    }

    if created:
        invoice = Invoice(
            tenant_id=tenant_id, debtor_id=debtor.id, external_id=data.external_id,
            status=InvoiceStatus.ABERTO, **fields,
        )
        session.add(invoice)
        session.flush()
        audit(session, tenant_id=tenant_id, actor=actor, action="cria_titulo",
              entity="invoice", entity_id=invoice.id, after=fields)
    else:
        before = {k: getattr(invoice, k) for k in fields}
        if invoice.status in (
            InvoiceStatus.PAGO,
            InvoiceStatus.RENEGOCIADO,
            InvoiceStatus.CANCELADO,
        ):
            return invoice, False
        for key, value in fields.items():
            if value is not None:
                setattr(invoice, key, value)
        after = {k: getattr(invoice, k) for k in fields}
        if before != after:
            audit(session, tenant_id=tenant_id, actor=actor, action="atualiza_titulo",
                  entity="invoice", entity_id=invoice.id, before=before, after=after)
    return invoice, created


def parse_invoice_csv(content: bytes) -> tuple[list[InvoiceIn], list[str]]:
    text = content.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows, errors = [], []
    for line, raw in enumerate(reader, start=2):
        mapped = {
            CSV_FIELDS[k.strip().lower()]: (v or "").strip() or None
            for k, v in raw.items()
            if k and k.strip().lower() in CSV_FIELDS
        }
        cells = {
            k.strip().lower(): (v or "").strip()
            for k, v in raw.items()
            if k and (v or "").strip()
        }
        mapped["debtor_phones"] = [cells[name] for name in PHONE_COLUMNS if cells.get(name)]
        if mapped.get("amount"):
            value = mapped["amount"].replace("R$", "").strip()
            if "," in value:
                value = value.replace(".", "").replace(",", ".")
            mapped["amount"] = Decimal(value)
        if mapped.get("due_date") and "/" in mapped["due_date"]:
            d, m, y = mapped["due_date"].split("/")
            mapped["due_date"] = f"{y}-{m}-{d}"
        try:
            rows.append(InvoiceIn(**mapped))
        except (ValidationError, ArithmeticError) as exc:
            errors.append(f"linha {line}: {exc}")
    return rows, errors


def import_invoices(
    session: Session, tenant_id: UUID, rows: list[InvoiceIn], actor: str
) -> ImportResult:
    result = ImportResult()
    for row in rows:
        _, created = upsert_invoice(session, tenant_id, row, actor)
        if created:
            result.created += 1
        else:
            result.updated += 1
    return result
