"""Política de negociação e gerador de opções (FLUXOS.md §7, tool `build_payment_options`).

O LLM nunca cria valores: ele só escolhe uma das opções que este módulo devolve.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

CENT = Decimal("0.01")

DEFAULT_NEGOTIATION_POLICY: dict = {
    "max_discount_pct_cash": 10,
    "min_down_payment_pct": 20,
    "max_installments": 6,
    "min_installment_amount": 50,
    "installment_interval_days": 30,
    "monthly_interest_pct": 0,
    "first_due_in_days": 3,
    "max_promise_days": 15,
}


@dataclass(frozen=True)
class NegotiationPolicy:
    max_discount_pct_cash: Decimal
    min_down_payment_pct: Decimal
    max_installments: int
    min_installment_amount: Decimal
    installment_interval_days: int
    monthly_interest_pct: Decimal
    first_due_in_days: int
    max_promise_days: int

    @classmethod
    def from_json(cls, data: dict | None) -> "NegotiationPolicy":
        merged = {**DEFAULT_NEGOTIATION_POLICY, **(data or {})}
        return cls(
            max_discount_pct_cash=Decimal(str(merged["max_discount_pct_cash"])),
            min_down_payment_pct=Decimal(str(merged["min_down_payment_pct"])),
            max_installments=int(merged["max_installments"]),
            min_installment_amount=Decimal(str(merged["min_installment_amount"])),
            installment_interval_days=int(merged["installment_interval_days"]),
            monthly_interest_pct=Decimal(str(merged["monthly_interest_pct"])),
            first_due_in_days=int(merged["first_due_in_days"]),
            max_promise_days=int(merged["max_promise_days"]),
        )


@dataclass(frozen=True)
class Installment:
    number: int
    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class PaymentOption:
    id: str
    kind: str  # "a_vista" | "parcelado"
    total: Decimal
    discount: Decimal
    down_payment: Decimal
    installments: tuple[Installment, ...]

    def describe(self) -> str:
        if self.kind == "a_vista":
            due = self.installments[0].due_date.strftime("%d/%m")
            extra = f" (desconto de {brl(self.discount)})" if self.discount else ""
            return f"À vista: {brl(self.total)} até {due}{extra}"
        rest = self.installments[1:]
        return (
            f"Entrada de {brl(self.down_payment)} + {len(rest)}x de {brl(rest[0].amount)}"
            f" (total {brl(self.total)})"
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["total"] = str(self.total)
        data["discount"] = str(self.discount)
        data["down_payment"] = str(self.down_payment)
        data["installments"] = [
            {"number": i.number, "due_date": i.due_date.isoformat(), "amount": str(i.amount)}
            for i in self.installments
        ]
        return data


def brl(value: Decimal) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _split(total: Decimal, parts: int) -> list[Decimal]:
    """Divide em centavos; a diferença de arredondamento vai para a última parcela."""
    base = (total / parts).quantize(CENT, rounding=ROUND_DOWN)
    amounts = [base] * parts
    amounts[-1] = total - base * (parts - 1)
    return amounts


def build_payment_options(
    total_open: Decimal, policy: NegotiationPolicy, today: date
) -> list[PaymentOption]:
    if total_open <= 0:
        return []

    first_due = today + timedelta(days=policy.first_due_in_days)
    options: list[PaymentOption] = []

    discount = (total_open * policy.max_discount_pct_cash / 100).quantize(CENT, rounding=ROUND_DOWN)
    cash_total = total_open - discount
    options.append(
        PaymentOption(
            id="a_vista",
            kind="a_vista",
            total=cash_total,
            discount=discount,
            down_payment=cash_total,
            installments=(Installment(1, first_due, cash_total),),
        )
    )

    min_down = (total_open * policy.min_down_payment_pct / 100).quantize(CENT)
    for n in range(2, policy.max_installments + 1):
        months = n - 1
        financed = total_open - min_down
        interest = (financed * policy.monthly_interest_pct / 100 * months).quantize(CENT)
        financed_total = financed + interest
        rest = _split(financed_total, months)
        if min(rest) < policy.min_installment_amount:
            break
        installments = [Installment(1, first_due, min_down)] + [
            Installment(
                i + 2, first_due + timedelta(days=policy.installment_interval_days * (i + 1)), amt
            )
            for i, amt in enumerate(rest)
        ]
        options.append(
            PaymentOption(
                id=f"parcelado_{n}x",
                kind="parcelado",
                total=min_down + financed_total,
                discount=Decimal("0"),
                down_payment=min_down,
                installments=tuple(installments),
            )
        )

    return options


def validate_promise_date(promised: date, today: date, policy: NegotiationPolicy) -> str | None:
    """Devolve o motivo da recusa, ou None se a data é aceitável."""
    if promised <= today:
        return "a data precisa ser futura"
    if promised > today + timedelta(days=policy.max_promise_days):
        return f"a data precisa ser em até {policy.max_promise_days} dias"
    return None
