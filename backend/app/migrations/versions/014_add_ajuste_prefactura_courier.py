"""Add valor_ajustado/notas_ajuste to prefacturas_courier (ajustar monto a pagar real)

Revision ID: 014
Revises: 013
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prefacturas_courier",
        sa.Column("valor_ajustado", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "prefacturas_courier",
        sa.Column("notas_ajuste", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prefacturas_courier", "notas_ajuste")
    op.drop_column("prefacturas_courier", "valor_ajustado")
