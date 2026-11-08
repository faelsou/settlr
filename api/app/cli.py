"""Comandos operacionais.

    python -m app.cli migrate      # Alembic + checkpointer (job one-off do deploy)
    python -m app.cli seed-demo    # tenant e títulos de exemplo (só dev)
    python -m app.cli seed-envio   # títulos de teste da régua, um número só (só dev)
"""

import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config


def migrate() -> None:
    from app.agent.runner import setup_checkpointer

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")
    setup_checkpointer()
    print("migração concluída")


DEFAULT_RECONCILIATION_RULES = {
    "days_before_due": 10,
    "days_after_due": 60,
    "name_similarity_min": 0.82,
    "max_invoices_in_sum": 4,
    "allow_partial": True,
    "max_overpay_pct": "2",
    "max_underpay_pct": "0",
}


def seed_demo() -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.agent.policy import DEFAULT_NEGOTIATION_POLICY
    from app.core.config import get_settings
    from app.core.db import SessionLocal, set_tenant
    from app.dunning.rules import DEFAULT_ALLOWED_HOURS, DEFAULT_DUNNING_RULES
    from app.ingest.schemas import InvoiceIn
    from app.ingest.service import import_invoices
    from app.models import (
        Approval,
        Conversation,
        Debtor,
        Invoice,
        Message,
        Payment,
        ReviewException,
        Tenant,
    )
    from app.models.enums import (
        ConversationState,
        ExceptionType,
        InvoiceStatus,
        PaymentOrigin,
        PaymentStatus,
    )

    if get_settings().env == "prod":
        sys.exit("seed-demo não roda em produção")

    with SessionLocal() as session, session.begin():
        tenant = session.query(Tenant).filter_by(slug="demo").first()
        if tenant is None:
            tenant = Tenant(
                name="Clínica Demo",
                slug="demo",
                active=True,
                negotiation_policy=DEFAULT_NEGOTIATION_POLICY,
                dunning_rules=DEFAULT_DUNNING_RULES,
                allowed_hours=DEFAULT_ALLOWED_HOURS,
                reconciliation_rules=DEFAULT_RECONCILIATION_RULES,
                whatsapp_instance="Cobranca",
                legal_basis="Execução de contrato (LGPD art. 7º, V)",
                owner_email="operador@demo.local",
            )
            session.add(tenant)
            session.flush()
        elif tenant.whatsapp_instance in (None, "demo"):
            tenant.whatsapp_instance = "Cobranca"
        if not tenant.owner_email:
            tenant.owner_email = "operador@demo.local"
        from app.dunning.legal import adopt_canonical_texts

        if upgraded := adopt_canonical_texts(tenant.dunning_rules):
            tenant.dunning_rules = upgraded
        set_tenant(session, tenant.id)

        today = date.today()
        rows = [
            InvoiceIn(
                external_id=f"demo-{n}",
                debtor_name=name,
                debtor_document=doc,
                debtor_phone=phone,
                amount=Decimal(amount),
                due_date=today + timedelta(days=offset),
                description=desc,
                txid=f"txdemo{n:04d}",
            )
            for n, (name, doc, phone, amount, offset, desc) in enumerate([
                ("Maria Souza", "12345678909", "5511952313944", "350.00", -5, "Mensalidade setembro"),
                ("Maria Souza", "12345678909", "5511952313944", "350.00", 25, "Mensalidade outubro"),
                ("João Pereira", "98765432100", "21977776666", "1200.00", -12, "Tratamento ortodôntico"),
                ("Ana Lima", "11144477735", "31966665555", "89.90", 2, "Consulta de retorno"),
            ], start=1)
        ]
        result = import_invoices(session, tenant.id, rows, "seed")

        invoices = list(session.scalars(select(Invoice).where(Invoice.tenant_id == tenant.id)))
        by_ext = {inv.external_id: inv for inv in invoices}
        for ext in ("demo-1", "demo-3"):
            if ext in by_ext and by_ext[ext].status == InvoiceStatus.ABERTO:
                by_ext[ext].status = InvoiceStatus.EM_COBRANCA

        maria = session.scalars(select(Debtor).where(Debtor.document == "12345678909")).first()
        joao = session.scalars(select(Debtor).where(Debtor.document == "98765432100")).first()
        now = datetime.now(UTC)

        if not session.scalars(select(Payment).where(Payment.tenant_id == tenant.id)).first():
            unidentified = Payment(
                tenant_id=tenant.id,
                origin=PaymentOrigin.WEBHOOK,
                status=PaymentStatus.EM_EXCECAO,
                amount=Decimal("199.90"),
                paid_at=now - timedelta(days=1),
                e2e_id="E18236120202610161230ABCDEFGHIJK",
                payer_name="Pix Desconhecido",
                payer_doc="00011122233",
                payer_bank="Banco Demo",
                bank_confirmed_at=now - timedelta(hours=20),
                raw={"seed": True},
            )
            suggestion = Payment(
                tenant_id=tenant.id,
                origin=PaymentOrigin.EXTRATO,
                status=PaymentStatus.EM_EXCECAO,
                amount=Decimal("350.00"),
                paid_at=now - timedelta(days=4),
                payer_name="Maria de Souza",
                payer_doc="12345678909",
                payer_bank="Nubank",
                bank_confirmed_at=now - timedelta(days=4),
                raw={"seed": True},
            )
            receipt = Payment(
                tenant_id=tenant.id,
                origin=PaymentOrigin.COMPROVANTE,
                status=PaymentStatus.AGUARDANDO_BANCO,
                amount=Decimal("1200.00"),
                paid_at=now - timedelta(hours=6),
                payer_name="Joao Pereira",
                payer_doc="98765432100",
                debtor_id=joao.id if joao else None,
                extraction_confidence=0.91,
                raw={"seed": True},
            )
            session.add_all([unidentified, suggestion, receipt])
            session.flush()

            session.add_all([
                ReviewException(
                    tenant_id=tenant.id,
                    type=ExceptionType.PAGAMENTO_NAO_IDENTIFICADO,
                    payment_id=unidentified.id,
                    details={"reason": "nenhum título candidato", "layer": 4},
                ),
                ReviewException(
                    tenant_id=tenant.id,
                    type=ExceptionType.SUGESTAO_MATCH,
                    payment_id=suggestion.id,
                    invoice_id=by_ext["demo-1"].id if "demo-1" in by_ext else None,
                    details={
                        "reason": "candidatos com score, aguardando confirmação humana",
                        "layer": 3,
                        "suggestions": [
                            {
                                "method": "valor_nome",
                                "score": 0.93,
                                "allocations": [
                                    {
                                        "invoice_id": str(by_ext["demo-1"].id),
                                        "amount": "350.00",
                                    }
                                ],
                            }
                        ],
                    },
                ),
            ])
            if joao:
                by_ext["demo-3"].status = InvoiceStatus.CONTESTADO
                session.add(
                    ReviewException(
                        tenant_id=tenant.id,
                        type=ExceptionType.CONTESTACAO,
                        invoice_id=by_ext["demo-3"].id,
                        details={"debtor_id": str(joao.id), "motivo": "valor diferente do combinado"},
                    )
                )

        if maria and not session.scalars(
            select(Conversation).where(Conversation.debtor_id == maria.id)
        ).first():
            conv = Conversation(
                tenant_id=tenant.id,
                debtor_id=maria.id,
                wa_jid="5511988887777",
                intent="parcelar_desconto",
                state=ConversationState.AGUARDANDO_APROVACAO,
                summary="Pediu 8 parcelas. A política do tenant permite no máximo 6.",
                identity_verified=True,
            )
            session.add(conv)
            session.flush()
            session.add_all([
                Message(
                    tenant_id=tenant.id,
                    conversation_id=conv.id,
                    invoice_id=by_ext.get("demo-1").id if "demo-1" in by_ext else None,
                    direction="in",
                    author="devedor",
                    body="Oi, não vou conseguir pagar à vista. Dá para parcelar em 8 vezes?",
                    created_at=now - timedelta(hours=2),
                ),
                Message(
                    tenant_id=tenant.id,
                    conversation_id=conv.id,
                    invoice_id=by_ext.get("demo-1").id if "demo-1" in by_ext else None,
                    direction="out",
                    author="agente",
                    body=(
                        "Consigo oferecer à vista com 10% de desconto ou entrada + até 6 parcelas. "
                        "Oito vezes fica fora da política — vou pedir uma aprovação."
                    ),
                    created_at=now - timedelta(hours=1, minutes=50),
                ),
            ])
            session.add(
                Approval(
                    tenant_id=tenant.id,
                    conversation_id=conv.id,
                    thread_id=f"demo-{conv.id}",
                    reason="Pedido de 8 parcelas acima do máximo da política (6).",
                    payload={"pedido": "8x", "max_politica": 6, "invoice_id": str(by_ext["demo-1"].id)},
                )
            )

        print(
            f"tenant demo: {tenant.id} · títulos criados {result.created}, "
            f"atualizados {result.updated}"
        )


