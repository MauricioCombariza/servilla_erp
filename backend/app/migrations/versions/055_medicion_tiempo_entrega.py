"""Columnas para medir el tiempo de entrega de los paquetes iMile (mejora continua):

- fecha_entrega: hora de entrega al cliente final ("Delivered time" del informe
  Delivered de iMile, se llena en la carga masiva).
- fecha_llegada_ds: hora de llegada a la estación según iMile (evento "Arrived" del
  tracking; inicio del reloj de las 48 h).
- novedades_imile: lista de novedades del tracking ([{"hora", "motivo"}], un elemento
  por cada "add a problem"). NULL = todavía no se ha consultado el tracking.

Revision ID: 055
Revises: 054
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "055"
down_revision: Union[str, None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("seriales_gestion", sa.Column("fecha_entrega", sa.TIMESTAMP(timezone=True)))
    op.add_column("seriales_gestion", sa.Column("fecha_llegada_ds", sa.TIMESTAMP(timezone=True)))
    op.add_column("seriales_gestion", sa.Column("novedades_imile", JSONB))
    op.create_index("idx_sg_fecha_entrega", "seriales_gestion", ["fecha_entrega"])
    # Las guías entregadas a las que les falta consultar el tracking
    op.create_index(
        "idx_sg_tracking_pendiente", "seriales_gestion", ["fecha_entrega"],
        postgresql_where=sa.text("fecha_entrega IS NOT NULL AND novedades_imile IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_sg_tracking_pendiente", table_name="seriales_gestion")
    op.drop_index("idx_sg_fecha_entrega", table_name="seriales_gestion")
    op.drop_column("seriales_gestion", "novedades_imile")
    op.drop_column("seriales_gestion", "fecha_llegada_ds")
    op.drop_column("seriales_gestion", "fecha_entrega")
