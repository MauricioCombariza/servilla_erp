"""Add devoluciones (seriales devueltos cargados por Excel, con estado de seguimiento)

Revision ID: 022
Revises: 021
Create Date: 2026-08-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devoluciones",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("serial", sa.String(50), unique=True, nullable=False),
        sa.Column("nombre", sa.String(255), nullable=True),
        sa.Column("telefono", sa.String(20), nullable=True),
        sa.Column("direccion", sa.Text, nullable=True),
        sa.Column("localidad", sa.String(100), nullable=True),
        sa.Column("estado", sa.String(30), server_default="transito", nullable=False),
        sa.Column("fecha_carga", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("fecha_actualizacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_devoluciones_estado", "devoluciones", ["estado"])


def downgrade() -> None:
    op.drop_index("idx_devoluciones_estado", table_name="devoluciones")
    op.drop_table("devoluciones")
