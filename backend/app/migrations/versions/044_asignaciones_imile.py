"""Paso 3.3: asignación de los paquetes del mensajero en iMile.

- personal.nombre_imile: el nombre con que el mensajero aparece en iMile, cuando no es
  igual al del ERP.
- asignaciones_imile: resultado de asignar cada serial en iMile, por día. Un serial queda
  con el último mensajero al que se mandó.

Revision ID: 044
Revises: 043
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("personal", sa.Column("nombre_imile", sa.String(150), nullable=True))
    op.create_table(
        "asignaciones_imile",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("serial", sa.String(50), nullable=False),
        sa.Column("personal_id", sa.Integer, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("mensaje", sa.Text, nullable=True),
        sa.Column("codigo", sa.String(20), nullable=True),
        sa.Column("usuario", sa.String(50), nullable=False),
        sa.Column("fecha_envio", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("fecha", "serial", name="uq_asignaciones_imile_fecha_serial"),
    )


def downgrade() -> None:
    op.drop_table("asignaciones_imile")
    op.drop_column("personal", "nombre_imile")
