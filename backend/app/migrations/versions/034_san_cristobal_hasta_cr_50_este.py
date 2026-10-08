"""San Cristóbal: el límite oriental de sus códigos postales pasa a CR 50 ESTE
(antes CR 15/17/20 ESTE dejaban por fuera direcciones como CL 11 # 16-99 SUR ESTE).
El CSV semilla de la 031 ya trae el valor nuevo; esto actualiza bases que ya la aplicaron.

Revision ID: 034
Revises: 033
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANTERIORES = {"110411": "CR 15 ESTE", "110421": "CR 15 ESTE", "110431": "CR 17 ESTE", "110441": "CR 20 ESTE"}


def upgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_oriente = 'CR 50 ESTE'
        WHERE tipo = 'codigo_postal' AND nombre IN ('110411', '110421', '110431', '110441')
    """)


def downgrade() -> None:
    for cp, limite in ANTERIORES.items():
        op.execute(f"""
            UPDATE sectorizacion_limites SET limite_oriente = '{limite}'
            WHERE tipo = 'codigo_postal' AND nombre = '{cp}'
        """)
