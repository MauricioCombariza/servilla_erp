"""Fontibón: el límite occidental de 110911 y 110921 pasa a CR 150 (río Bogotá)
(antes CR 125/130 dejaban por fuera direcciones como CR 135 # 17-84 y ningún otro
código postal las cubría, así que quedaban sin localidad).
El CSV semilla de la 031 ya trae el valor nuevo; esto actualiza bases que ya la aplicaron.

Revision ID: 046
Revises: 045
Create Date: 2026-10-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANTERIORES = {"110911": "CR 125", "110921": "CR 130"}


def upgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_occidente = 'CR 150'
        WHERE tipo = 'codigo_postal' AND nombre IN ('110911', '110921')
    """)


def downgrade() -> None:
    for cp, limite in ANTERIORES.items():
        op.execute(f"""
            UPDATE sectorizacion_limites SET limite_occidente = '{limite}'
            WHERE tipo = 'codigo_postal' AND nombre = '{cp}'
        """)
