"""Add ajustes_liquidacion: descuentos/bonificaciones pendientes por aplicar

Hasta el 2026-09-09 la liquidación no exigía planilla, y el importador llena
f_esc con f_emi cuando el serial aún no se ha escaneado: se pagaron seriales
antes de escanearse (con la fecha de emisión). Al reabrirlos para liquidarlos
en el mes real de escaneo, lo ya cobrado debe descontarse en la siguiente
liquidación del mensajero. Esta tabla guarda ese ajuste hasta que /generar lo
aplica (liquidacion_aplicada_id).

Revision ID: 030
Revises: 029
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ajustes_liquidacion",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("personal_id", sa.Integer, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("motivo", sa.Text, nullable=False),
        sa.Column("liquidacion_origen_id", sa.Integer, sa.ForeignKey("liquidaciones.id", ondelete="SET NULL")),
        sa.Column("liquidacion_aplicada_id", sa.Integer, sa.ForeignKey("liquidaciones.id", ondelete="SET NULL")),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("tipo IN ('descuento', 'bonificacion')", name="ck_ajustes_liquidacion_tipo"),
        sa.CheckConstraint("monto > 0", name="ck_ajustes_liquidacion_monto"),
    )
    op.create_index(
        "idx_ajustes_liquidacion_pendientes", "ajustes_liquidacion", ["personal_id"],
        postgresql_where=sa.text("liquidacion_aplicada_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_ajustes_liquidacion_pendientes", table_name="ajustes_liquidacion")
    op.drop_table("ajustes_liquidacion")
