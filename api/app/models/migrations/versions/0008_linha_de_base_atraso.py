"""linha de base do atraso médio anterior à implantação

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-09 23:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("baseline_avg_days_late", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "baseline_avg_days_late")
