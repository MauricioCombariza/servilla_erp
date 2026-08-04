"""Add valor_ajustado/notas_ajuste to liquidaciones (ajustar monto a pagar real)

Revision ID: 017
Revises: 016
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "liquidaciones",
        sa.Column("valor_ajustado", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "liquidaciones",
        sa.Column("notas_ajuste", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("liquidaciones", "notas_ajuste")
    op.drop_column("liquidaciones", "valor_ajustado")
