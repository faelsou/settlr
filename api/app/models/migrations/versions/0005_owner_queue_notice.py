"""contato do dono para o aviso da fila humana

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08 15:50:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("owner_email", sa.String(length=200), nullable=True))
    op.add_column("tenants", sa.Column("owner_phone", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "owner_phone")
    op.drop_column("tenants", "owner_email")
