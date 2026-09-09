"""Add fecha_escaneo column to devoluciones

fecha_actualizacion se pisa en cada re-carga del Excel de devoluciones (ON
CONFLICT DO UPDATE la toca siempre, sin tocar estado — ver
devoluciones_service.py), por lo que no sirve para reportes "del día". Se
agrega una columna separada que solo se estampa cuando estado pasa a
'devolucion' (ver devoluciones.py PATCH).

Revision ID: 028
Revises: 027
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devoluciones", sa.Column("fecha_escaneo", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    # Backfill best-effort: no existe forma de reconstruir el momento exacto
    # real de escaneo para filas ya marcadas 'devolucion' antes de este cambio;
    # fecha_actualizacion es la mejor aproximación disponible.
    op.execute(
        "UPDATE devoluciones SET fecha_escaneo = fecha_actualizacion "
        "WHERE estado = 'devolucion' AND fecha_escaneo IS NULL"
    )


def downgrade() -> None:
    op.drop_column("devoluciones", "fecha_escaneo")
