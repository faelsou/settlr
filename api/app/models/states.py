"""Transições permitidas (FLUXOS.md §13 e §14). Mudar status fora daqui é bug."""

from app.models.enums import InvoiceStatus as I
from app.models.enums import PaymentStatus as P

INVOICE_TRANSITIONS: dict[I, set[I]] = {
    I.ABERTO: {I.EM_COBRANCA, I.PAGO, I.PARCIALMENTE_PAGO, I.CANCELADO, I.EM_NEGOCIACAO,
               I.PROMESSA, I.CONTESTADO, I.FILA_HUMANA},
    I.EM_COBRANCA: {I.PROMESSA, I.EM_NEGOCIACAO, I.PARCIALMENTE_PAGO, I.PAGO, I.FILA_HUMANA,
                    I.CONTESTADO, I.CANCELADO},
    I.PROMESSA: {I.EM_COBRANCA, I.PAGO, I.PARCIALMENTE_PAGO, I.EM_NEGOCIACAO, I.CONTESTADO},
    I.EM_NEGOCIACAO: {I.RENEGOCIADO, I.EM_COBRANCA, I.PAGO, I.PARCIALMENTE_PAGO, I.FILA_HUMANA},
    I.PARCIALMENTE_PAGO: {I.PAGO, I.EM_COBRANCA, I.PROMESSA, I.EM_NEGOCIACAO, I.FILA_HUMANA,
                          I.CONTESTADO},
    I.FILA_HUMANA: {I.PAGO, I.PARCIALMENTE_PAGO, I.EM_NEGOCIACAO, I.CANCELADO, I.CONTESTADO,
                    I.EM_COBRANCA},
    I.CONTESTADO: {I.EM_COBRANCA, I.CANCELADO},
    I.RENEGOCIADO: set(),
    I.PAGO: set(),
    I.CANCELADO: set(),
}

PAYMENT_TRANSITIONS: dict[P, set[P]] = {
    P.RECEBIDO_COMPROVANTE: {P.AGUARDANDO_BANCO, P.EM_EXCECAO, P.DESCARTADO},
    P.AGUARDANDO_BANCO: {P.CONFIRMADO, P.EM_EXCECAO, P.DESCARTADO},
    P.RECEBIDO_BANCO: {P.CONFIRMADO},
    P.CONFIRMADO: {P.CONCILIADO, P.EM_EXCECAO},
    P.EM_EXCECAO: {P.CONCILIADO, P.DESCARTADO, P.AGUARDANDO_BANCO, P.CONFIRMADO},
    P.CONCILIADO: set(),
    P.DESCARTADO: set(),
}


class InvalidTransition(ValueError):
    pass


def check_invoice(current: str, new: str) -> None:
    if current != new and I(new) not in INVOICE_TRANSITIONS[I(current)]:
        raise InvalidTransition(f"título: {current} → {new} não é permitido")


def check_payment(current: str, new: str) -> None:
    if current != new and P(new) not in PAYMENT_TRANSITIONS[P(current)]:
        raise InvalidTransition(f"pagamento: {current} → {new} não é permitido")
