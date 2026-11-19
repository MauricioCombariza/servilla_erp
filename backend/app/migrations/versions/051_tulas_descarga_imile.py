"""Descarga automática de la tula en iMile ("Descarga de escaneo" / dsOffloadingScan).

Si al abrir una tula iMile todavía no la tiene descargada, el servicio Go la descarga
(tarea "descarga" en imile_tareas) y después consulta cuántos paquetes trae. Aquí
queda cómo terminó, y el celular lo ve en /api/flujo/cambios (por imile_fecha).

Revision ID: 051
Revises: 050
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "051"
down_revision: Union[str, None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pendiente | ok | repetido | error | bloqueado | sin_confirmar
    op.add_column("tulas", sa.Column("imile_descarga_estado", sa.String(20)))
    op.add_column("tulas", sa.Column("imile_descarga_mensaje", sa.Text))
    op.add_column("tulas", sa.Column("imile_fecha", sa.TIMESTAMP(timezone=True)))
    op.create_index("idx_tulas_imile_fecha", "tulas", ["imile_fecha"])


def downgrade() -> None:
    op.drop_index("idx_tulas_imile_fecha", table_name="tulas")
    op.drop_column("tulas", "imile_fecha")
    op.drop_column("tulas", "imile_descarga_mensaje")
    op.drop_column("tulas", "imile_descarga_estado")
