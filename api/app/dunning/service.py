"""Execução da régua no banco e no WhatsApp. A decisão em si está em `rules.py`."""

import time
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.policy import brl
from app.channels.delivery import ACEITO, ENVIADO, PENDENTE, counts_as_dispatched
from app.channels.email import send_email
from app.channels.metrics import record_message
from app.channels.outbound import get_or_create_conversation, log_message
from app.channels.whatsapp import EvolutionClient
from app.core.audit import audit
from app.core.phones import contact_phones
from app.core.redis import get_redis
from app.dunning.rules import DEFAULT_DUNNING_RULES, Step, decide, parse_steps
from app.models import Debtor, DunningEvent, Invoice, Promise, Tenant
from app.models.enums import DUNNING_STATUSES, ExceptionType, InvoiceStatus, MessageDirection
from app.reconciliation.service import open_exception, set_invoice_status

DEFAULT_RATE_PER_MINUTE = 20


class RateLimited(RuntimeError):
    pass


def take_rate_slot(instance: str, per_minute: int) -> bool:
    key = f"rl:wa:{instance}:{int(time.time() // 60)}"
    r = get_redis()
    count = r.incr(key)
    if count == 1:
        r.expire(key, 120)
    return count <= per_minute


def eligible_invoice_ids(session: Session, tenant: Tenant, today: date) -> list[UUID]:
    steps = parse_steps(tenant.dunning_rules)
    horizon = today - timedelta(days=min(s.offset for s in steps))
    return list(
        session.scalars(
            select(Invoice.id)
            .where(Invoice.tenant_id == tenant.id)
            .where(Invoice.status.in_(DUNNING_STATUSES))
            .where(Invoice.due_date <= horizon)
            .order_by(Invoice.due_date)
        )
    )


def render(template: str, invoice: Invoice, debtor: Debtor) -> str:
    return template.format(
        nome=debtor.name.split()[0].title(),
        descricao=invoice.description or f"título {invoice.external_id}",
        valor=brl(invoice.amount_open if invoice.amount_open > 0 else Decimal(invoice.amount)),
        vencimento=invoice.due_date.strftime("%d/%m/%Y"),
        pix=invoice.pix_copy_paste or "-",
        link=invoice.payment_url or invoice.digitable_line or "-",
    )


@dataclass
class StepOutcome:
    action: str
    reason: str = ""


def process_invoice(
    session: Session,
    tenant: Tenant,
    invoice_id: UUID,
    today: date,
    client: EvolutionClient | None = None,
) -> StepOutcome:
    invoice = session.scalars(select(Invoice).where(Invoice.id == invoice_id).with_for_update()).one()
    debtor = session.get(Debtor, invoice.debtor_id)

    recorded = session.execute(
        select(DunningEvent.step, DunningEvent.channel, DunningEvent.delivery_status).where(
            DunningEvent.invoice_id == invoice.id
        )
    ).tuples()
    sent = {(step, channel) for step, channel, status in recorded if counts_as_dispatched(status)}
    active_promise = session.scalar(
        select(func.max(Promise.promised_date)).where(
            Promise.invoice_id == invoice.id, Promise.fulfilled.is_(None)
        )
    )
    steps = parse_steps(tenant.dunning_rules)
    decision = decide(
        today=today,
        due_date=invoice.due_date,
        steps=steps,
        opt_out=debtor.opt_out,
        active_promise=active_promise,
        sent=sent,
    )

    if decision.action == "handoff":
        set_invoice_status(invoice, InvoiceStatus.FILA_HUMANA)
        open_exception(session, tenant.id, ExceptionType.FILA_HUMANA, invoice_id=invoice.id,
                       details={"reason": "fim da régua (D+30)"})
        return StepOutcome("handoff")
    if decision.action == "skip":
        return StepOutcome("skip", decision.reason)

    _send_step(session, tenant, invoice, debtor, decision.step, decision.channels, client)
    if invoice.status == InvoiceStatus.ABERTO:
        set_invoice_status(invoice, InvoiceStatus.EM_COBRANCA)
    return StepOutcome("send", decision.step.key)


def _send_step(
    session: Session,
    tenant: Tenant,
    invoice: Invoice,
    debtor: Debtor,
    step: Step,
    channels: tuple[str, ...],
    client: EvolutionClient | None,
) -> None:
    rules = tenant.dunning_rules or DEFAULT_DUNNING_RULES
    templates = {**DEFAULT_DUNNING_RULES["templates"], **rules.get("templates", {})}
    wa_templates = rules.get("whatsapp_templates", {})
    text = render(templates[step.template], invoice, debtor)

    for channel in channels:
        message_id = None
        delivery_status = ENVIADO
        if channel == "whatsapp":
            numbers = contact_phones(debtor.phone, debtor.phones)
            if not numbers or not tenant.whatsapp_instance:
                record_message("saida", "enviada", "regua", "texto", "falha")
                continue
            per_minute = int(rules.get("rate_per_minute", DEFAULT_RATE_PER_MINUTE))
            client = client or EvolutionClient()
            official = wa_templates.get(step.template)
            conv = get_or_create_conversation(session, tenant.id, debtor)
            msg = log_message(
                session, conv, MessageDirection.OUT, f"regua:{step.key}", text,
                invoice_id=invoice.id, delivery_status=PENDENTE,
            )
            session.flush()
            message_ids: list[str | None] = []
            for number in numbers:
                if not take_rate_slot(tenant.whatsapp_instance, per_minute):
                    record_message("saida", "enviada", "regua", "texto", "falha")
                    raise RateLimited(tenant.whatsapp_instance)
                try:
                    if official:
                        message_ids.append(client.send_template(
                            tenant.whatsapp_instance, number, official["name"],
                            official.get("language", "pt_BR"),
                            [render(p, invoice, debtor) for p in official.get("params", [])],
                        ))
                    else:
                        message_ids.append(client.send_text(tenant.whatsapp_instance, number, text))
                except (httpx.TimeoutException, httpx.TransportError):
                    record_message("saida", "enviada", "regua", "texto", "falha")
                    break
                except Exception:
                    record_message("saida", "enviada", "regua", "texto", "falha")
                    raise
                record_message("saida", "enviada", "regua", "texto", "ok")
            if message_ids:
                message_id = next((item for item in message_ids if item), None)
                msg.wa_message_id = message_id
                msg.delivery_status = ACEITO
                delivery_status = ACEITO
            else:
                message_id = None
                delivery_status = PENDENTE
        elif channel == "email":
            if not debtor.email:
                continue
            send_email(debtor.email, f"Aviso sobre {invoice.description or 'seu pagamento'}", text)
            delivery_status = ENVIADO
        else:
            continue

        session.add(DunningEvent(
            tenant_id=tenant.id, invoice_id=invoice.id, step=step.key,
            channel=channel, message_id=message_id, delivery_status=delivery_status,
        ))
        sent_to = contact_phones(debtor.phone, debtor.phones) if channel == "whatsapp" else []
        audit(
            session, tenant_id=tenant.id, actor="regua", action="disparo",
            entity="invoice", entity_id=invoice.id,
            after={
                "step": step.key,
                "channel": channel,
                "message_id": message_id,
                "delivery_status": delivery_status,
                "phones": sent_to,
            },
        )
