"""Adaptadores de emissor de cobrança. Cada um traduz o webhook do emissor para
`InvoiceIn` (título novo/alterado) ou `BankPaymentIn` (dinheiro recebido), e emite
a cobrança da parcela quando o devedor aceita um acordo."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.logging import get_logger
from app.ingest.schemas import InvoiceIn
from app.reconciliation.service import BankPaymentIn

log = get_logger(__name__)

ASAAS_INVOICE_EVENTS = {"PAYMENT_CREATED", "PAYMENT_UPDATED"}
ASAAS_PAYMENT_EVENTS = {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}
ASAAS_SETTLED = {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"}
CENT = Decimal("0.01")
_E2E = re.compile(r"^E[A-Za-z0-9]{31}$")
_PAGE = 100
_MAX_ROWS = 2000


@dataclass(frozen=True)
class IssuedCharge:
    """Cobrança criada no emissor, já com o código que o devedor usa para pagar."""

    external_id: str
    txid: str
    pix_copy_paste: str | None
    digitable_line: str | None
    payment_url: str | None


class AsaasAdapter:
    def __init__(self, config: dict[str, Any], client: httpx.Client | None = None):
        self.base_url = str(config.get("base_url", "https://api.asaas.com/v3")).rstrip("/")
        self.api_key = config.get("api_key", "")
        billing = str(config.get("billing_type") or "PIX").upper()
        self.billing_type = billing if billing in {"PIX", "BOLETO"} else "PIX"
        self._client = client

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self._client is not None:
            response = self._client.request(method, path, **kwargs)
        else:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"access_token": self.api_key},
                timeout=20,
                **kwargs,
            )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def _customer(self, customer_id: str) -> dict[str, Any]:
        return self._request("GET", f"/customers/{customer_id}")

    def _pages(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset < _MAX_ROWS:
            page = self._request("GET", path, params={**params, "limit": _PAGE, "offset": offset})
            data = page.get("data") or []
            rows.extend(data)
            if not page.get("hasMore") or not data:
                break
            offset += len(data)
        return rows

    def parse(self, body: dict[str, Any]) -> InvoiceIn | BankPaymentIn | None:
        event = body.get("event")
        payment = body.get("payment") or {}

        if event in ASAAS_INVOICE_EVENTS:
            customer = self._customer(payment["customer"])
            return InvoiceIn(
                external_id=payment["id"],
                debtor_name=customer["name"],
                debtor_document=customer["cpfCnpj"],
                debtor_phone=customer.get("mobilePhone") or customer.get("phone"),
                debtor_email=customer.get("email"),
                amount=Decimal(str(payment["value"])),
                due_date=payment["dueDate"],
                description=payment.get("description"),
                txid=payment["id"],
                digitable_line=payment.get("identificationField"),
                payment_url=payment.get("invoiceUrl"),
            )

        if event in ASAAS_PAYMENT_EVENTS:
            return _asaas_payment(
                payment, raw={"provider": "asaas", "event": event, "payment": payment},
            )
        return None

    def statement(self, since: date) -> list[BankPaymentIn]:
        """Cobranças já recebidas. É o extrato do emissor, sem arquivo e sem webhook."""
        rows: list[BankPaymentIn] = []
        for status_name in sorted(ASAAS_SETTLED):
            params = {"status": status_name, "paymentDate[ge]": since.isoformat()}
            for payment in self._pages("/payments", params):
                if payment.get("status") not in ASAAS_SETTLED:
                    continue
                row = _asaas_payment(
                    payment,
                    raw={"source": "extrato_emissor", "provider": "asaas", "payment": payment},
                )
                if row is not None:
                    rows.append(row)
        return rows

    def issue(
        self,
        *,
        name: str,
        document: str,
        phone: str | None,
        email: str | None,
        amount: Decimal,
        due_date: date,
        description: str,
    ) -> IssuedCharge:
        """Cria a cobrança e só devolve se houver PIX ou linha digitável."""
        customer_id = self._customer_id(name, document, phone, email)
        payment = self._request(
            "POST",
            "/payments",
            json={
                "customer": customer_id,
                "billingType": self.billing_type,
                "value": float(amount.quantize(CENT)),
                "dueDate": due_date.isoformat(),
                "description": description,
            },
        )
        payment_id = payment["id"]
        try:
            pix, line = self._instrument(payment_id)
        except httpx.HTTPError:
            self.cancel(payment_id)
            raise
        if not pix and not line:
            self.cancel(payment_id)
            raise ValueError("emissor não devolveu PIX nem boleto")
        return IssuedCharge(
            external_id=payment_id,
            txid=payment_id,
            pix_copy_paste=pix,
            digitable_line=line,
            payment_url=payment.get("invoiceUrl") or payment.get("bankSlipUrl"),
        )

    def cancel(self, payment_id: str) -> None:
        try:
            self._request("DELETE", f"/payments/{payment_id}")
        except httpx.HTTPError:
            log.warning("issuer.cancel_failed", payment_id=payment_id)

    def mark_paid(self, payment_id: str, paid_on: date, value: Decimal) -> str:
        """Marca a cobrança como recebida. Cobrança que o Asaas já quitou conta como feita."""
        try:
            self._request(
                "POST",
                f"/payments/{payment_id}/receiveInCash",
                json={
                    "paymentDate": paid_on.isoformat(),
                    "value": float(value.quantize(CENT)),
                    "notifyCustomer": False,
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and _already_received(exc.response):
                return "already_paid"
            raise
        return "paid"

    def _customer_id(
        self, name: str, document: str, phone: str | None, email: str | None,
    ) -> str:
        found = self._request("GET", "/customers", params={"cpfCnpj": document})
        data = found.get("data") or []
        if data:
            return data[0]["id"]
        body = {"name": name, "cpfCnpj": document, "mobilePhone": phone, "email": email}
        created = self._request("POST", "/customers", json={k: v for k, v in body.items() if v})
        return created["id"]

    def _instrument(self, payment_id: str) -> tuple[str | None, str | None]:
        pix = line = None
        errors: list[httpx.HTTPError] = []
        answered = False
        if self.billing_type != "BOLETO":
            try:
                qr = self._request("GET", f"/payments/{payment_id}/pixQrCode")
                pix = qr.get("payload") or None
                answered = True
            except httpx.HTTPError as exc:
                errors.append(exc)
        if not pix:
            try:
                field = self._request("GET", f"/payments/{payment_id}/identificationField")
                raw = field.get("identificationField") or ""
                digits = re.sub(r"\D", "", raw)
                line = digits or None
                answered = True
            except httpx.HTTPError as exc:
                errors.append(exc)
        if not pix and not line and not answered and errors:
            raise errors[-1]
        return pix, line


def _fit(value: str | None, size: int) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or len(value) > size:
        return None
    return value


def _e2e_value(value: object) -> str | None:
    if isinstance(value, str) and _E2E.match(value.strip()):
        return value.strip()
    return None


def _asaas_e2e(payment: dict[str, Any]) -> str | None:
    for key in ("endToEndIdentifier", "endToEndId"):
        found = _e2e_value(payment.get(key))
        if found:
            return found
    pix = payment.get("pixTransaction")
    found = _e2e_value(pix)
    if found:
        return found
    if isinstance(pix, dict):
        for key in ("endToEndIdentifier", "endToEndId"):
            found = _e2e_value(pix.get(key))
            if found:
                return found
    return None


def _asaas_payment(payment: dict[str, Any], *, raw: dict[str, Any]) -> BankPaymentIn | None:
    paid = payment.get("clientPaymentDate") or payment.get("paymentDate")
    payment_id = str(payment.get("id") or "")
    if not paid or not payment_id:
        return None
    try:
        amount = Decimal(str(payment["value"]))
    except (InvalidOperation, KeyError):
        return None
    if amount <= 0:
        return None
    paid_on = datetime.fromisoformat(str(paid)[:10]).date()
    return BankPaymentIn(
        amount=amount,
        paid_at=datetime.combine(paid_on, time(12), tzinfo=UTC),
        e2e_id=_fit(_asaas_e2e(payment), 64),
        txid=_fit(payment_id, 64),
        source_id=_fit(f"asaas:{payment_id}", 120),
        raw=raw,
    )


def _already_received(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    text = str(body).lower()
    settled = "recebid" in text or "confirmad" in text
    return settled and ("já" in text or "ja " in text)


def get_adapter(
    provider: str | None,
    config: dict[str, Any],
    client: httpx.Client | None = None,
) -> AsaasAdapter:
    if provider == "asaas":
        return AsaasAdapter(config, client=client)
    raise NotImplementedError(f"emissor sem adaptador: {provider}")
