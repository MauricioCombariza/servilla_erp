"""Zona 80_1 (CR 20–24) llega hasta la CL 100 (antes CL 92): la Autopista Norte entre
CL 92 y CL 99 se traduce a CR 20 y quedaba sin zona ("Autopista Norte 95-01").
Decisión del usuario. El CSV semilla de la 031 ya trae el valor nuevo; esto actualiza
bases que ya la aplicaron.

Revision ID: 048
Revises: 047
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_sur = 'CL 100'
        WHERE tipo = 'zona' AND nombre = '80_1'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE sectorizacion_limites SET limite_sur = 'CL 92'
        WHERE tipo = 'zona' AND nombre = '80_1'
    """)
