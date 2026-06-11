"""Add revisado_por to planillas_revisadas

Revision ID: 005
Revises: 004
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La tabla planillas_revisadas ya existe desde 001_initial_schema.
    # Solo agregamos la columna revisado_por si no existe.
    op.execute("""
        ALTER TABLE planillas_revisadas
        ADD COLUMN IF NOT EXISTS revisado_por VARCHAR(100)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE planillas_revisadas DROP COLUMN IF EXISTS revisado_por")
