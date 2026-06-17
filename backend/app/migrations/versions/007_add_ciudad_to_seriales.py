"""Add ciudad column to seriales_gestion

Revision ID: 007
Revises: 006
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE seriales_gestion
        ADD COLUMN IF NOT EXISTS ciudad VARCHAR(150)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_seriales_ciudad
        ON seriales_gestion (planilla, ciudad)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_seriales_ciudad")
    op.execute("ALTER TABLE seriales_gestion DROP COLUMN IF EXISTS ciudad")
