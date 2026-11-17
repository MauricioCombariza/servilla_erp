"""Códigos postales 110871 (Kennedy) y 111811 (Rafael Uribe Uribe) con límites corregidos.

- 110871 tenía límite norte CL 63 y, como se evalúa antes que Fontibón 110921
  (CL 12–22, CR 86–150), se quedaba con direcciones de Fontibón
  ("CL 15 # 119A-60", El Recodo). Ahora llega hasta la CL 12.
- 111811 solo cubría CR 27 ESTE–CR 14, así que ningún código de Rafael Uribe Uribe
  incluía la CR 20 ("CL 29 SUR # 20-09", Quiroga) y caía en 110851 (Kennedy).
  Ahora es CL 22 SUR–CL 47A SUR, CR 14–CR 30.

El CSV semilla de la 031 ya trae los valores nuevos; esto actualiza bases que ya la aplicaron.

Revision ID: 054
Revises: 053
Create Date: 2026-11-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "054"
down_revision: Union[str, None] = "053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_norte = 'CL 12'
        WHERE tipo = 'codigo_postal' AND nombre = '110871'
    """)
    op.execute("""
        UPDATE sectorizacion_limites
        SET limite_norte = 'CL 22 SUR', limite_oriente = 'CR 14', limite_occidente = 'CR 30'
        WHERE tipo = 'codigo_postal' AND nombre = '111811'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_norte = 'CL 63'
        WHERE tipo = 'codigo_postal' AND nombre = '110871'
    """)
    op.execute("""
        UPDATE sectorizacion_limites
        SET limite_norte = 'CL 1 SUR', limite_oriente = 'CR 27 ESTE', limite_occidente = 'CR 14'
        WHERE tipo = 'codigo_postal' AND nombre = '111811'
    """)
