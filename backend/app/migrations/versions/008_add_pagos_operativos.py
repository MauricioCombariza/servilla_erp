"""Add pagos_operativos_mensuales

Revision ID: 008
Revises: 007
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pagos_operativos_mensuales",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("periodo_mes", sa.Integer, nullable=False),
        sa.Column("periodo_anio", sa.Integer, nullable=False),
        sa.Column("monto_total", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("fecha_vencimiento", sa.Date, nullable=True),
        sa.Column("estado", sa.String(20), server_default="pendiente"),
        sa.Column("fecha_pago", sa.Date, nullable=True),
        sa.Column("observaciones", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tipo", "periodo_mes", "periodo_anio", name="uq_pago_tipo_periodo"),
    )


def downgrade() -> None:
    op.drop_table("pagos_operativos_mensuales")
