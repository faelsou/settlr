from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ReceiptExtraction(BaseModel):
    """Saída estruturada do LLM ao ler um comprovante. Campos ausentes ficam nulos;
    o modelo não deve inferir o que não está escrito."""

    is_payment_receipt: bool = Field(
        description="Se o documento é de fato um comprovante de pagamento"
    )
    amount: Decimal | None = Field(None, description="Valor pago em reais, ex.: 150.00")
    paid_at: datetime | None = Field(None, description="Data e hora do pagamento, ISO 8601")
    payer_name: str | None = Field(None, description="Nome de quem pagou")
    payer_doc: str | None = Field(
        None, description="CPF/CNPJ do pagador exatamente como aparece, inclusive com asteriscos"
    )
    payee_name: str | None = Field(None, description="Nome de quem recebeu")
    e2e_id: str | None = Field(
        None, description="ID da transação PIX (E2E), 32 caracteres começando com E"
    )
    bank: str | None = Field(None, description="Banco ou instituição do pagador")
    method: str | None = Field(None, description="pix, boleto, ted, cartao ou outro")
    confidence: float = Field(description="Confiança de 0 a 1 na leitura dos campos principais")
