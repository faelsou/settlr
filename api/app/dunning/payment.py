"""PIX ou boleto que a régua pode entregar. Link sozinho não conta."""

from sqlalchemy import func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models import Invoice


def has_payment_code(pix: str | None, boleto: str | None) -> bool:
    return bool((pix or "").strip() or (boleto or "").strip())


def payment_code_clause() -> ColumnElement[bool]:
    def filled(column: object) -> ColumnElement[bool]:
        return func.length(func.btrim(func.coalesce(column, ""))) > 0

    return or_(filled(Invoice.pix_copy_paste), filled(Invoice.digitable_line))
