"""Nombres nuevos de las zonas (zonas_produccion_2026-10-21.xlsx, del usuario el 2026-10-21).

Varias zonas se juntan bajo un mismo nombre (p. ej. 60_2, 60_3 y 60_4 pasan a ser 60_1):
cada fila sigue siendo un rectángulo con sus límites, y una zona puede tener varios. Por eso
se quita la restricción de nombre único. Se renombra por `orden`, que no cambia, para que
sirva igual en producción que en una base nueva (cuyo CSV semilla ya trae los nombres
nuevos) y para que el intercambio 70_1 ↔ 70_2 no choque.

Lo ya registrado con los nombres viejos (tulas, paquetes, asignaciones) no se toca.

Revision ID: 043
Revises: 042
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# orden: (nombre anterior, nombre nuevo). Las demás zonas no cambian.
CAMBIOS = {
    1: ("60_1", "60_3"),
    2: ("60_2", "60_1"),
    3: ("60_3", "60_1"),
    4: ("60_4", "60_1"),
    5: ("60_5", "60_2"),
    6: ("60_6", "60_2"),
    7: ("60_7", "60_3"),
    8: ("60_8", "60_4"),
    9: ("60_9", "60_7"),
    10: ("60_10", "60_6"),
    11: ("60_11", "60_5"),
    12: ("60_12", "60_8"),
    13: ("60_13", "60_3"),
    14: ("70_1", "70_2"),
    15: ("70_2", "70_1"),
}

_RENOMBRAR = sa.text("UPDATE sectorizacion_limites SET nombre = :nombre WHERE tipo = 'zona' AND orden = :orden")


def upgrade() -> None:
    op.drop_constraint("uq_sectorizacion_limites_tipo_nombre", "sectorizacion_limites", type_="unique")
    for orden, (_, nuevo) in CAMBIOS.items():
        op.get_bind().execute(_RENOMBRAR, {"orden": orden, "nombre": nuevo})


def downgrade() -> None:
    for orden, (anterior, _) in CAMBIOS.items():
        op.get_bind().execute(_RENOMBRAR, {"orden": orden, "nombre": anterior})
    op.create_unique_constraint("uq_sectorizacion_limites_tipo_nombre", "sectorizacion_limites", ["tipo", "nombre"])
