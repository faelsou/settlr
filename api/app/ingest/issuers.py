"""Adaptadores de emissor de cobrança. Cada um traduz o webhook do emissor para
`InvoiceIn` (título novo/alterado) ou `BankPaymentIn` (dinheiro recebido), e emite
a cobrança da parcela quando o devedor aceita um acordo."""

import base64
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import httpx

from app.core.logging import get_logger
from app.ingest.schemas import InvoiceIn
from app.reconciliation.service import BankPaymentIn

log = get_logger(__name__)

ASAAS_INVOICE_EVENTS = {"PAYMENT_CREATED", "PAYMENT_UPDATED"}
ASAAS_PAYMENT_EVENTS = {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}
ASAAS_SETTLED = {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"}
INTER_OPEN = {"A_RECEBER", "ATRASADO", "PROTESTO"}
INTER_PAID = {"RECEBIDO", "MARCADO_RECEBIDO"}
INTER_BASE = "https://cdpj.partners.bancointer.com.br"
CENT = Decimal("0.01")
_E2E = re.compile(r"^E[A-Za-z0-9]{31}$")
_INTER_CHARGE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
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

    def events(self, body: dict[str, Any] | list[Any]) -> list[InvoiceIn | BankPaymentIn]:
        if not isinstance(body, dict):
            raise ValueError("webhook do Asaas não é um objeto")
        parsed = self.parse(body)
        return [] if parsed is None else [parsed]


class InterAdapter:
    """Cobrança v3 do Banco Inter. O callback real é uma lista, um item por cobrança."""

    def __init__(self, config: dict[str, Any], client: httpx.Client | None = None):
        self.base_url = str(config.get("base_url", INTER_BASE)).rstrip("/")
        self.access_token = str(config.get("access_token") or "")
        self.conta = str(config.get("conta_corrente") or "")
        self.client_id = str(config.get("client_id") or "")
        self.client_secret = str(config.get("client_secret") or "")
        billing = str(config.get("billing_type") or "PIX").upper()
        self.billing_type = billing if billing in {"PIX", "BOLETO"} else "PIX"
        agenda = int(config.get("num_dias_agenda") or 30)
        self.num_dias_agenda = min(60, max(0, agenda))
        self.address = {
            "endereco": str(config.get("endereco") or "").strip(),
            "numero": str(config.get("numero") or "S/N").strip(),
            "bairro": str(config.get("bairro") or "Centro").strip(),
            "cidade": str(config.get("cidade") or "").strip(),
            "uf": str(config.get("uf") or "").strip().upper(),
            "cep": re.sub(r"\D", "", str(config.get("cep") or "")),
        }
        cert = config.get("cert_file")
        key = config.get("key_file")
        self.cert = (str(cert), str(key)) if cert and key else None
        self._client = client

    def events(self, body: dict[str, Any] | list[Any]) -> list[InvoiceIn | BankPaymentIn]:
        items = body if isinstance(body, list) else [body]
        found: list[InvoiceIn | BankPaymentIn] = []
        for item in items:
            if not isinstance(item, dict) or "situacao" not in item:
                continue
            situacao = str(item.get("situacao") or "")
            if situacao in INTER_PAID:
                row = _inter_payment(
                    item,
                    raw={"provider": "inter", "event": situacao, "cobranca": item},
                )
                if row is not None:
                    found.append(row)
            elif situacao in INTER_OPEN:
                invoice = self._invoice(item)
                if invoice is not None:
                    found.append(invoice)
        return found

    def parse(self, body: dict[str, Any] | list[Any]) -> InvoiceIn | BankPaymentIn | None:
        rows = self.events(body)
        return rows[0] if rows else None

    def statement(self, since: date) -> list[BankPaymentIn]:
        """Cobranças recebidas no Inter, pelo filtro PAGAMENTO da coleção."""
        end = date.today()
        if end < since:
            end = since
        rows: list[BankPaymentIn] = []
        for status_name in sorted(INTER_PAID):
            page = 0
            while len(rows) < _MAX_ROWS:
                payload = self._request(
                    "GET",
                    "/cobranca/v3/cobrancas",
                    params={
                        "dataInicial": since.isoformat(),
                        "dataFinal": end.isoformat(),
                        "filtrarDataPor": "PAGAMENTO",
                        "situacao": status_name,
                        "paginacao.itensPorPagina": _PAGE,
                        "paginacao.paginaAtual": page,
                    },
                )
                batch = payload.get("cobrancas") or []
                for item in batch:
                    row = _inter_payment(
                        item,
                        raw={
                            "source": "extrato_emissor",
                            "provider": "inter",
                            "cobranca": item,
                        },
                    )
                    if row is not None:
                        rows.append(row)
                if payload.get("ultimaPagina", True) or not batch:
                    break
                page += 1
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
        """Emite boleto com PIX e só devolve se o Inter já trouxe um dos dois."""
        created = self._request(
            "POST",
            "/cobranca/v3/cobrancas",
            json=self._emit_body(name, document, phone, email, amount, due_date, description),
        )
        payment_id = str(created["codigoSolicitacao"])
        try:
            detail = self._request("GET", f"/cobranca/v3/cobrancas/{payment_id}")
        except httpx.HTTPError:
            self.cancel(payment_id)
            raise
        pix, line, txid = _inter_instruments(detail)
        if not pix and not line:
            self.cancel(payment_id)
            raise ValueError("emissor não devolveu PIX nem boleto")
        return IssuedCharge(
            external_id=payment_id,
            txid=txid or payment_id,
            pix_copy_paste=pix,
            digitable_line=line,
            payment_url=None,
        )

    def cancel(self, payment_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/cobranca/v3/cobrancas/{payment_id}/cancelar",
                json={"motivoCancelamento": "Cancelado pelo Settlr"},
            )
        except httpx.HTTPError:
            log.warning("issuer.cancel_failed", payment_id=payment_id)

    def mark_paid(self, payment_id: str, paid_on: date, value: Decimal) -> str:
        """Baixa de prova. No Inter, `POST /pagar` existe no sandbox e dispara o callback."""
        log.info(
            "issuer.inter_pagar",
            payment_id=payment_id,
            paid_on=paid_on.isoformat(),
            value=str(value),
        )
        pagar_com = "BOLETO" if self.billing_type == "BOLETO" else "PIX"
        try:
            self._request(
                "POST",
                f"/cobranca/v3/cobrancas/{payment_id}/pagar",
                json={"pagarCom": pagar_com},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 409, 422} and _inter_already(exc.response):
                return "already_paid"
            raise
        return "paid"

    def _emit_body(
        self,
        name: str,
        document: str,
        phone: str | None,
        email: str | None,
        amount: Decimal,
        due_date: date,
        description: str,
    ) -> dict[str, Any]:
        address = self.address
        if not address["endereco"] or not address["cidade"] or len(address["uf"]) != 2:
            raise ValueError("emissor Inter sem endereço do pagador")
        if len(address["cep"]) != 8:
            raise ValueError("emissor Inter sem CEP do pagador")
        digits = re.sub(r"\D", "", document)
        pagador: dict[str, Any] = {
            "cpfCnpj": digits,
            "tipoPessoa": "JURIDICA" if len(digits) == 14 else "FISICA",
            "nome": name,
            **address,
        }
        if email:
            pagador["email"] = email
        ddd, telefone = _split_phone(phone)
        if ddd and telefone:
            pagador["ddd"] = ddd
            pagador["telefone"] = telefone
        body: dict[str, Any] = {
            "seuNumero": uuid4().hex[:15],
            "valorNominal": float(amount.quantize(CENT)),
            "dataVencimento": due_date.isoformat(),
            "numDiasAgenda": self.num_dias_agenda,
            "pagador": pagador,
            "formasRecebimento": ["BOLETO"] if self.billing_type == "BOLETO" else ["BOLETO", "PIX"],
        }
        if description:
            body["mensagem"] = {"linha1": description[:78]}
        return body

    def _invoice(self, item: dict[str, Any]) -> InvoiceIn | None:
        codigo = str(item.get("codigoSolicitacao") or "")
        if not codigo:
            return None
        detail = self._request("GET", f"/cobranca/v3/cobrancas/{codigo}")
        cobranca = detail.get("cobranca") or {}
        pagador = cobranca.get("pagador") or item.get("pagador") or {}
        nome = str(pagador.get("nome") or "").strip()
        document = str(pagador.get("cpfCnpj") or "")
        due = cobranca.get("dataVencimento") or item.get("dataVencimento")
        amount = _money(cobranca.get("valorNominal"))
        if amount is None:
            amount = _money(item.get("valorNominal"))
        if not nome or not document or not due or amount is None or amount <= 0:
            log.warning("issuer.inter_sem_pagador", codigo=codigo)
            return None
        pix, line, txid = _inter_instruments({**item, **detail})
        phone = _join_phone(pagador)
        return InvoiceIn(
            external_id=codigo,
            debtor_name=nome,
            debtor_document=document,
            debtor_phone=phone,
            debtor_email=pagador.get("email") or None,
            amount=amount,
            due_date=due,
            description=_fit(str(item.get("seuNumero") or ""), 300),
            txid=_fit(txid or codigo, 64),
            digitable_line=line,
            pix_copy_paste=pix,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = self._headers()
        if self._client is not None:
            response = self._client.request(method, path, headers=headers, **kwargs)
        else:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                cert=self.cert,
                timeout=20,
                **kwargs,
            )
        response.raise_for_status()
        if not response.content:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        if not self.access_token and self.client_id and self.client_secret:
            self.access_token = self._token()
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if self.conta:
            headers["x-conta-corrente"] = self.conta
        return headers

    def _token(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        basic = base64.b64encode(raw).decode()
        scope = "boleto-cobranca.read boleto-cobranca.write"
        kwargs = {
            "headers": {"Authorization": f"Basic {basic}"},
            "data": {"grant_type": "client_credentials", "scope": scope},
        }
        if self._client is not None:
            response = self._client.request("POST", "/oauth/v2/token", **kwargs)
        else:
            response = httpx.request(
                "POST",
                f"{self.base_url}/oauth/v2/token",
                cert=self.cert,
                timeout=20,
                **kwargs,
            )
        response.raise_for_status()
        return str(response.json()["access_token"])


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


def _money(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount


def _when(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    if "T" not in text:
        return datetime.combine(date.fromisoformat(text[:10]), time(12), tzinfo=UTC)
    if "." in text:
        head, tail = text.split(".", 1)
        digits = []
        rest = []
        for char in tail:
            if char.isdigit() and not rest:
                digits.append(char)
            else:
                rest.append(char)
        frac = ("".join(digits) + "000000")[:6]
        text = f"{head}.{frac}{''.join(rest)}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _split_phone(phone: str | None) -> tuple[str | None, str | None]:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) not in {10, 11}:
        return None, None
    return digits[:2], digits[2:]


def _join_phone(pagador: dict[str, Any]) -> str | None:
    ddd = re.sub(r"\D", "", str(pagador.get("ddd") or ""))
    number = re.sub(r"\D", "", str(pagador.get("telefone") or pagador.get("celular") or ""))
    if ddd and number and not number.startswith(ddd):
        number = ddd + number
    if len(number) in {10, 11}:
        return number
    return None


def _digits(value: object, size: int) -> str | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    return _fit(digits, size)


def _inter_instruments(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    cobranca = payload.get("cobranca") if isinstance(payload.get("cobranca"), dict) else {}
    pix_node = payload.get("pix") if isinstance(payload.get("pix"), dict) else {}
    boleto = payload.get("boleto") if isinstance(payload.get("boleto"), dict) else {}
    pix = (
        pix_node.get("pixCopiaECola")
        or payload.get("pixCopiaECola")
        or cobranca.get("pixCopiaECola")
    )
    line = _digits(
        boleto.get("linhaDigitavel")
        or payload.get("linhaDigitavel")
        or cobranca.get("linhaDigitavel"),
        64,
    )
    txid = pix_node.get("txid") or payload.get("txid") or cobranca.get("txid")
    pix_text = pix.strip() if isinstance(pix, str) and pix.strip() else None
    txid_text = txid.strip() if isinstance(txid, str) and txid.strip() else None
    return pix_text, line, txid_text


def _inter_payment(item: dict[str, Any], *, raw: dict[str, Any]) -> BankPaymentIn | None:
    if str(item.get("situacao") or "") not in INTER_PAID:
        return None
    codigo = str(item.get("codigoSolicitacao") or "")
    if not _INTER_CHARGE.fullmatch(codigo):
        return None
    amount = _money(item.get("valorTotalRecebido"))
    if amount is None or amount <= 0:
        amount = _money(item.get("valorNominal"))
    if amount is None or amount <= 0:
        return None
    when_raw = item.get("dataHoraSituacao") or item.get("dataSituacao")
    if not when_raw:
        return None
    txid = _inter_instruments(item)[2]
    return BankPaymentIn(
        amount=amount,
        paid_at=_when(str(when_raw)),
        e2e_id=_fit(_e2e_value(item.get("endToEndId") or item.get("endToEnd")), 64),
        txid=_fit(txid or codigo, 64),
        source_id=_fit(f"inter:{codigo}", 120),
        raw=raw,
    )


def _inter_already(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    text = str(body).lower()
    return "recebid" in text or "marcado_recebido" in text


def get_adapter(
    provider: str | None,
    config: dict[str, Any],
    client: httpx.Client | None = None,
) -> AsaasAdapter | InterAdapter:
    if provider == "asaas":
        return AsaasAdapter(config, client=client)
    if provider == "inter":
        return InterAdapter(config, client=client)
    raise NotImplementedError(f"emissor sem adaptador: {provider}")
