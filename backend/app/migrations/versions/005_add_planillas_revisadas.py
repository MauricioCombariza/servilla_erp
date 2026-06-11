"""Add planillas_revisadas table

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
    op.execute("""
        CREATE TABLE IF NOT EXISTS planillas_revisadas (
            planilla VARCHAR(100) NOT NULL PRIMARY KEY,
            fecha_revision TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            revisado_por VARCHAR(100)
        )
    """)


def downgrade() -> None:
    op.drop_table("planillas_revisadas")