TEST_PHONE = "5511952313944"

# Cada vencimento cai numa etapa da régua no dia em que o comando roda.
# offset é o mesmo da etapa: D-3 vence daqui a 3 dias, D+15 venceu há 15.
ENVIO_CASES = [
    ("envio-d-3", "Carla Mendes", "20000000191", "180.00", 3, "Lembrete · consulta de avaliação", "D-3"),
    ("envio-d0", "Pedro Alves", "20000000272", "240.00", 0, "Vence hoje · sessão de fisioterapia", "D0"),
    ("envio-d1", "Lúcia Ferreira", "20000000353", "310.00", -1, "Atraso · segunda via do retorno", "D+1"),
    ("envio-d3", "Helena Prado", "20000000606", "390.00", -3, "Atraso · desconto à vista no clareamento", "D+3"),
    ("envio-d5", "Rafael Costa", "20000000434", "420.00", -5, "Atraso · negociação do pacote de exames", "D+5"),
    ("envio-d7", "Marcos Vieira", "20000000797", "510.00", -7, "Atraso · parcelamento da manutenção", "D+7"),
    ("envio-d10", "Camila Duarte", "20000000878", "640.00", -10, "Atraso · entrada e saldo do implante", "D+10"),
    ("envio-d15", "Beatriz Nunes", "20000000515", "560.00", -15, "Atraso · última tentativa do tratamento", "D+15"),
    ("envio-d21", "Otávio Ramos", "20000000959", "780.00", -21, "Atraso · aviso de restrição da prótese", "D+21"),
]


