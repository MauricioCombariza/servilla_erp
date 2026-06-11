"""Add planillas_revisadas table

Revision ID: 005
Revises: 004
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planillas_revisadas",
        sa.Column("planilla", sa.String(100), primary_key=True),
        sa.Column(
            "fecha_revision",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revisado_por", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("planillas_revisadas")
