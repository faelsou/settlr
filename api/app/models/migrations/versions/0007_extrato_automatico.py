"""extrato automático: feed do banco e lançamento único

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08 22:40:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "bank_feed",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("payments", sa.Column("source_id", sa.String(length=120), nullable=True))
    op.create_unique_constraint("uq_payments_tenant_source", "payments", ["tenant_id", "source_id"])


def downgrade() -> None:
    op.drop_constraint("uq_payments_tenant_source", "payments", type_="unique")
    op.drop_column("payments", "source_id")
    op.drop_column("tenants", "bank_feed")