def seed_envio() -> None:
    """Grava a régua no tenant e cria um título por etapa, todos no mesmo telefone.

    Não envia mensagem. A régua dispara quando o worker roda, dentro do horário
    do tenant. Sem e-mail, as etapas com e-mail saem só pelo WhatsApp.
    """
    from app.core.config import get_settings
    from app.core.db import SessionLocal, set_tenant
    from app.dunning.rules import DEFAULT_DUNNING_RULES
    from app.ingest.schemas import InvoiceIn
    from app.ingest.service import import_invoices
    from app.models import Tenant

    if get_settings().env == "prod":
        sys.exit("seed-envio não roda em produção")

    with SessionLocal() as session, session.begin():
        tenant = session.query(Tenant).filter_by(slug="demo").first()
        if tenant is None:
            sys.exit("tenant demo não encontrado — rode python -m app.cli seed-demo")
        set_tenant(session, tenant.id)
        tenant.dunning_rules = DEFAULT_DUNNING_RULES

        today = date.today()
        rows = [
            InvoiceIn(
                external_id=external_id,
                debtor_name=name,
                debtor_document=doc,
                debtor_phone=TEST_PHONE,
                amount=Decimal(amount),
                due_date=today + timedelta(days=offset),
                description=desc,
                txid=f"tx{external_id}",
                pix_copy_paste=f"00020126{external_id}",
                payment_url=f"https://pagar.demo.local/{external_id}",
            )
            for external_id, name, doc, amount, offset, desc, _step in ENVIO_CASES
        ]
        result = import_invoices(session, tenant.id, rows, "seed-envio")

    print(
        f"tenant demo · telefone {TEST_PHONE} · "
        f"títulos criados {result.created}, atualizados {result.updated}"
    )
    for external_id, name, _doc, amount, offset, desc, step in ENVIO_CASES:
        due = today + timedelta(days=offset)
        print(f"  {step:<5} {due.isoformat()}  {name:<16} R$ {amount}  {desc}  ({external_id})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument("command", choices=["migrate", "seed-demo", "seed-envio"])
    args = parser.parse_args()
    {"migrate": migrate, "seed-demo": seed_demo, "seed-envio": seed_envio}[args.command]()


if __name__ == "__main__":
    main()
