"""Créditos da conta pelo Open Finance Brasil (API de contas). Sem arquivo."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import httpx

from app.reconciliation.service import BankPaymentIn

_E2E = re.compile(r"^E[A-Za-z0-9]{31}$")
_EFFECTIVE = "TRANSACAO_EFETIVADA"
_PAGE = 100
_MAX_PAGES = 20


class OpenFinanceClient:
    def __init__(self, config: dict[str, Any], client: httpx.Client | None = None):
        self.base_url = str(config["base_url"]).rstrip("/")
        self.token = str(config["token"])
        self.account_id = str(config["account_id"])
        self._client = client

    def statement(self, since: date, today: date) -> list[BankPaymentIn]:
        rows: list[BankPaymentIn] = []
        for page in range(1, _MAX_PAGES + 1):
            body = self._page(since, today, page)
            for item in body.get("data") or []:
                row = _credit(item)
                if row is not None:
                    rows.append(row)
            total = int((body.get("meta") or {}).get("totalPages") or 1)
            if page >= total:
                break
        return rows

    def _page(self, since: date, today: date, page: int) -> dict[str, Any]:
        path = f"/accounts/{self.account_id}/transactions"
        params = {
            "fromBookingDate": since.isoformat(),
            "toBookingDate": today.isoformat(),
            "page": page,
            "page-size": _PAGE,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "x-fapi-interaction-id": str(uuid4()),
        }
        if self._client is not None:
            response = self._client.request("GET", path, params=params, headers=headers)
        else:
            response = httpx.request(
                "GET", f"{self.base_url}{path}", params=params, headers=headers, timeout=20,
            )
        response.raise_for_status()
        return response.json()


def _credit(item: dict[str, Any]) -> BankPaymentIn | None:
    if item.get("creditDebitType") != "CREDITO":
        return None
    kind = item.get("completedAuthorisedPaymentType")
    if kind and kind != _EFFECTIVE:
        return None
    transaction_id = str(item.get("transactionId") or "").strip()
    if not transaction_id or len(f"of:{transaction_id}") > 120:
        return None
    amount_raw = (item.get("transactionAmount") or {}).get("amount")
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0:
        return None
    paid_at = _when(item.get("transactionDateTime"))
    if paid_at is None:
        return None
    e2e = transaction_id if _E2E.match(transaction_id) else None
    if e2e is None:
        extra = item.get("endToEndId")
        if isinstance(extra, str) and _E2E.match(extra):
            e2e = extra
    return BankPaymentIn(
        amount=amount,
        paid_at=paid_at,
        e2e_id=e2e,
        source_id=f"of:{transaction_id}",
        payer_doc=_document(item.get("partieCnpjCpf")),
        payer_bank=_fit(item.get("partieCompeCode"), 120),
        raw={"source": "open_finance", "transactionId": transaction_id, "type": item.get("type")},
    )


def _when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _document(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) not in (11, 14):
        return None
    return digits


def _fit(value: object, size: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > size:
        return None
    return value
