"""recibo de entrega do WhatsApp: status na mensagem e reenvio após falha

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07 20:45:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("delivery_status", sa.String(length=24), nullable=True))
    op.create_index("ix_messages_wa_message_id", "messages", ["wa_message_id"], unique=False)
    op.create_index("ix_dunning_events_message_id", "dunning_events", ["message_id"], unique=False)
    op.drop_constraint(
        "dunning_events_invoice_id_step_channel_key",
        "dunning_events",
        type_="unique",
    )
    op.create_index(
        "uq_dunning_events_step_aberto",
        "dunning_events",
        ["invoice_id", "step", "channel"],
        unique=True,
        postgresql_where=sa.text("delivery_status <> 'falhou'"),
    )


def downgrade() -> None:
    op.drop_index("uq_dunning_events_step_aberto", table_name="dunning_events")
    op.create_unique_constraint(
        "dunning_events_invoice_id_step_channel_key",
        "dunning_events",
        ["invoice_id", "step", "channel"],
    )
    op.drop_index("ix_dunning_events_message_id", table_name="dunning_events")
    op.drop_index("ix_messages_wa_message_id", table_name="messages")
    op.drop_column("messages", "delivery_status")
