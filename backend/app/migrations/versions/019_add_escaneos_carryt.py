"""Add escaneos_carryt (registro de paquetes Carryt escaneados por mensajero)

Revision ID: 019
Revises: 018
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "escaneos_carryt",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("cliente", sa.String(50), server_default="'Carryt'", nullable=False),
        sa.Column("fecha", sa.Date, server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("cod_men", sa.String(4), nullable=False),
        sa.Column("nombre_mensajero", sa.String(150), nullable=False),
        sa.Column("serial", sa.String(50), unique=True, nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_ec_cod_men_fecha", "escaneos_carryt", ["cod_men", "fecha"])


def downgrade() -> None:
    op.drop_index("idx_ec_cod_men_fecha", table_name="escaneos_carryt")
    op.drop_table("escaneos_carryt")
