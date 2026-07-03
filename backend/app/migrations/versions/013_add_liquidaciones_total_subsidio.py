"""Add liquidaciones.total_subsidio (transport subsidy was never paid out)

Revision ID: 013
Revises: 012
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "liquidaciones",
        sa.Column("total_subsidio", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("liquidaciones", "total_subsidio")
