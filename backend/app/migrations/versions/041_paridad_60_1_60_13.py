"""Corrige la paridad de placa en los bordes de 60_1 y 60_13 (prueba de exactitud
contra el histórico, aprobada por el usuario el 2026-10-09):
  - 60_1, CL 63: impar → par (como sus vecinas 60_2, 60_3 y 60_11). Las placas pares de
    la CL 63 entre CR 24 y 30 quedaban fuera de zona y las entregaba el mensajero de 60_1.
  - 60_13, CL 63F: par → impar. 60_1 y 60_13 decían ambas "par", así que las placas
    impares de la CL 63F no caían en ninguna zona.

Revision ID: 041
Revises: 040
Create Date: 2026-10-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (zona, columna de paridad, valor nuevo, valor anterior)
CAMBIOS = [
    ("60_1", "placas_sur", "par", "impar"),       # limite_sur = CL 63
    ("60_13", "placas_norte", "impar", "par"),    # limite_norte = CL 63F
]


def _aplicar(nuevo: bool) -> None:
    for zona, columna, valor_nuevo, valor_anterior in CAMBIOS:
        op.get_bind().execute(
            sa.text(f"UPDATE sectorizacion_limites SET {columna} = :valor WHERE tipo = 'zona' AND nombre = :zona"),
            {"valor": valor_nuevo if nuevo else valor_anterior, "zona": zona},
        )


def upgrade() -> None:
    _aplicar(nuevo=True)


def downgrade() -> None:
    _aplicar(nuevo=False)
