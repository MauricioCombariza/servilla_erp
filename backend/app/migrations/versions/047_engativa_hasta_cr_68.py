"""Engativá: el límite oriental de 111071 pasa de CR 72 a CR 68 (Av. 68)
(la franja CR 68–72 entre CL 26 y CL 63 no la cubría ningún código postal, así que
direcciones como CR 69 # 47-50 quedaban sin localidad). Sin zona: decisión del usuario.
El CSV semilla de la 031 ya trae el valor nuevo; esto actualiza bases que ya la aplicaron.

Revision ID: 047
Revises: 046
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_oriente = 'CR 68'
        WHERE tipo = 'codigo_postal' AND nombre = '111071'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_oriente = 'CR 72'
        WHERE tipo = 'codigo_postal' AND nombre = '111071'
    """)
