"""Importação de OFX ou CSV. É a exceção: o caminho feliz não usa arquivo."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from ofxparse import OfxParser

from app.reconciliation.service import BankPaymentIn

CSV_COLUMNS = {"data", "valor"}


def _decimal_br(value: str) -> Decimal:
    value = value.strip().replace("R$", "").replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return Decimal(value)


def _parse_date(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"data inválida: {value}")


def parse_csv(content: bytes) -> list[BankPaymentIn]:
    """CSV com cabeçalho: data, valor e opcionalmente e2e_id, documento, nome, descricao.
    Só entradas (valor positivo) viram pagamento."""
    text = content.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = {h.strip().lower() for h in reader.fieldnames or []}
    if not CSV_COLUMNS <= headers:
        raise ValueError(f"CSV precisa das colunas {sorted(CSV_COLUMNS)}")

    payments: list[BankPaymentIn] = []
    for line, row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            amount = _decimal_br(row["valor"])
        except InvalidOperation as exc:
            raise ValueError(f"linha {line}: valor inválido") from exc
        if amount <= 0:
            continue
        payments.append(
            BankPaymentIn(
                amount=amount,
                paid_at=_parse_date(row["data"]),
                e2e_id=row.get("e2e_id") or None,
                payer_doc=row.get("documento") or None,
                payer_name=row.get("nome") or None,
                raw={"source": "csv", "line": line, **row},
            )
        )
    return payments


def parse_ofx(content: bytes) -> list[BankPaymentIn]:
    ofx = OfxParser.parse(io.BytesIO(content))
    payments: list[BankPaymentIn] = []
    for account in ofx.accounts:
        for tx in account.statement.transactions:
            amount = Decimal(str(tx.amount))
            if amount <= 0:
                continue
            paid_at = tx.date if tx.date.tzinfo else tx.date.replace(tzinfo=UTC)
            payments.append(
                BankPaymentIn(
                    amount=amount,
                    paid_at=paid_at,
                    payer_name=tx.payee or None,
                    raw={"source": "ofx", "fitid": tx.id, "memo": tx.memo, "payee": tx.payee},
                )
            )
    return payments


def parse_statement(filename: str, content: bytes) -> list[BankPaymentIn]:
    if filename.lower().endswith((".ofx", ".qfx")):
        return parse_ofx(content)
    return parse_csv(content)
