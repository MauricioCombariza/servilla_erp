"""tulas.seriales_esperados: los seriales que trae la tula según iMile (Paso 2.3), para
mostrar al cerrarla cuáles faltaron y cuáles llegaron sin venir en ella.

Revision ID: 042
Revises: 041
Create Date: 2026-10-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tulas", sa.Column("seriales_esperados", postgresql.ARRAY(sa.String(50)), nullable=True))


def downgrade() -> None:
    op.drop_column("tulas", "seriales_esperados")
