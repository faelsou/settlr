from enum import StrEnum


class InvoiceStatus(StrEnum):
    """Máquina de estados do título (FLUXOS.md §13)."""

    ABERTO = "aberto"
    EM_COBRANCA = "em_cobranca"
    PROMESSA = "promessa"
    EM_NEGOCIACAO = "em_negociacao"
    RENEGOCIADO = "renegociado"
    PARCIALMENTE_PAGO = "parcialmente_pago"
    PAGO = "pago"
    FILA_HUMANA = "fila_humana"
    CONTESTADO = "contestado"
    CANCELADO = "cancelado"


OPEN_INVOICE_STATUSES = (
    InvoiceStatus.ABERTO,
    InvoiceStatus.EM_COBRANCA,
    InvoiceStatus.PROMESSA,
    InvoiceStatus.EM_NEGOCIACAO,
    InvoiceStatus.PARCIALMENTE_PAGO,
    InvoiceStatus.FILA_HUMANA,
)

DUNNING_STATUSES = (
    InvoiceStatus.ABERTO,
    InvoiceStatus.EM_COBRANCA,
    InvoiceStatus.PROMESSA,
    InvoiceStatus.PARCIALMENTE_PAGO,
)


class PaymentStatus(StrEnum):
    """Máquina de estados do pagamento (FLUXOS.md §14)."""

    RECEBIDO_COMPROVANTE = "recebido_comprovante"
    AGUARDANDO_BANCO = "aguardando_banco"
    RECEBIDO_BANCO = "recebido_banco"
    CONFIRMADO = "confirmado"
    CONCILIADO = "conciliado"
    EM_EXCECAO = "em_excecao"
    DESCARTADO = "descartado"


class PaymentOrigin(StrEnum):
    COMPROVANTE = "comprovante"
    EXTRATO = "extrato"
    WEBHOOK = "webhook"


class MatchMethod(StrEnum):
    CHAVE_EXATA = "chave_exata"
    VALOR_DOCUMENTO = "valor_documento"
    VALOR_NOME = "valor_nome"
    SOMA_TITULOS = "soma_titulos"
    MANUAL = "manual"


class ExceptionType(StrEnum):
    PAGAMENTO_NAO_IDENTIFICADO = "pagamento_nao_identificado"
    SUGESTAO_MATCH = "sugestao_match"
    CONTESTACAO = "contestacao"
    LEITURA_BAIXA_CONFIANCA = "leitura_baixa_confianca"
    TRANSCRICAO_INDISPONIVEL = "transcricao_indisponivel"
    DIFERENCA_VALOR = "diferenca_valor"
    FILA_HUMANA = "fila_humana"
    SESSAO_CANAL = "sessao_canal"


class ExceptionStatus(StrEnum):
    ABERTA = "aberta"
    RESOLVIDA = "resolvida"
    REJEITADA = "rejeitada"


class Intent(StrEnum):
    JA_PAGUEI = "ja_paguei"
    VOU_PAGAR = "vou_pagar"
    PARCELAR_DESCONTO = "parcelar_desconto"
    CONTESTACAO = "contestacao"
    PARAR = "parar"
    HOSTIL_SENSIVEL = "hostil_sensivel"
    DUVIDA = "duvida"


class ConversationState(StrEnum):
    AGENTE = "agente"
    AGUARDANDO_IDENTIDADE = "aguardando_identidade"
    AGUARDANDO_COMPROVANTE = "aguardando_comprovante"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    HUMANO = "humano"
    ENCERRADA = "encerrada"


class MessageDirection(StrEnum):
    IN = "in"
    OUT = "out"


class ApprovalStatus(StrEnum):
    PENDENTE = "pendente"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"
