"""Entre la CL 72 y la CL 100, las zonas del borde oriental (70_1, 70_2 y 80_1) cubren
desde la CR 24 hasta la CR 1 (antes llegaban hasta la CR 20, placa impar). Lo que quedaba
al oriente de la CR 20 en Chapinero salía sin zona (p. ej. "CL 72 13 49", "CL 85 14 43").
Decisión del usuario (2026-11-05). El CSV semilla de la 031 ya trae el valor nuevo; esto
actualiza las bases que ya la aplicaron.

Revision ID: 049
Revises: 048
Create Date: 2026-11-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ZONAS = "('70_1', '70_2', '80_1')"


def upgrade() -> None:
    op.execute(f"""
        UPDATE sectorizacion_limites SET limite_oriente = 'CR 1', placas_oriente = NULL
        WHERE tipo = 'zona' AND nombre IN {_ZONAS} AND limite_oriente = 'CR 20'
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE sectorizacion_limites SET limite_oriente = 'CR 20', placas_oriente = 'impar'
        WHERE tipo = 'zona' AND nombre IN {_ZONAS} AND limite_oriente = 'CR 1'
    """)
