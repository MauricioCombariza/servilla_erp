"""Add geocercas (geocercas hexagonales dibujadas manualmente sobre el mapa,
con área en m2 calculada server-side; base para futura sectorización de entregas)

Revision ID: 026
Revises: 025
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geocercas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("poligono", postgresql.JSONB, nullable=False),
        sa.Column("area_m2", sa.Numeric(12, 2), nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("creado_por", sa.String(100), nullable=True),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("fecha_actualizacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_geocercas_activo", "geocercas", ["activo"])


def downgrade() -> None:
    op.drop_index("idx_geocercas_activo", table_name="geocercas")
    op.drop_table("geocercas")
