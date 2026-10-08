"""Ajusta los límites de las zonas 60_1, 60_10 y 60_11 (zonas_especificas.xlsx
actualizado por el usuario el 2026-10-08). 60_10 empieza en la CL 64 para no pisar
a 60_11 (CL 63–64), decisión del usuario.

Revision ID: 040
Revises: 039
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNAS = ("limite_norte", "placas_norte", "limite_sur", "placas_sur",
            "limite_oriente", "placas_oriente", "limite_occidente", "placas_occidente")

NUEVOS = {
    "60_1": ("CL 63F", "par", "CL 63", "impar", "CR 24", "impar", "CR 30", "par"),
    "60_10": ("CL 64", "par", "CL 68", "impar", "CR 30", "impar", "CR 60", "par"),
    "60_11": ("CL 63", "par", "CL 64", "impar", "CR 30", "impar", "CR 60", "par"),
}

ANTERIORES = {
    "60_1": ("CL 63F", "par", "CL 63", "impar", "CR 24", "impar", "CR 36", "par"),
    "60_10": ("CL 63", "par", "CL 68", "impar", "CR 30", "impar", "CR 54", "par"),
    "60_11": ("CL 63", "par", "CL 68", "impar", "CR 54", "impar", "CR 60", "par"),
}


def _aplicar(valores: dict[str, tuple]) -> None:
    sets = ", ".join(f"{c} = :{c}" for c in COLUMNAS)
    sentencia = sa.text(f"UPDATE sectorizacion_limites SET {sets} WHERE tipo = 'zona' AND nombre = :nombre")
    for nombre, fila in valores.items():
        op.get_bind().execute(sentencia, {"nombre": nombre, **dict(zip(COLUMNAS, fila))})


def upgrade() -> None:
    _aplicar(NUEVOS)


def downgrade() -> None:
    _aplicar(ANTERIORES)
